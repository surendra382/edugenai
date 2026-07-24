# Feature: OCR Processing Pipeline

**Phase:** 2 — Knowledge Base
**ID:** phase2-f02
**Status:** Done
**Depends on:** phase2-f01

---

## 1. Goal

Every uploaded image/PDF is automatically OCR'd after upload. Extracted
text is stored and viewable per document; failures are visible and
retryable. The original file is always preserved untouched.

## 2. Scope

### In Scope
- OCR runs as a FastAPI `BackgroundTask` kicked off right after a
  successful upload — no separate job queue/worker process yet (that's a
  Phase 5 concern if throughput ever requires it)
- OCR engine sits behind a swappable `OCRProvider` interface (per
  CLAUDE.md's modularity requirement), with a default implementation
  backed by PaddleOCR (images) + Tesseract (PDF pages via
  pdf2image → per-page OCR)
- Extracted text persisted to disk at
  `knowledge_base/{subject_id}/{chapter_id}/extracted_text/{document_id}.txt`
- `Document.status` extended with `ocr_processing`, `ocr_done`,
  `ocr_failed`
- Retry endpoint for a document stuck in `ocr_failed`
- Admin UI: live status per document, extracted text preview, retry button

### Out of Scope
- Chunking / embeddings (phase2-f04)
- Manual correction/editing of extracted text (structured metadata editing
  is phase2-f03; raw OCR-text editing is a future enhancement)
- PDF extraction quality tuning beyond a basic per-page OCR loop

## 3. Data Model

```
Document (extended)
  status               TEXT   -- add: ocr_processing | ocr_done | ocr_failed
  extracted_text_path  TEXT NULL
  ocr_error            TEXT NULL   -- last failure reason; cleared on retry
```

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| GET | `/documents/{id}/text` | — | `200 {text: str}` | 404 if document missing; 409 if OCR not yet `ocr_done` |
| POST | `/documents/{id}/ocr/retry` | — | `202` Document | 404 if missing; 409 if not currently `ocr_failed` |

The phase2-f01 upload endpoint's request/response shape is unchanged; it
now additionally schedules OCR as a background task and returns `201`
immediately with `status=ocr_processing`.

## 5. UI Behavior

- `admin_knowledge_base.py` extended:
  - Status column becomes live: `uploaded` → `ocr_processing` →
    `ocr_done` / `ocr_failed`
  - "View Text" expander per `ocr_done` row showing the extracted text
  - "Retry OCR" button per `ocr_failed` row, showing `ocr_error`
  - A manual "Refresh" button re-fetches document status (Streamlit has
    no background polling in this v1 — documented limitation, not a bug)

## 6. Test Strategy

### Unit Tests
- `OCRProvider` interface: a stub implementation is used in tests (no real
  OCR engine in CI) — verifies pipeline wiring, not OCR accuracy
- Retry is rejected when the document is not in `ocr_failed`

### Integration Tests
- Upload triggers OCR (via the stub provider) → status eventually
  `ocr_done`, `GET /documents/{id}/text` returns the stub's extracted text
- Simulated OCR failure → status `ocr_failed`, `ocr_error` populated
- Retry on a failed document → status cycles back through
  `ocr_processing` to `ocr_done` (stub succeeds on retry)
- Retry on a document not in `ocr_failed` → 409
- `GET /documents/{id}/text` before OCR completes → 409

### Manual Verification
- [x] Upload a real textbook-page image, confirm status progresses to
      `ocr_done` and the extracted text is readable
- [x] Upload a file that fails OCR (e.g. a corrupt image), confirm
      `ocr_failed` with a useful error message
- [x] Retry a failed OCR, confirm it recovers (or fails again cleanly)
- [x] Confirm the original file is still present/downloadable after OCR runs

## 7. Acceptance Criteria

- [x] All integration tests pass using the stub OCR provider
- [x] The real PaddleOCR/Tesseract provider is wired as the default and
      manually verified at least once end-to-end
