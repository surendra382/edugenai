# Feature: Question Bank — Structured Extraction & Storage

**Phase:** 5 — Enhancements
**ID:** phase5-f03
**Status:** In Progress
**Depends on:** phase1-f03, phase3-f02

---

## 0. Why This Feature

The generation flow shipped in Phase 3/4 produces low-quality papers: generic,
below the requested difficulty, off-topic, and in the wrong locale (`$` instead
of `₹`). Root-cause analysis showed the RAG stack is the wrong tool for this
problem, on two counts:

- **Vector retrieval adds no value here.** The generation "query" is always a
  set of exact categorical facets (class, subject, chapter, difficulty), which
  is a plain relational filter — not a fuzzy semantic search. The Chroma /
  embedding layer contributed no benefit and was in fact the source of the
  silent "no material retrieved → hallucinated questions" bug (a document could
  be OCR'd but never embedded, and generation fell back to ungrounded LLM
  knowledge without warning).
- **Character-based OCR + chunking destroys the input.** The uploaded material
  is *question papers* — dense with math notation, options, and answer keys.
  Tesseract-class OCR mangles the math, and fixed-size chunking slices questions
  mid-item, so no coherent question survives to steer generation.

The fix is to stop treating uploads as prose to embed, and instead treat each
uploaded question as a **first-class, structured record**. A multimodal model
(Gemini) reads an image and returns each question as structured data —
stem, options, answer, type, concept, difficulty — which we store in a simple
relational table alongside user-supplied facets (class, subject/chapter,
source). Later features query this table by exact filters to assemble
level-matched few-shot examples for generation.

**Scope expanded during implementation.** The original plan was to ship
ingest → structured extraction → store → review as a first, testable slice,
leaving the old OCR/chunking/embedding/Chroma pipeline in place and deferring
generation-side use of the bank to a follow-up feature. That was reconsidered
before implementation: running two ingestion paths side by side (one for
prose, one for structured questions) would leave admins guessing which
upload flow to use, and the old pipeline's problems described above are
architectural, not tunable. This feature therefore **fully replaces** the old
pipeline in one cutover, including wiring generation to read exemplars from
the bank — see §5a below. `phase2-f01`, `phase2-f02`, `phase2-f03`,
`phase2-f04`, and `phase2-f05` are superseded by this feature (each carries a
note pointing here); `phase3-f02`'s retrieval mechanism is updated, its
prompt/LLM/parsing stages are unchanged.

## 1. Goal

An admin can upload one or more images of a question paper, tag the batch with
its class / subject / chapter / source, and have the system extract each
question into a structured **Question Bank** table (question, concept, type,
options, answer, difficulty) that can be listed and reviewed. No vector store,
no chunking.

## 2. Scope

### In Scope

- **`QuestionBankItem` table** — one row per extracted question.
- **`question_extractor`** — a `VisionExtractor` interface with a Gemini
  implementation that reads an image and returns a list of structured questions
  (strict JSON schema, see §4). Behind an interface + stub, matching the
  existing `LLMProvider` / `OCRProvider` pattern so tests never hit the network.
- **Import API** — upload N images plus batch-level facts (subject/chapter,
  class, source); extract and persist rows; report per-image counts and errors.
- **Review API** — list stored questions (filterable) and delete a bad row, so
  extraction quality can be verified before building generation on top.
- **Generation cutover** — `generation_pipeline.py` reads exemplar questions
  from `QuestionBankItem` (chapter + difficulty match, backfilled) instead of
  `HybridRetriever`/Chroma. See §5a.
- **Removal of the old pipeline** — `Document`/`Chunk`/`DocumentMetadata`
  models, OCR (Tesseract + Gemini-as-OCR), chunking, embeddings, Chroma, the
  FTS5 keyword index, and the `/chapters/{id}/search` debug endpoint are all
  deleted, not left in place.

### Out of Scope

- Rich admin editing (bulk edit, re-tagging, difficulty re-scoring) beyond
  create/list/delete — a later enhancement.
- De-duplication of questions across imports.
- Auto-mapping to chapters the admin hasn't created (chapter must exist).

## 3. Data Model

One new table. `subject` is reached through `chapter_id` (chapters already carry
`subject_id`), so it isn't stored redundantly. Batch-level facts (`class_grade`,
`source`) are supplied by the admin at import time; the rest are extracted by
the model.

```
QuestionBankItem
  id             INTEGER PK
  chapter_id     INTEGER FK -> chapters.id NOT NULL   -- admin-supplied (implies subject)
  class_grade    TEXT NOT NULL         -- admin-supplied, e.g. "8"
  source         TEXT NOT NULL         -- admin-supplied: sainik | olympiad | cbse_textbook | unknown | <free text>
  question_type  TEXT NOT NULL         -- extracted: mcq | true_false | short_answer | numerical | fill_blank
  stem           TEXT NOT NULL         -- extracted: the question text (math as plain/unicode, not LaTeX)
  concept        TEXT NULL             -- extracted: concept/sub-skill the question tests
  options        TEXT NULL             -- extracted: JSON-encoded list[str]; required for mcq, else NULL
  answer         TEXT NULL             -- extracted: correct option text / value, when present in source
  difficulty     TEXT NOT NULL         -- extracted: easy | medium | hard
  source_image   TEXT NULL             -- provenance: original filename / stored path
  created_at     DATETIME

  INDEX (chapter_id, difficulty, question_type)
```

Field ownership:

| Field | Provided by |
|---|---|
| `chapter_id`, `class_grade`, `source` | Admin, once per import batch |
| `question_type`, `stem`, `concept`, `options`, `answer`, `difficulty` | Model, per question |

`difficulty` is a bucketed enum for now; a numeric score can be added later if
tagging needs finer calibration (deliberately omitted to keep this slice small).

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/chapters/{chapter_id}/question-bank/import` | multipart: `images[]` (jpg/jpeg/png **or pdf**) + `class_grade`, `source` | `201` `{created: int, items: QuestionBankItemRead[], errors: [{filename, error}]}` | 404 if chapter missing; a PDF is split into pages (`pdf2image`/poppler) and each page is extracted as its own image, so one PDF containing a whole chapter's paper works in a single upload; per-page failures reported as `{filename, error}` with the filename labeled `"<name> (page N)"`, not fatal to the rest of the file |
| GET | `/chapters/{chapter_id}/question-bank` | — (query: `difficulty`, `type`) | `200` `QuestionBankItemRead[]` | Review/verify extraction; 404 if chapter missing |
| DELETE | `/question-bank/{id}` | — | `204` | Remove a mis-extracted row; 404 if missing |

Extraction (one Gemini call per page) runs with bounded concurrency
(`asyncio.to_thread` + a semaphore capped at 4 concurrent calls, in
`api/question_bank.py`) rather than one page at a time — a whole scanned
chapter as a single multi-page PDF would otherwise take one Gemini
round-trip's latency *times* the page count, both slow for the admin and
blocking to every other request on the server in the meantime, since a
synchronous call inside an `async def` route holds the event loop.

**Extraction contract (model → JSON).** The extractor prompts Gemini to return
**only** a JSON array; each element:

```json
{
  "question_type": "mcq | true_false | short_answer | numerical | fill_blank",
  "stem": "question text, math in plain/unicode (sqrt(16), x^2, ×, ÷, ₹) — never LaTeX/backslashes",
  "concept": "short concept/sub-skill label, e.g. 'square root by prime factorisation'",
  "options": ["opt A text", "opt B text", "..."],   // omit or null unless mcq
  "answer": "correct option text or value, or null if not shown in the image",
  "difficulty": "easy | medium | hard"
}
```

Parsing reuses the strictness style of the existing `question_parser`: reject
non-JSON, unknown `question_type`, and `mcq` items with fewer than 2 options;
tolerate a missing `answer` (source may not print a key).

## 5a. Generation Cutover

`generation_pipeline.py`'s per-chapter retrieval stage no longer calls
`HybridRetriever.search()`. It queries `QuestionBankItem` filtered by
`chapter_id`, preferring rows matching the requested `difficulty` and
backfilling with other difficulties for that chapter if there aren't enough
(target ~8, matching the old chunk `limit`). Each exemplar is formatted as
`[difficulty] (type) stem` (+ options/answer if present) and passed into
`prompt_builder.build_prompt`'s existing `context_chunks: list[str]`
parameter — no signature change, since that function was already decoupled
from any chunk/retriever-specific type. The prompt's context framing was
reworded to describe these as real exemplar exam questions to draw
style/difficulty from without copying verbatim, rather than "textbook/notes
material." A chapter with no imported questions still falls back to the
existing bounded-general-knowledge prompt branch. A `question_bank.lookup`
structured log event (chapter_id, result_count, difficulty breakdown)
replaces the old `retrieval.result` event at this point in the pipeline.

## 5b. UI Behavior

**Admin → Question Bank (new page, replaces the old Knowledge Base + Preview pages):**

- **Import form:** pick chapter, enter class, enter source, upload one or
  more images → submit. On completion, show `created` count and any per-image
  errors.
- **Review table:** stem (truncated), type, concept, difficulty, source; delete
  action per row. Filter by difficulty / type.
- Empty state: "No questions imported yet for this chapter."

Student flow: unchanged (still generates a paper the same way; only the
context source behind that generation changed, per §5a).

## 6. Test Strategy

### Unit Tests

- `question_extractor` parsing: valid JSON array → list of items; MCQ item keeps
  `options`; non-MCQ → `options` NULL; missing `answer` tolerated; invalid JSON,
  unknown `question_type`, and MCQ with <2 options rejected.
- Import handler maps batch facts (`chapter_id`, `class_grade`, `source`) onto
  every extracted row; math in `stem` is stored as given (no LaTeX).

### Integration Tests

- `POST .../question-bank/import` with a `StubVisionExtractor` returning two
  questions → `201`, `created=2`, rows visible via `GET`.
- One image extracts cleanly, a second raises → `created` counts the good rows,
  `errors` lists the bad image, request still `201`.
- Import to a nonexistent chapter → `404`.
- `GET` with `difficulty=hard` filters correctly.
- `DELETE /question-bank/{id}` removes the row; deleting a missing id → `404`.
- A question-set generation run against a chapter with imported
  `QuestionBankItem` rows completes using exemplar-derived context (§5a).
- Deleting a chapter with existing `QuestionBankItem` rows returns `409`
  (preserves the block-not-cascade standing decision, now checked against
  the new table instead of `Document`).

### Manual Verification

- [ ] Import a real Sainik/Olympiad question-paper image with Gemini; confirm
      each printed question becomes one row with correct type, options, answer,
      and a sane difficulty/concept tag, and that ₹ and math survive intact.
- [ ] Import a multi-question page (e.g. 10 MCQs) → 10 rows, none merged or
      split mid-question.

## 7. Acceptance Criteria

- [ ] Uploading question-paper images with admin-supplied class/subject/source
      produces one structured `QuestionBankItem` per question, stored in SQLite
      with no vector store or chunking involved.
- [ ] Extracted math and currency are preserved (plain/unicode, `₹`), and MCQ
      options/answers are captured when present in the source.
- [ ] Stored questions are listable and deletable for review.
- [ ] Question generation draws exemplar context from `QuestionBankItem`
      instead of vector/keyword retrieval, with a general-knowledge fallback
      when a chapter has no imported questions.
- [ ] The old OCR/chunking/embedding/Chroma pipeline and its API/UI surface
      are fully removed, not left dormant alongside the new path.
- [ ] All unit and integration tests pass with the stub extractor; the manual
      checklist is verified against a real Gemini key.
