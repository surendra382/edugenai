from sqlalchemy import text
from sqlalchemy.orm import Session


def index_chunk(
    db: Session,
    *,
    chunk_id: int,
    document_id: int,
    chapter_id: int,
    material_type: str,
    chunk_text: str,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO chunks_fts (rowid, text, chunk_id, document_id, chapter_id, material_type)
            VALUES (:rowid, :text, :chunk_id, :document_id, :chapter_id, :material_type)
            """
        ),
        {
            "rowid": chunk_id,
            "text": chunk_text,
            "chunk_id": chunk_id,
            "document_id": document_id,
            "chapter_id": chapter_id,
            "material_type": material_type,
        },
    )


def remove_chunk(db: Session, chunk_id: int) -> None:
    db.execute(text("DELETE FROM chunks_fts WHERE rowid = :rowid"), {"rowid": chunk_id})


def keyword_search(db: Session, chapter_id: int, query: str, limit: int) -> list[dict]:
    phrase = query.replace('"', '""')
    rows = db.execute(
        text(
            """
            SELECT chunk_id, document_id, text, material_type
            FROM chunks_fts
            WHERE chunks_fts MATCH :match_query AND chapter_id = :chapter_id
            ORDER BY rank
            LIMIT :limit
            """
        ),
        {"match_query": f'"{phrase}"', "chapter_id": chapter_id, "limit": limit},
    ).all()
    return [
        {
            "chunk_id": row.chunk_id,
            "document_id": row.document_id,
            "text": row.text,
            "material_type": row.material_type,
        }
        for row in rows
    ]
