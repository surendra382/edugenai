from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.models.chapter import Chapter
from backend.app.models.chunk import Chunk
from backend.app.models.document import Document
from backend.app.models.document_metadata import DocumentMetadata
from backend.app.services import embeddings as embeddings_module
from backend.app.services import search_index
from backend.app.services.chunking import chunk_text
from backend.app.services.vector_store import get_collection


def run_embedding(document_id: int, db: Session) -> None:
    document = db.get(Document, document_id)
    if document is None:
        return

    document.status = "embedding_processing"
    db.commit()

    try:
        text = Path(document.extracted_text_path).read_text(encoding="utf-8")
        chunks = chunk_text(text)
        vectors = embeddings_module.embedding_provider.embed(chunks) if chunks else []
    except Exception as exc:
        document.status = "embedding_failed"
        document.embedding_error = str(exc)
        db.commit()
        return

    chapter = db.get(Chapter, document.chapter_id)
    metadata_row = (
        db.query(DocumentMetadata).filter(DocumentMetadata.document_id == document_id).first()
    )
    difficulty = metadata_row.difficulty if metadata_row else None

    collection = get_collection()
    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        chroma_id = f"document-{document_id}-chunk-{index}"
        chunk_metadata = {
            "document_id": document_id,
            "chapter_id": document.chapter_id,
            "subject_id": chapter.subject_id,
            "material_type": document.material_type,
        }
        if difficulty:
            chunk_metadata["difficulty"] = difficulty
        collection.add(
            ids=[chroma_id], embeddings=[vector], documents=[chunk], metadatas=[chunk_metadata]
        )
        chunk_row = Chunk(document_id=document_id, chunk_index=index, text=chunk, chroma_id=chroma_id)
        db.add(chunk_row)
        db.flush()
        search_index.index_chunk(
            db,
            chunk_id=chunk_row.id,
            document_id=document_id,
            chapter_id=document.chapter_id,
            material_type=document.material_type,
            chunk_text=chunk,
        )

    document.status = "embedded"
    document.embedding_error = None
    db.commit()
