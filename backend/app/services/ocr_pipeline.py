from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.chapter import Chapter
from backend.app.models.document import Document
from backend.app.services import ocr as ocr_module
from backend.app.services.embedding_pipeline import run_embedding


def run_ocr(document_id: int, db: Session) -> None:
    document = db.get(Document, document_id)
    if document is None:
        return

    try:
        text = ocr_module.ocr_provider.extract_text(
            Path(document.storage_path), document.file_type
        )
    except Exception as exc:  # OCR engines fail on real-world corrupt/unreadable files
        document.status = "ocr_failed"
        document.ocr_error = str(exc)
        db.commit()
        return

    text_path = _extracted_text_path(document, db)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")

    document.extracted_text_path = str(text_path)
    document.status = "ocr_done"
    document.ocr_error = None
    db.commit()

    run_embedding(document_id=document.id, db=db)


def _extracted_text_path(document: Document, db: Session) -> Path:
    chapter = db.get(Chapter, document.chapter_id)
    return (
        Path(settings.knowledge_base_dir)
        / str(chapter.subject_id)
        / str(document.chapter_id)
        / "extracted_text"
        / f"{document.id}.txt"
    )
