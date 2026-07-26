# Feature: Prompt Builder & Question Generation Engine

**Phase:** 3 — AI Question Generator
**ID:** phase3-f02
**Status:** Done
**Depends on:** phase3-f01, phase2-f05

---

> **Retrieval mechanism updated by [phase5-f03](phase5-f03-exemplar-bank-difficulty-tagging.md).**
> The generation flow described below is otherwise unchanged (prompt
> builder → LLM → question parser), but its context source is no longer
> `HybridRetriever`/Chroma chunk search — it now queries `QuestionBankItem`
> directly for difficulty-matched exemplar questions per chapter. Any
> mention of "retrieved chunks"/"uploaded material" below should be read as
> "question bank exemplars."

## 1. Goal

Given a chapter, difficulty, question types, and a question count, the
system generates a fresh practice paper — combining retrieved knowledge-base
context with the LLM's own bounded general knowledge, per SRS §5/§6 — and
persists it so it can be polled and reviewed, per SRS Modules 6–8.

## 2. Scope

### In Scope
- `QuestionSet` + `Question` tables
- `prompt_builder.build_prompt(...)`: constructs the generation prompt —
  uploaded context first (retrieved via the existing `HybridRetriever`),
  falling back to general knowledge explicitly bounded to the named
  chapter/subject when no context is available; instructs the model to
  respond with a JSON array only
- `question_parser.parse_questions(...)`: strict parsing/validation of the
  model's JSON response (type, text, options-only-for-mcq, exact count)
- `generation_pipeline.run_generation(question_set_id, db)`: orchestrates
  retrieval → prompt → LLM call → parse → persist, as a `BackgroundTask`,
  mirroring the OCR/embedding pipeline's status-machine pattern
- API: create (dispatch), list (history), get, list questions, retry

### Out of Scope
- Answer key generation (phase3-f03)
- Admin UI (phase3-f04)
- Chunk-diversity-aware retrieval (v1 uses the chapter name as a single
  topical query, top 8 chunks — a documented simplification)
- Cross-question deduplication against prior sets

## 3. Data Model

```
QuestionSet
  id                INTEGER PK
  chapter_id        INTEGER FK -> chapters.id NOT NULL
  difficulty        TEXT NOT NULL          -- easy | medium | hard
  question_types    TEXT NOT NULL          -- comma-joined, e.g. "mcq,short_answer"
  num_questions     INTEGER NOT NULL
  status            TEXT NOT NULL DEFAULT 'generating'  -- generating | completed | failed
  generation_error  TEXT NULL
  created_at        DATETIME
  updated_at        DATETIME

Question
  id                INTEGER PK
  question_set_id   INTEGER FK -> question_sets.id NOT NULL
  question_index    INTEGER NOT NULL
  question_type     TEXT NOT NULL         -- mcq | fill_blank | true_false | short_answer | long_answer | numerical
  text              TEXT NOT NULL
  options           TEXT NULL             -- JSON-encoded list[str], mcq only
  created_at        DATETIME

  UNIQUE(question_set_id, question_index)
```

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/chapters/{chapter_id}/question-sets` | `{difficulty, question_types: [...], num_questions}` | `202` `QuestionSetRead` | 404 if chapter missing; creates row `status="generating"`, dispatches background generation |
| GET | `/chapters/{chapter_id}/question-sets` | — | `200` `QuestionSetRead[]` | Newest first; 404 if chapter missing |
| GET | `/question-sets/{id}` | — | `200` `QuestionSetRead` | 404 if missing |
| GET | `/question-sets/{id}/questions` | — | `200` `QuestionRead[]` | Empty list until `completed` |
| POST | `/question-sets/{id}/retry` | — | `202` `QuestionSetRead` | 409 if not `failed`; re-dispatches generation |

## 5. UI Behavior

None yet — phase3-f04 adds the admin-facing generator page.

## 6. Test Strategy

### Unit Tests
- `build_prompt` includes the requested difficulty, question types, and
  chapter name; includes an explicit "use general knowledge bounded to this
  chapter" note when `context_chunks=[]`
- `parse_questions` accepts valid JSON (with and without ```` ``` ```` code
  fences); rejects invalid JSON; rejects an unknown `type`; rejects an
  `mcq` item with fewer than 2 options; rejects a parsed count that doesn't
  match `expect_count`

### Integration Tests
- `POST .../question-sets` with a `StubLLMProvider` returning a valid JSON
  array → set eventually `completed`, `GET .../questions` returns the
  expected rows in order
- Malformed LLM output → `status="failed"`, `generation_error` populated
- Retry on a failed set (stub swapped to valid output) → recovers to
  `completed`
- Retry on a set not in `failed` → `409`
- Generate on a nonexistent chapter → `404`
- `GET /question-sets/999` → `404`

### Manual Verification
- [x] Generated against "Mathematics / Rational Numbers" with no embedded
      material (empty knowledge base) using a real `GROQ_API_KEY`: 4
      questions (2 mcq, 2 short_answer) at "easy" difficulty came back
      on-topic and correct, confirming the general-knowledge fallback stays
      bounded to the chapter without any uploaded context
- [ ] Generate against a chapter that *does* have embedded material,
      confirm the retrieved context visibly shapes the questions (not yet
      exercised — no embedded documents in this environment yet)

## 7. Acceptance Criteria

- [x] All integration tests pass using the stub LLM provider
- [x] Verified against the real Groq API (see above); the embedded-context
      scenario is still open pending a chapter with uploaded material
