from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.models.chapter import Chapter
from backend.app.models.chunk import Chunk
from backend.app.models.document import Document
from backend.app.models.document_metadata import DocumentMetadata
from backend.app.schemas.chunk import ChunkRead
from backend.app.schemas.document import DocumentRead
from backend.app.schemas.document_metadata import DocumentMetadataRead, DocumentMetadataUpdate
from backend.app.services import search_index
from backend.app.services.embedding_pipeline import run_embedding
from backend.app.services.ocr_pipeline import run_ocr
from backend.app.services.vector_store import get_collection

router = APIRouter(tags=["documents"])

MaterialType = Literal["textbook_page", "worksheet", "sample_paper", "notes", "question_paper"]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PDF_EXTENSIONS = {".pdf"}


def _infer_file_type(filename: str) -> str | None:
    extension = Path(filename).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in PDF_EXTENSIONS:
        return "pdf"
    return None


def _exceeds_max_size(size_bytes: int) -> bool:
    return size_bytes > settings.max_upload_size_mb * 1024 * 1024


def _get_chapter_or_404(db: Session, chapter_id: int) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return chapter


def _get_document_or_404(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _can_retry_ocr(status_value: str) -> bool:
    return status_value == "ocr_failed"


def _can_retry_embedding(status_value: str) -> bool:
    return status_value == "embedding_failed"


def _get_document_metadata_or_404(db: Session, document_id: int) -> DocumentMetadata:
    _get_document_or_404(db, document_id)
    metadata = (
        db.query(DocumentMetadata).filter(DocumentMetadata.document_id == document_id).first()
    )
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return metadata


@router.post(
    "/chapters/{chapter_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    chapter_id: int,
    background_tasks: BackgroundTasks,
    material_type: MaterialType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    chapter = _get_chapter_or_404(db, chapter_id)

    original_filename = file.filename or ""
    file_type = _infer_file_type(original_filename)
    if file_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type of '{original_filename}' is not allowed",
        )

    contents = await file.read()
    if _exceeds_max_size(len(contents)):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb}MB",
        )

    document = Document(
        chapter_id=chapter_id,
        material_type=material_type,
        file_type=file_type,
        original_filename=original_filename,
        storage_path="",
        file_size_bytes=len(contents),
        status="uploaded",
    )
    db.add(document)
    db.flush()
    db.add(DocumentMetadata(document_id=document.id))

    target_dir = (
        Path(settings.knowledge_base_dir)
        / str(chapter.subject_id)
        / str(chapter_id)
        / material_type
    )
    target_path = target_dir / f"{document.id}_{original_filename}"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(contents)
    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store uploaded file",
        ) from exc

    document.storage_path = str(target_path)
    document.status = "ocr_processing"
    db.commit()
    db.refresh(document)

    background_tasks.add_task(run_ocr, document_id=document.id, db=db)
    return document


@router.get("/chapters/{chapter_id}/documents", response_model=list[DocumentRead])
def list_documents(chapter_id: int, db: Session = Depends(get_db)) -> list[Document]:
    _get_chapter_or_404(db, chapter_id)
    return (
        db.query(Document)
        .filter(Document.chapter_id == chapter_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    return _get_document_or_404(db, document_id)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db)) -> None:
    document = _get_document_or_404(db, document_id)
    file_path = Path(document.storage_path)
    if file_path.exists():
        file_path.unlink()

    chunks = db.query(Chunk).filter(Chunk.document_id == document_id).all()
    if chunks:
        get_collection().delete(ids=[chunk.chroma_id for chunk in chunks])
        for chunk in chunks:
            search_index.remove_chunk(db, chunk.id)
            db.delete(chunk)

    metadata = (
        db.query(DocumentMetadata).filter(DocumentMetadata.document_id == document_id).first()
    )
    if metadata is not None:
        db.delete(metadata)

    db.delete(document)
    db.commit()


@router.get("/documents/{document_id}/text")
def get_document_text(document_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    document = _get_document_or_404(db, document_id)
    if not document.extracted_text_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="OCR has not completed successfully for this document",
        )
    text = Path(document.extracted_text_path).read_text(encoding="utf-8")
    return {"text": text}


@router.post(
    "/documents/{document_id}/ocr/retry",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_ocr(
    document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> Document:
    document = _get_document_or_404(db, document_id)
    if not _can_retry_ocr(document.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not in a failed OCR state",
        )

    document.status = "ocr_processing"
    document.ocr_error = None
    db.commit()
    db.refresh(document)

    background_tasks.add_task(run_ocr, document_id=document.id, db=db)
    return document


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkRead])
def list_chunks(document_id: int, db: Session = Depends(get_db)) -> list[Chunk]:
    _get_document_or_404(db, document_id)
    return (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .all()
    )


@router.post(
    "/documents/{document_id}/embeddings/retry",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_embedding(
    document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> Document:
    document = _get_document_or_404(db, document_id)
    if not _can_retry_embedding(document.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not in a failed embedding state",
        )

    document.status = "embedding_processing"
    document.embedding_error = None
    db.commit()
    db.refresh(document)

    background_tasks.add_task(run_embedding, document_id=document.id, db=db)
    return document


@router.get("/documents/{document_id}/metadata", response_model=DocumentMetadataRead)
def get_document_metadata(document_id: int, db: Session = Depends(get_db)) -> DocumentMetadata:
    return _get_document_metadata_or_404(db, document_id)


@router.put("/documents/{document_id}/metadata", response_model=DocumentMetadataRead)
def update_document_metadata(
    document_id: int, payload: DocumentMetadataUpdate, db: Session = Depends(get_db)
) -> DocumentMetadata:
    metadata = _get_document_metadata_or_404(db, document_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(metadata, field, value)
    db.commit()
    db.refresh(metadata)
    return metadata
