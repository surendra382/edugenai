# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State

**Pre-implementation.** The repository currently contains only folder scaffolding
(`backend/`, `frontend/`, `configs/`, `data/`, `knowledge_base/`, `requirements/`,
`scripts/`, `storage/`, `tests/`) and planning docs — no application code exists
yet. There are no build/lint/test commands to run until Feature F01 (see below)
lands and populates `requirements/`.

## Source of Truth

Before making any implementation decision, read:

- **`docs/srs.md`** — the full Software Requirements Specification: vision,
  functional requirements, architecture, tech stack, and phased roadmap.
- **`docs/features/README.md`** — the feature tracker. Each SRS phase is broken
  into individual features, one markdown file per feature, each with its own
  Status field.
- **`docs/features/phase*-f*.md`** — one file per feature: goal, in/out of
  scope, data model, API contract, UI behavior, test strategy, and acceptance
  criteria. Treat the API contract and data model sections as the spec to
  implement against, not a suggestion.
- **`docs/features/TEMPLATE.md`** — the required structure for any new feature
  doc added for later phases.

## Development Methodology

This project is built **one feature at a time, as vertical slices** — DB model
→ API endpoint → UI page → tests, all for one feature, before starting the
next. Do not build a layer (e.g. "all the DB models") across multiple features
at once. Workflow per the tracker:

1. Pick the next `Not Started` feature in `docs/features/README.md`.
2. Flip its status to `In Progress`.
3. Implement it end-to-end per its feature doc, including the tests listed
   under that doc's "Test Strategy" section.
4. Verify manually against that doc's "Manual Verification" checklist.
5. Flip status to `Done` and move to the next feature.

Auth is intentionally deferred past Phase 1 — do not add login/auth checks
unless the feature doc being implemented calls for it.

## Planned Architecture (per `docs/srs.md`)

```
Streamlit UI  →  FastAPI backend  →  Question Generator → Prompt Builder → Retriever
                                                                    │
                                                       ┌────────────┴────────────┐
                                                  Knowledge Base            Web Search
                                                (Chroma vector DB,         (optional)
                                                 OCR text, SQLite
                                                 metadata, local storage)
                                                                    │
                                                               Ollama LLM
```

Planned tech stack (v1, cost-conscious — avoid paid services like Azure OpenAI,
Pinecone, paid OCR/DB APIs):

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Backend | FastAPI |
| LLM | Ollama (Qwen / Gemma / Llama) |
| OCR | PaddleOCR + Tesseract |
| Vector DB | Chroma |
| Embeddings | BAAI BGE / Nomic Embed |
| Metadata DB | SQLite |
| Storage | Local filesystem |
| Search | DuckDuckGo / Tavily Free |

The architecture is required to stay modular — every major component (OCR,
retrieval, LLM, search, storage) should be replaceable behind an interface
without touching the rest of the system, to allow migrating to paid cloud
services later.

## Key Standing Decisions

These were made while scoping Phase 1 features and apply project-wide unless
a specific feature doc overrides them:

- **Delete semantics are block, not cascade.** Deleting a Subject with
  existing Chapters (and, later, deleting a Chapter with knowledge-base
  content) returns `409` rather than cascading — avoids silent loss of
  uploaded material.
- **Uniqueness is scoped to parent.** Chapter names are unique within their
  Subject, not globally (two subjects may each have a "Chapter 1").
- **Knowledge priority order** for question generation (per SRS §5): uploaded
  knowledge base > LLM general knowledge (bounded to the selected chapter) >
  optional internet search (style/trends only, never syllabus scope).
