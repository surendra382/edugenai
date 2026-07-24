# Feature Tracker

This directory breaks the SRS (`../srs.md`) roadmap into individually shippable
features. Each feature is a **vertical slice** — DB → API → UI → tests — built
and tested end-to-end before moving to the next one.

Workflow: pick one `Not Started` feature, flip it to `In Progress`, implement
it top to bottom per its Test Strategy section, verify manually, flip to
`Done`, commit, move to the next row.

Use `TEMPLATE.md` when adding a new feature file.

---

## Phase 1 — Foundation

| ID  | Feature | Depends on | Status |
|-----|---------|------------|--------|
| F01 | [Core Infrastructure](phase1-f01-core-infrastructure.md) | — | Done |
| F02 | [Subject Management](phase1-f02-subject-management.md) | F01 | Done |
| F03 | [Chapter Management](phase1-f03-chapter-management.md) | F01, F02 | Done |

Auth is explicitly deferred — not part of Phase 1. It resurfaces once the
Student Portal (Phase 4) needs to distinguish admin vs. student roles.

## Phase 2 — Knowledge Base

| ID  | Feature | Depends on | Status |
|-----|---------|------------|--------|
| F01 | [Material Upload & Storage](phase2-f01-material-upload.md) | phase1-f03 | Done |
| F02 | [OCR Processing Pipeline](phase2-f02-ocr-processing.md) | phase2-f01 | Done |
| F03 | [Metadata Management](phase2-f03-metadata-management.md) | phase2-f01 | Done |
| F04 | [Chunking & Embeddings (Vector DB)](phase2-f04-chunking-embeddings.md) | phase2-f02, phase2-f03 | Done |
| F05 | [Hybrid Retrieval & Preview](phase2-f05-hybrid-retrieval.md) | phase2-f04 | Done |

Storage layout decision: all uploaded material and derived artifacts
(OCR text, embeddings) live under `knowledge_base/{subject_id}/{chapter_id}/...`,
keyed by ID rather than name so renames never break file paths. The
top-level `storage/` folder is reserved/unused for now — out of Phase 2's
scope.

Every OCR/embedding provider is built behind a swappable interface with a
stub implementation for tests, so CI never depends on a real OCR engine or
embedding model — only the "Manual Verification" checklist items exercise
the real PaddleOCR/Tesseract/BGE stack.

## Phase 3 — AI Question Generator

| ID  | Feature | Depends on | Status |
|-----|---------|------------|--------|
| F01 | [LLM Provider Integration (Groq)](phase3-f01-llm-integration.md) | — | Done |
| F02 | [Prompt Builder & Question Generation Engine](phase3-f02-question-generation.md) | phase3-f01, phase2-f05 | Done |
| F03 | [Answer Key Generation](phase3-f03-answer-key.md) | phase3-f02 | Done |
| F04 | [Admin "Generate Practice Paper" UI](phase3-f04-admin-question-generator-ui.md) | phase3-f03 | Done |

LLM backend decision: Groq's hosted API (OpenAI-compatible `chat/completions`,
default model `llama-3.3-70b-versatile`) rather than local Ollama — avoids a
multi-GB model download and local inference cost, fits the project's
cost-conscious stance via Groq's free tier. Built behind a swappable
`LLMProvider` interface, same pattern as `EmbeddingProvider`/`OCRProvider`,
so a local Ollama provider could be added later without touching callers.

Generated practice papers are persisted (`QuestionSet`/`Question` tables) via
a `BackgroundTask` pipeline mirroring Phase 2's OCR/embedding pipeline, rather
than generated statelessly — this also seeds the "session history" need
called out for Phase 4.

## Phase 4 — Student Portal

| ID  | Feature | Depends on | Status |
|-----|---------|------------|--------|
| F01 | [Student "Generate Practice Paper" UI](phase4-f01-student-practice-paper-ui.md) | phase3-f03 | Done |
| F02 | [PDF Export](phase4-f02-pdf-export.md) | phase4-f01, phase3-f03 | Done |
| F03 | [Practice Paper History](phase4-f03-practice-paper-history.md) | phase4-f01 | Done |

Standing decision: Phase 4 does **not** add authentication. The Phase 1
note above anticipated auth "resurfacing" here, but the SRS roadmap (§18)
scopes Authentication to Phase 5, and CLAUDE.md says not to add auth checks
unless a feature doc calls for it — so admin vs. student stays a purely
navigational split (separate pages, grouped links on the landing page),
with no login, credentials, or session/user identity. This also means
Practice Paper History (F03) is one shared history, not per-student —
real per-user separation arrives once Phase 5 adds real accounts.

## Phase 5 — Enhancements

| ID  | Feature | Depends on | Status |
|-----|---------|------------|--------|
| F01 | [Multi-Chapter Practice Paper Generation](phase5-f01-multi-chapter-paper-generation.md) | phase3-f02, phase3-f03, phase4-f01, phase4-f02, phase4-f03 | In Progress |
| F02 | [Observability & Structured Logging](phase5-f02-observability-logging.md) | phase2-f05, phase3-f01, phase3-f02 | In Progress |

Not part of the original SRS roadmap (§18), which numbers "Deployment &
Production" as Phase 5 — that phase is renumbered to Phase 6 below. This
phase holds mid-project enhancements to the Phase 3/4 generation flow that
came up after Phase 4 shipped, sequenced ahead of deployment since they
change the API contract deployment would otherwise need to carry forward.

F02 adds logging (final prompt text, LLM token usage, retrieved chunks, and
full-traceback error logging) using only the Python stdlib (`logging`,
`contextvars`) — no new dependency — consistent with the project's
avoid-paid/heavy-services stance already applied to the LLM/OCR/vector-DB
choices.

## Phase 6 — Deployment & Production
_Not broken down yet._
