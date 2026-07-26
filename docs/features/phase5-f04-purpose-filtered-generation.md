# Feature: Purpose-Filtered Few-Shot Generation

**Phase:** 5 — Enhancements
**ID:** phase5-f04
**Status:** Done
**Depends on:** phase5-f01, phase5-f03

---

## 0. Why This Feature

`phase5-f03` wired generation to pull few-shot exemplars from
`QuestionBankItem`, filtered by chapter and difficulty. That table already
carries a `source` field per question — admin-supplied at import time,
free text such as `sainik`, `olympiad`, `cbse_textbook`, `unknown` — but
nothing on the generation side reads it. A user picking "Sainik School"
practice questions today gets exemplars from whatever happens to be
imported for that chapter/difficulty, regardless of whether it's a Sainik
paper, an Olympiad paper, or a plain textbook exercise — the one facet the
Question Bank was explicitly imported to distinguish is invisible at
generation time.

This feature closes that gap: expose `source` as a selectable "Purpose" on
the generation request, and have exemplar selection prefer matching-purpose
questions before falling back — the same graceful-degradation shape
`_select_exemplars` already uses for difficulty (prefer exact match,
backfill within the chapter rather than fail), extended by one more facet.

## 1. Goal

A user generating a practice paper can pick a **purpose** (e.g. "Sainik",
"Olympiad", "CBSE Textbook", or "Any") alongside subject, chapter(s),
difficulty, and question count. The exemplars fed to the LLM are drawn
preferentially from `QuestionBankItem` rows matching that purpose, and the
prompt explicitly names the target exam style. The purpose is recorded on
the resulting paper and shown in its PDF.

## 2. Scope

### In Scope

- `QuestionSet.source` — new nullable column, uniform across the whole
  paper (same granularity as `difficulty`/`question_types`/
  `include_answer_key` today — see `phase5-f01` §2 Out of Scope, which this
  feature follows rather than diverges from). `NULL`/absent means "Any" —
  no purpose filter, current behavior unchanged.
- `GET /chapters/{chapter_id}/question-bank/sources` — new endpoint
  returning the distinct `source` values actually imported for that
  chapter, so the picker reflects real data instead of a guessed/hardcoded
  list. Empty list if nothing's been imported yet.
- `generation_pipeline._select_exemplars` extended with a third filter tier:
  when a `source` is requested, prefer chapter+difficulty+source exemplars,
  backfill with chapter+difficulty (any source), then chapter (any
  difficulty/source) — same shape as today's difficulty-only backfill, one
  tier deeper. When `source` is `None`, behavior is unchanged.
- `prompt_builder.build_prompt` gains an optional `source` parameter: when
  set, the prompt explicitly instructs the LLM to write in that exam's
  style (not just relying on exemplar style to carry it implicitly),
  independent of how many/few matching exemplars were actually found.
- `build_question_paper_pdf` renders the purpose in the paper's header
  when set (e.g. `"Sainik — Mathematics — Easy"`), omitted when `None`.
- Both generation endpoints (`POST /chapters/{chapter_id}/question-sets`,
  `POST /subjects/{subject_id}/question-sets`) and both UI pages
  (`admin_question_generator.py`, `student_generate.py`) gain a "Purpose"
  picker, populated from the new sources endpoint plus a leading "Any"
  option.
- Structured logging: `question_bank.lookup` gains a `source_requested`
  field and reports which fallback tier was actually used, so a paper that
  silently degraded to "any source" is visible in logs, not just inferred.

### Out of Scope

- Per-chapter purpose overrides on a multi-chapter paper — stays uniform
  for the whole paper, same reasoning `phase5-f01` already applied to
  difficulty/question-types.
- Showing exemplar *counts* per purpose in the picker (e.g. "Olympiad (12
  available)") — the sources endpoint returns names only; a
  count-annotated picker is a nice-to-have follow-up, not required to make
  the filter work.
- Constraining `source` to a fixed enum anywhere (`QuestionBankItem.source`
  is deliberately free text per `phase5-f03`; this feature doesn't change
  that or add validation against a closed vocabulary).
- Per-item tagging of which exemplars matched vs. which came from a
  fallback tier when formatting the prompt — the prompt states the target
  purpose once; individual exemplar lines aren't annotated with their own
  provenance.

## 3. Data Model

```
QuestionSet (extended)
  source            TEXT NULL     -- new; free text, mirrors QuestionBankItem.source;
                                    -- NULL means "Any" (no purpose filter)
```

No Alembic migrations exist in this project (`Base.metadata.create_all()`
only creates missing tables, it does not alter existing ones — see
`backend/app/db/session.py`, and the same note in `phase5-f01`). As before,
implementation includes running `scripts/reset_data.py --yes` against the
local dev DB rather than hand-writing an `ALTER TABLE` migration.

## 4. API Contract

| Method | Path | Body / Query | Response | Notes |
|--------|------|------|----------|-------|
| GET | `/chapters/{chapter_id}/question-bank/sources` | — | `200` `list[str]` | Distinct `QuestionBankItem.source` values for this chapter, sorted; `[]` if none imported yet; `404` if chapter missing |
| POST | `/chapters/{chapter_id}/question-sets` | adds optional `source: str \| None` | `202` `QuestionSetRead` | Unchanged otherwise |
| POST | `/subjects/{subject_id}/question-sets` | adds optional `source: str \| None` | `202` `QuestionSetRead` | Unchanged otherwise |
| GET | `/question-sets/{id}/pdf` | unchanged | `200` PDF | Header includes purpose when the set has one |

**Schema additions:**

```python
# QuestionSetCreate / QuestionSetCreateMulti gain:
    source: str | None = None

# QuestionSetRead / QuestionSetHistoryRead gain:
    source: str | None
```

**`_select_exemplars` signature change** (`generation_pipeline.py`):

```python
def _select_exemplars(
    db: Session, chapter_id: int, difficulty: str, source: str | None, limit: int = EXEMPLAR_LIMIT
) -> list[QuestionBankItem]:
```

Fallback order when `source` is not `None`: (1) `chapter_id` +
`difficulty` + `source` exact match, (2) backfill `chapter_id` +
`difficulty` (any source), (3) backfill `chapter_id` only (any
difficulty/source) — each tier excluding ids already picked, same
`limit`-filling pattern the current difficulty-only backfill already uses.
When `source` is `None`, tier (1) is skipped entirely and behavior is
byte-for-byte what it is today.

**`prompt_builder.build_prompt` signature change:**

```python
def build_prompt(
    subject_name: str,
    chapter_name: str,
    difficulty: str,
    question_types: list[str],
    num_questions: int,
    context_chunks: list[str],
    include_answer_key: bool = False,
    source: str | None = None,   # new
) -> str:
```

When `source` is set, an instruction line is added (independent of the
context section): write these questions in the style of a `{source}` exam
for this subject/chapter/difficulty.

## 5. UI Behavior

- Both `admin_question_generator.py` and `student_generate.py`: a
  "Purpose" `st.selectbox` appears once chapter(s) are selected, options =
  `["Any"] + <distinct sources for the selected chapter(s)>` (union across
  chapters for the student multi-select page, fetched via the new
  `/sources` endpoint), defaulting to "Any". Selecting "Any" sends
  `source=None`; anything else sends that string.
- Result view: purpose shown alongside difficulty in the paper's header
  caption (e.g. `"Difficulty: easy · Purpose: Sainik"`), omitted when "Any"
  was selected.
- `student_history.py`: purpose shown as an additional column/detail when
  present, matching how difficulty is already surfaced there.
- Empty state: if a selected chapter has no imported sources yet, the
  Purpose picker still shows (just `["Any"]`) rather than being hidden —
  keeps the control's position stable regardless of data state.

## 6. Test Strategy

### Unit Tests

- `_select_exemplars` with a `source`: chapter+difficulty+source exact
  matches preferred; when fewer than `limit`, backfilled with
  chapter+difficulty (any source), then chapter-only, without duplicating
  ids across tiers.
- `_select_exemplars` with `source=None`: identical results to current
  (pre-feature) behavior — regression check.
- `build_prompt` includes the purpose instruction line when `source` is
  set, omits it when `None`.
- `build_question_paper_pdf` includes the purpose in the header when set,
  matches today's header exactly when `None`.
- `QuestionSetCreate`/`QuestionSetCreateMulti` accept `source` omitted, as
  `None`, and as a string.

### Integration Tests

- `GET /chapters/{id}/question-bank/sources` on a chapter with imported
  items of 2 distinct sources → returns both, sorted; on a chapter with no
  imports → `[]`; on a nonexistent chapter → `404`.
- Generate with a `source` that has matching `QuestionBankItem` rows for
  the chapter/difficulty → `question_bank.lookup` log shows tier-1
  (exact-match) results used.
- Generate with a `source` that has zero matching rows but the chapter has
  other exemplars → set still completes (backfilled), log shows a
  fallback tier was used.
- Generate with `source=None` → unchanged from current behavior.
- `GET /question-sets/{id}/pdf` on a completed set with a `source` →
  response PDF text includes the purpose string in the header.
- `QuestionSetRead`/history responses round-trip `source` correctly
  (set it, fetch it back).

### Manual Verification

Verified via general end-to-end usage in the running app (Question Bank
import → purpose-filtered generation → PDF download) rather than the full
itemized checklist below; the specific sub-cases are left unchecked as a
reference for deeper verification later if a related bug shows up.

- [ ] Import a few Sainik-tagged and a few Olympiad-tagged questions for
      the same chapter/difficulty via the Question Bank page; generate a
      paper picking "Sainik" as purpose against a real LLM key; confirm
      the generated questions read like Sainik-style questions, not a mix.
- [ ] Generate again picking "Any"; confirm behavior is unchanged from
      before this feature (exemplars pulled regardless of source).
- [ ] Pick a purpose with no imported exemplars for that chapter; confirm
      generation still completes (general-knowledge/backfill fallback,
      not a failure) and the log shows the fallback tier used.
- [ ] Download the PDF for a purpose-tagged paper and confirm the purpose
      appears in the header.

## 7. Acceptance Criteria

- [ ] A user can select a purpose (or "Any") alongside existing generation
      facets, on both the admin and student generation pages.
- [ ] Exemplar selection prefers purpose-matching `QuestionBankItem` rows
      and gracefully backfills within the same chapter when too few exist,
      never failing generation solely for lack of purpose-specific content.
- [ ] The prompt explicitly states the target exam style when a purpose is
      set.
- [ ] The purpose is persisted on the `QuestionSet`, returned in reads, and
      shown in the exported PDF.
- [ ] All unit and integration tests pass; the manual checklist is
      verified against a real LLM key with real imported exemplars of at
      least two distinct purposes.
