import logging
import time
from typing import Protocol

from sqlalchemy.orm import Session

from backend.app.core.logging import get_logger
from backend.app.models.chunk import Chunk
from backend.app.schemas.search import SearchResult
from backend.app.services import embeddings as embeddings_module
from backend.app.services import search_index
from backend.app.services.vector_store import get_collection

logger = get_logger(__name__)

RRF_K = 60
TEXT_PREVIEW_CHARS = 200


def reciprocal_rank_fusion(ranked_lists: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked_list in ranked_lists:
        for rank, item_id in enumerate(ranked_list, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def _semantic_search(
    db: Session, chapter_id: int, query: str, limit: int
) -> tuple[list[int], dict[int, dict]]:
    vector = embeddings_module.embedding_provider.embed([query])[0]
    result = get_collection().query(
        query_embeddings=[vector],
        n_results=limit,
        where={"chapter_id": chapter_id},
    )
    chroma_ids = result["ids"][0] if result["ids"] else []
    if not chroma_ids:
        return [], {}

    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    chunk_id_by_chroma_id = {
        chunk.chroma_id: chunk.id
        for chunk in db.query(Chunk).filter(Chunk.chroma_id.in_(chroma_ids)).all()
    }

    ranked_ids: list[int] = []
    details: dict[int, dict] = {}
    for chroma_id, chunk_text, metadata in zip(chroma_ids, documents, metadatas):
        chunk_id = chunk_id_by_chroma_id.get(chroma_id)
        if chunk_id is None:
            continue
        ranked_ids.append(chunk_id)
        details[chunk_id] = {
            "document_id": metadata["document_id"],
            "text": chunk_text,
            "material_type": metadata["material_type"],
        }
    return ranked_ids, details


def _keyword_search(
    db: Session, chapter_id: int, query: str, limit: int
) -> tuple[list[int], dict[int, dict]]:
    rows = search_index.keyword_search(db, chapter_id, query, limit)
    ranked_ids = [row["chunk_id"] for row in rows]
    details = {
        row["chunk_id"]: {
            "document_id": row["document_id"],
            "text": row["text"],
            "material_type": row["material_type"],
        }
        for row in rows
    }
    return ranked_ids, details


class Retriever(Protocol):
    def search(self, db: Session, chapter_id: int, query: str, limit: int = 10) -> list[SearchResult]: ...


class HybridRetriever:
    def search(self, db: Session, chapter_id: int, query: str, limit: int = 10) -> list[SearchResult]:
        started_at = time.perf_counter()

        semantic_ids, semantic_details = _semantic_search(db, chapter_id, query, limit)
        keyword_ids, keyword_details = _keyword_search(db, chapter_id, query, limit)

        fused_scores = reciprocal_rank_fusion([semantic_ids, keyword_ids])
        details = {**semantic_details, **keyword_details}

        ranked_chunk_ids = sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)

        results = []
        for chunk_id in ranked_chunk_ids[:limit]:
            detail = details[chunk_id]
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    document_id=detail["document_id"],
                    text=detail["text"],
                    score=fused_scores[chunk_id],
                    material_type=detail["material_type"],
                )
            )

        latency_ms = (time.perf_counter() - started_at) * 1000
        include_full_text = logger.isEnabledFor(logging.DEBUG)
        logger.info(
            "retrieval.result",
            extra={
                "event": "retrieval.result",
                "chapter_id": chapter_id,
                "query": query,
                "limit": limit,
                "result_count": len(results),
                "latency_ms": round(latency_ms, 2),
                "results": [
                    {
                        "chunk_id": result.chunk_id,
                        "document_id": result.document_id,
                        "material_type": result.material_type,
                        "score": result.score,
                        "text_preview": result.text[:TEXT_PREVIEW_CHARS],
                        **({"text": result.text} if include_full_text else {}),
                    }
                    for result in results
                ],
            },
        )
        return results


retriever: Retriever = HybridRetriever()
