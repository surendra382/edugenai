# Feature: Chunking & Embeddings (Vector DB)

**Phase:** 2 — Knowledge Base
**ID:** phase2-f04
**Status:** Done
**Depends on:** phase2-f02, phase2-f03

---

> **Superseded by [phase5-f03](phase5-f03-exemplar-bank-difficulty-tagging.md).**
> Chunking, embeddings, and Chroma have been removed entirely — question
> generation now reads structured `QuestionBankItem` exemplars directly by
> chapter/difficulty instead of chunk-level vector search. This doc is kept
> for historical reference only.

## 1. Goal

OCR'd document text is automatically chunked, embedded, and indexed into
a Chroma vector database — tagged with subject/chapter/document metadata
— with no manual intervention required, per SRS Module 5.

## 2. Scope

### In Scope
- Triggered automatically as a `BackgroundTask` when a document reaches
  `ocr_done` (chains off phase2-f02's OCR completion)
- Chunking: fixed-size sliding-window over the extracted text (~500
  characters, ~50-character overlap) — simple and deterministic; strategy
  lives behind a plain function so it's easy to swap later
- Embedding provider behind a swappable `EmbeddingProvider` interface,
  default implementation using a local BGE/Nomic Embed model via
  `sentence-transformers`
- Chroma persistent client at `knowledge_base/.chroma/`, single collection
  (`knowledge_base`); each chunk stored with metadata
  `{document_id, chapter_id, subject_id, material_type, difficulty}`
  (`difficulty` pulled from phase2-f03's metadata if set, else omitted)
- `Chunk` table mirrors what's in Chroma for traceability/debugging and
  to back the keyword-search side of phase2-f05
- `Document.status` extended with `embedding_processing`, `embedded`,
  `embedding_failed`
- Retry endpoint for a document stuck in `embedding_failed`

### Out of Scope
- Hybrid retrieval / querying (phase2-f05)
- Chunk-size tuning per material type
- Re-embedding automatically when a document's metadata changes after the
  fact — retry is manual only in v1

## 3. Data Model

```
Chunk
  id            INTEGER PK
  document_id   INTEGER FK -> Document.id NOT NULL
  chunk_index   INTEGER NOT NULL
  text          TEXT NOT NULL
  chroma_id     TEXT UNIQUE NOT NULL   -- id used in the Chroma collection
  created_at    DATETIME

  UNIQUE(document_id, chunk_index)

Document (extended)
  status            TEXT   -- add: embedding_processing | embedded | embedding_failed
  embedding_error   TEXT NULL
```

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| GET | `/documents/{id}/chunks` | — | `200` Chunk[] | 404 if missing; empty list if not yet embedded |
| POST | `/documents/{id}/embeddings/retry` | — | `202` Document | 404 if missing; 409 if not currently `embedding_failed` |

## 5. UI Behavior

- `admin_knowledge_base.py`: status badge extends to show
  `embedding_processing` / `embedded` / `embedding_failed`
- "View Chunks" expander once `embedded` (chunk count + first ~100 chars
  of each chunk)
- "Retry Embedding" button on `embedding_failed`, showing `embedding_error`

## 6. Test Strategy

### Unit Tests
- Chunking function splits a sample text into the expected chunk
  count/boundaries for a given size + overlap
- `EmbeddingProvider` interface: a stub implementation returns
  deterministic fixed-length vectors for tests (no real model loaded in CI)

### Integration Tests
- A document reaching `ocr_done` triggers embedding (stub OCR + stub
  embeddings) → status eventually `embedded`,
  `GET /documents/{id}/chunks` returns the expected chunks
- Simulated embedding failure → status `embedding_failed`,
  `embedding_error` populated
- Retry on a failed embedding → recovers to `embedded` (stub succeeds on
  retry)
- Retry on a document not in `embedding_failed` → 409
- The Chroma collection contains one vector per chunk with the correct
  `document_id`/`chapter_id`/`subject_id` metadata

### Manual Verification
- [x] Upload and OCR a real document, confirm it progresses to `embedded`
      automatically
- [x] Inspect the Chroma collection (via the chunks endpoint or a small
      script) and confirm vectors + metadata are present
- [x] Force and then retry an embedding failure, confirm recovery

## 7. Acceptance Criteria

- [x] All integration tests pass using stub providers
- [x] The real embedding model is wired as default and manually verified
      once end-to-end (upload → OCR → embed)
