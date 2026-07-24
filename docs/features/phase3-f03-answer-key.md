# Feature: Answer Key Generation

**Phase:** 3 — AI Question Generator
**ID:** phase3-f03
**Status:** Done
**Depends on:** phase3-f02

---

## 1. Goal

A generated practice paper can optionally include a per-question answer key,
per SRS Module 9 ("every generated paper should optionally include an
answer key").

## 2. Scope

### In Scope
- `include_answer_key` flag on a question-set request, threaded through the
  prompt and the parser
- `Question.answer` populated only when the flag was set on the request that
  generated it — enforced at persistence time regardless of what the model
  returns, so a `False` request can never leak an answer

### Out of Scope
- Step-by-step solutions (explicitly "future" per SRS Module 9)
- Per-question toggling within a single set (the flag is set once, for the
  whole set, at generation time)

## 3. Data Model

```
QuestionSet (extended)
  include_answer_key   BOOLEAN NOT NULL DEFAULT false

Question (extended)
  answer               TEXT NULL   -- populated only when the owning set's
                                    -- include_answer_key is true
```

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/chapters/{chapter_id}/question-sets` | adds `include_answer_key: bool = false` | `202` `QuestionSetRead` (now includes `include_answer_key`) | unchanged otherwise from phase3-f02 |
| GET | `/question-sets/{id}/questions` | — | `200` `QuestionRead[]` (now includes `answer: str \| None`) | `answer` is always `null` when the set's `include_answer_key` is `false` |

## 5. UI Behavior

None yet — phase3-f04 adds the checkbox and answer-key display.

## 6. Test Strategy

### Unit Tests
- `build_prompt(..., include_answer_key=True)` instructs the model to add
  an `"answer"` field per question
- `parse_questions(..., expect_answer=True)` rejects an item missing
  `"answer"`; `expect_answer=False` does not require it

### Integration Tests
- `include_answer_key=True` with a stub returning answers → persisted
  `Question.answer` populated for every question
- `include_answer_key=False` with a stub that *still* returns an `"answer"`
  field → persisted rows have `answer is None` (defensive floor)
- `include_answer_key=True` with a stub omitting `"answer"` → `status="failed"`

### Manual Verification
- [x] Generated with `include_answer_key=true` against the real Groq API:
      every question got a plausible, correct `answer` (e.g. mcq answer
      `"A) 5/10"` matching the correct option text, short_answer answer
      `"3/4"` for a simplification question)
- [ ] Spot-check a `numerical` question specifically, and confirm
      `include_answer_key=false` still omits answers with the real API
      (only `mcq`/`short_answer` + `include_answer_key=true` exercised so
      far manually; the `false` path and other types are covered by the
      integration tests above but not yet re-confirmed against the live API)

## 7. Acceptance Criteria

- [x] All integration tests above pass
- [x] Manual verification confirms correct answer-key behavior against the
      real Groq API for the scenario above
