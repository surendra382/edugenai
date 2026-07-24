# Feature: Hybrid Retrieval & Preview

**Phase:** 2 — Knowledge Base
**ID:** phase2-f05
**Status:** Done
**Depends on:** phase2-f04

---

## 1. Goal

Admin can query a chapter's knowledge base with combined semantic +
keyword search and get back ranked, relevant chunks — closing out Phase 2
with the retrieval interface Phase 3's Question Generator will consume.

## 2. Scope

### In Scope
- `Retriever` component behind a swappable interface: combines Chroma
  semantic search (vector similarity, from phase2-f04) with a keyword
  search over `Chunk.text` (SQLite FTS5 virtual table), merged via
  reciprocal-rank fusion
- `chunks_fts` FTS5 virtual table, kept in sync whenever phase2-f04
  inserts a `Chunk` row
- An admin-facing HTTP endpoint scoped to a chapter. Phase 3 will call the
  same `Retriever` interface directly in-process — this endpoint is for
  admin preview/debugging, not necessarily the path Phase 3 uses in
  production
- Admin UI: a "Preview Documents" page — pick a chapter, enter a test
  query, see ranked results with source document and snippet

### Out of Scope
- Question generation itself (Phase 3)
- Cross-chapter or cross-subject search
- LLM-based result re-ranking (future enhancement)

## 3. Data Model

No new SQLAlchemy models. Adds a `chunks_fts` SQLite FTS5 virtual table
indexing `Chunk.text`, populated/updated alongside `Chunk` inserts.

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| GET | `/chapters/{chapter_id}/search?q=...&limit=10` | — | `200` SearchResult[] | 404 if chapter missing; each result: `{chunk_id, document_id, text, score, material_type}` |

## 5. UI Behavior

- `frontend/pages/admin_preview.py`
- Subject picker → Chapter picker (same cascading pattern as other admin
  pages) → search box → "Search" button
- Results list: snippet, source document filename, material type, score
- Empty state: "No results — try a different query, or confirm this
  chapter has embedded material"

## 6. Test Strategy

### Unit Tests
- Fusion ranking combines semantic + keyword scores deterministically for
  a fixed stub input

### Integration Tests
- Search returns keyword-only matches even when semantic scores are
  stubbed to zero (proves the keyword path works independently)
- Search returns semantic-only matches for a paraphrased query with no
  keyword overlap (stub embeddings crafted to be "close")
- Search scoped to a chapter with no embedded chunks → `200`, empty list
- Search on a nonexistent chapter → 404

### Manual Verification
- [x] Query a real embedded chapter with an exact phrase, confirm a
      keyword match appears
- [x] Query with a paraphrase (no exact words in common), confirm a
      semantic match still surfaces relevant chunks
- [x] Confirm result snippets correctly link back to a real, viewable
      source document

## 7. Acceptance Criteria

- [x] All integration tests above pass
- [x] "Preview Documents" page usable end-to-end from the Streamlit UI,
      ready for Phase 3 to build on
