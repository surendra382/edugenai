import asyncio
import io
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pdf2image import convert_from_bytes
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.models.chapter import Chapter
from backend.app.models.question_bank_item import QuestionBankItem
from backend.app.schemas.question_bank import (
    QuestionBankImportError,
    QuestionBankImportResult,
    QuestionBankItemRead,
)
from backend.app.services import question_bank_parser
from backend.app.services import vision_extractor as vision_extractor_module

router = APIRouter(tags=["question-bank"])

_IMAGE_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
_PDF_EXTENSIONS = {".pdf"}
# Each Gemini vision call takes several seconds to tens of seconds; without a
# cap here, one large multi-page PDF would either serialize (very slow for a
# whole scanned chapter) or fire dozens of calls at once (rate limits).
_MAX_CONCURRENT_EXTRACTIONS = 4


def _get_chapter_or_404(db: Session, chapter_id: int) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return chapter


def _get_question_bank_item_or_404(db: Session, item_id: int) -> QuestionBankItem:
    item = db.get(QuestionBankItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question bank item not found"
        )
    return item


def _exceeds_max_size(size_bytes: int) -> bool:
    return size_bytes > settings.max_upload_size_mb * 1024 * 1024


def _unique_path(target_dir: Path, filename: str) -> Path:
    return target_dir / f"{uuid.uuid4().hex[:8]}_{filename}"


def _extract_and_parse(page_bytes: bytes, mime_type: str) -> tuple[list[dict], list[str], str | None]:
    """Runs the (blocking, network-bound) extractor call plus parsing for one
    page. Returns (items, item_errors, hard_error) instead of raising, so a
    single bad page never short-circuits its siblings when run under
    asyncio.gather. Must not touch the SQLAlchemy session — this runs off
    the event loop via asyncio.to_thread, and Session isn't thread-safe."""
    try:
        raw_text = vision_extractor_module.vision_extractor.extract_raw(page_bytes, mime_type)
    except Exception as exc:  # noqa: BLE001 — any extractor failure is per-page, not fatal
        return [], [], f"extraction failed: {exc}"

    try:
        return (*question_bank_parser.parse(raw_text), None)
    except ValueError as exc:
        return [], [], str(exc)


async def _extract_and_parse_bounded(
    semaphore: asyncio.Semaphore, page_bytes: bytes, mime_type: str
) -> tuple[list[dict], list[str], str | None]:
    async with semaphore:
        return await asyncio.to_thread(_extract_and_parse, page_bytes, mime_type)


@router.post(
    "/chapters/{chapter_id}/question-bank/import",
    response_model=QuestionBankImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_question_bank(
    chapter_id: int,
    images: list[UploadFile] = File(...),
    class_grade: str = Form(...),
    source: str = Form(...),
    db: Session = Depends(get_db),
) -> QuestionBankImportResult:
    chapter = _get_chapter_or_404(db, chapter_id)

    target_dir = (
        Path(settings.knowledge_base_dir) / str(chapter.subject_id) / str(chapter_id) / "question_bank"
    )

    errors: list[QuestionBankImportError] = []
    # Each entry is one page ready for extraction: a standalone image, or one
    # page of a PDF (a PDF just expands into several of these up front).
    pages: list[dict] = []

    for image in images:
        filename = image.filename or "unnamed"
        extension = Path(filename).suffix.lower()

        if extension not in _IMAGE_MIME_TYPES and extension not in _PDF_EXTENSIONS:
            errors.append(
                QuestionBankImportError(
                    filename=filename, error=f"unsupported file type: {extension or 'unknown'}"
                )
            )
            continue

        contents = await image.read()
        if _exceeds_max_size(len(contents)):
            errors.append(
                QuestionBankImportError(
                    filename=filename,
                    error=f"file exceeds maximum size of {settings.max_upload_size_mb}MB",
                )
            )
            continue

        if extension in _IMAGE_MIME_TYPES:
            pages.append(
                {
                    "label": filename,
                    "storage_filename": filename,
                    "bytes": contents,
                    "mime_type": _IMAGE_MIME_TYPES[extension],
                }
            )
            continue

        try:
            pdf_pages = await asyncio.to_thread(convert_from_bytes, contents)
        except Exception as exc:  # noqa: BLE001 — a broken/unreadable PDF is per-file, not fatal
            errors.append(QuestionBankImportError(filename=filename, error=f"failed to read PDF: {exc}"))
            continue

        stem = Path(filename).stem
        for page_number, page_image in enumerate(pdf_pages, start=1):
            buffer = io.BytesIO()
            page_image.save(buffer, format="PNG")
            pages.append(
                {
                    "label": f"{filename} (page {page_number})",
                    "storage_filename": f"{stem}_page{page_number}.png",
                    "bytes": buffer.getvalue(),
                    "mime_type": "image/png",
                }
            )

    # The slow, network-bound part: run extractions concurrently (bounded)
    # instead of one page at a time, so a multi-page PDF doesn't take
    # minutes and doesn't hold the event loop hostage for other requests.
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EXTRACTIONS)
    results = await asyncio.gather(
        *(_extract_and_parse_bounded(semaphore, page["bytes"], page["mime_type"]) for page in pages)
    )

    created_items: list[QuestionBankItem] = []
    for page, (parsed_items, item_errors, hard_error) in zip(pages, results):
        if hard_error is not None:
            errors.append(QuestionBankImportError(filename=page["label"], error=hard_error))
            continue

        if not parsed_items:
            reason = "; ".join(item_errors) if item_errors else "no questions found"
            errors.append(QuestionBankImportError(filename=page["label"], error=reason))
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        stored_path = _unique_path(target_dir, page["storage_filename"])
        stored_path.write_bytes(page["bytes"])

        for item in parsed_items:
            row = QuestionBankItem(
                chapter_id=chapter_id,
                class_grade=class_grade,
                source=source,
                question_type=item["question_type"],
                stem=item["stem"],
                concept=item["concept"],
                options=json.dumps(item["options"]) if item["options"] else None,
                answer=item["answer"],
                difficulty=item["difficulty"],
                source_image=str(stored_path),
            )
            db.add(row)
            created_items.append(row)

        if item_errors:
            errors.append(
                QuestionBankImportError(
                    filename=page["label"],
                    error=f"{len(item_errors)} item(s) skipped: " + "; ".join(item_errors),
                )
            )

    db.commit()
    for row in created_items:
        db.refresh(row)

    return QuestionBankImportResult(created=len(created_items), items=created_items, errors=errors)


@router.get("/chapters/{chapter_id}/question-bank", response_model=list[QuestionBankItemRead])
def list_question_bank_items(
    chapter_id: int,
    difficulty: str | None = Query(None),
    type: str | None = Query(None, alias="type"),
    db: Session = Depends(get_db),
) -> list[QuestionBankItem]:
    _get_chapter_or_404(db, chapter_id)
    query = db.query(QuestionBankItem).filter(QuestionBankItem.chapter_id == chapter_id)
    if difficulty:
        query = query.filter(QuestionBankItem.difficulty == difficulty)
    if type:
        query = query.filter(QuestionBankItem.question_type == type)
    return query.order_by(QuestionBankItem.created_at.desc()).all()


@router.get("/chapters/{chapter_id}/question-bank/sources", response_model=list[str])
def list_question_bank_sources(chapter_id: int, db: Session = Depends(get_db)) -> list[str]:
    _get_chapter_or_404(db, chapter_id)
    rows = (
        db.query(QuestionBankItem.source)
        .filter(QuestionBankItem.chapter_id == chapter_id)
        .distinct()
        .order_by(QuestionBankItem.source)
        .all()
    )
    return [source for (source,) in rows]


@router.delete("/question-bank/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question_bank_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = _get_question_bank_item_or_404(db, item_id)
    db.delete(item)
    db.commit()
