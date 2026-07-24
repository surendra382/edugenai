# Feature: Multi-Chapter Practice Paper Generation

**Phase:** 5 — Enhancements
**ID:** phase5-f01
**Status:** In Progress
**Depends on:** phase3-f02, phase3-f03, phase4-f01, phase4-f02, phase4-f03

---

## 1. Goal

A student can select **multiple chapters within one subject** for a single
practice paper and specify **how many questions to pull from each chapter**,
instead of being limited to one chapter per generation request — closing the
gap between the SRS's per-chapter Module 6 flow and how a real exam/practice
paper is usually assembled (mixed across a syllabus unit).

## 2. Scope

### In Scope
- New DB table `question_set_chapters` recording the per-chapter question
  count for a paper; `QuestionSet` gains a direct `subject_id` FK and its
  `chapter_id` becomes nullable (populated only when a paper is
  single-chapter, for backward compatibility with existing chapter-scoped
  reads); `Question` gains a `chapter_id` FK so every persisted question
  records which chapter it came from.
- New endpoint `POST /subjects/{subject_id}/question-sets` — accepts a list
  of `{chapter_id, num_questions}` selections (1 or more chapters; the new
  student UI always uses this endpoint, even for a single selected chapter,
  so there's one code path instead of branching between old/new endpoints).
- `generation_pipeline.run_generation` reworked to loop retrieval → prompt →
  LLM → parse **once per selected chapter** (in the chapters' `Chapter.order`
  sequence, not selection-click order), persisting each chapter's questions
  with a running `question_index` offset so the paper stays one sequentially
  numbered document. Failure semantics stay all-or-nothing: any chapter's
  generation step failing fails the whole `QuestionSet` (`status="failed"`,
  `generation_error` names the chapter), matching the existing single-chapter
  behavior — no partial-paper state is introduced.
- Existing `POST /chapters/{chapter_id}/question-sets` endpoint is
  preserved with its current external contract, reimplemented as a
  single-chapter call into the same shared creation/generation logic (so
  behavior stays unified, not duplicated) — the admin UI and any existing
  integration keep working unchanged.
- `GET /question-sets` (history) filtering extended: `subject_id` now
  matches via the new direct column (covers multi-chapter sets, which have
  no single `chapter_id` to join through); `chapter_id` now matches via
  `question_set_chapters` (any set that *includes* that chapter, not just
  sets scoped entirely to it).
- `build_question_paper_pdf` extended to render a subject-level title once,
  then a chapter sub-heading + that chapter's questions for each chapter in
  the paper (question numbering stays continuous across the whole document);
  single-chapter papers keep today's plain single-header layout unchanged.
- `frontend/pages/student_generate.py`: Chapter picker becomes a
  multiselect; once chapters are selected, a per-chapter number input for
  question count appears with a live running total; result view groups
  questions (and the answer key, when present) under a sub-heading per
  chapter.
- `frontend/pages/student_history.py`: chapter column shows the chapter
  name for single-chapter sets or a chapter-count/name summary for
  multi-chapter sets; inline result view reuses the same grouped-by-chapter
  rendering as the generate page.
- A total-question cap of 60 across all selected chapters in one request —
  a v1 guardrail, since generation time now scales with chapter count (one
  sequential LLM call per chapter, not parallelized).

### Out of Scope
- `frontend/pages/admin_question_generator.py` — stays on the existing
  single-chapter endpoint/UI unchanged; a same-shaped follow-up if the admin
  workflow needs it, not bundled into this slice.
- Per-chapter difficulty or question-type overrides — difficulty, question
  types, and the answer-key flag stay uniform across the whole paper, same
  granularity as today, just applied per chapter during generation.
- Partial-success papers (e.g. 2 of 3 chapters generate, 1 fails) — the
  existing binary `generating/completed/failed` status model is kept as-is;
  a failed chapter fails the whole request, same as today's single-chapter
  behavior.
- Parallelizing the per-chapter LLM calls — v1 runs them sequentially in one
  background task, same execution model as today, just looped.
- Cross-chapter deduplication of questions — each chapter's retrieval/prompt
  is independent, same as generating N separate single-chapter papers would
  produce.
- Selecting chapters across more than one subject in a single paper — a
  paper stays scoped to one subject, per SRS's subject → chapter hierarchy.

## 3. Data Model

```
QuestionSet (extended)
  subject_id        INTEGER FK -> subjects.id NOT NULL   -- new; always populated
  chapter_id        INTEGER FK -> chapters.id NULL        -- was NOT NULL; now only
                                                            -- set when the paper is
                                                            -- single-chapter
  num_questions     INTEGER NOT NULL   -- unchanged meaning: sum across all
                                        -- selected chapters

QuestionSetChapter (new table: question_set_chapters)
  id                INTEGER PK
  question_set_id   INTEGER FK -> question_sets.id NOT NULL
  chapter_id        INTEGER FK -> chapters.id NOT NULL
  num_questions     INTEGER NOT NULL      -- 1..30, this chapter's share
  UNIQUE(question_set_id, chapter_id)

Question (extended)
  chapter_id        INTEGER FK -> chapters.id NOT NULL   -- new; which chapter
                                                            -- this question came from
```

No Alembic migrations exist in this project (`Base.metadata.create_all()`
only creates missing tables, it does not alter existing ones — see
`backend/app/db/session.py`). Since the project is pre-production with no
real user data, the implementation step for this feature includes deleting
any local/dev SQLite DB file and letting `create_tables()` recreate the
schema from scratch, rather than hand-writing an `ALTER TABLE` migration.

## 4. API Contract

| Method | Path | Body / Query | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/subjects/{subject_id}/question-sets` | `{chapters: [{chapter_id, num_questions}], difficulty, question_types, include_answer_key}` | `202` `QuestionSetRead` | `404` if subject missing. `422` if `chapters` is empty, any `num_questions` outside 1..30, or the sum exceeds 60. `400` if `chapters` has duplicate `chapter_id`s or any `chapter_id` doesn't belong to `subject_id`. Creates one `QuestionSet` row + one `QuestionSetChapter` row per selection, dispatches background generation looping per chapter. |
| POST | `/chapters/{chapter_id}/question-sets` | unchanged: `{difficulty, question_types, num_questions, include_answer_key}` | `202` `QuestionSetRead` | Unchanged external behavior; internally now a single-chapter call into the same creation path as the endpoint above (one `QuestionSetChapter` row, `QuestionSet.chapter_id` populated since it's single-chapter). |
| GET | `/chapters/{chapter_id}/question-sets` | — | `200` `QuestionSetRead[]` | Unchanged: still scoped to papers where `chapter_id` is this chapter (i.e. single-chapter papers on this chapter only — a multi-chapter paper that happens to include this chapter is not returned here, same narrow scoping as today). |
| GET | `/question-sets` | adds no new params; existing `subject_id`, `chapter_id`, `status`, `limit` | `200` `QuestionSetHistoryRead[]` | `subject_id` now filters via `QuestionSet.subject_id` directly (includes multi-chapter sets). `chapter_id` now filters via a join through `question_set_chapters` (matches any set including that chapter). |
| GET | `/question-sets/{id}/questions` | — | `200` `QuestionRead[]` | Each row now includes `chapter_id`; ordering stays `question_index` ascending (still one continuous sequence for the whole paper). |
| GET | `/question-sets/{id}/pdf` | unchanged | `200` PDF | Groups questions into a per-chapter section (heading + that chapter's questions) when the set has more than one `QuestionSetChapter` row; single-chapter sets render exactly as before. |

**Schema additions:**

```python
class ChapterSelection(BaseModel):
    chapter_id: int
    num_questions: int   # 1..30

class QuestionSetCreateMulti(BaseModel):
    chapters: list[ChapterSelection]   # min length 1
    difficulty: Difficulty
    question_types: list[QuestionType]
    include_answer_key: bool = False

class QuestionSetChapterRead(BaseModel):
    chapter_id: int
    chapter_name: str
    num_questions: int

# QuestionSetRead gains:
    subject_id: int
    chapter_id: int | None          # now nullable
    chapters: list[QuestionSetChapterRead]   # always 1+ rows

# QuestionSetHistoryRead gains:
    chapter_name: str | None        # now nullable — null when >1 chapter

# QuestionRead gains:
    chapter_id: int
```

## 5. UI Behavior

- `student_generate.py`:
  - Subject `st.selectbox` (unchanged) → Chapter picker becomes an
    `st.multiselect` over that subject's chapters (ordered by `Chapter.order`).
  - Once 1+ chapters are selected, an `st.number_input` (default 5, 1–30)
    appears per selected chapter, labeled with the chapter name; a caption
    below shows the running total (`"Total questions: N"`), disabling the
    submit button if the total exceeds 60.
  - Difficulty, question types, and "Include answer key" controls are
    unchanged, applied uniformly to every selected chapter.
  - Submit → `POST /subjects/{subject_id}/question-sets` with the assembled
    `chapters` list, regardless of whether 1 or several chapters were picked
    — one code path.
  - Result view (`completed`): questions rendered under an `st.subheader`
    per chapter (using the set's `chapters` breakdown, matched against each
    `Question.chapter_id`), grouped by type within each chapter section as
    today; the answer-key expander follows the same per-chapter grouping.
  - `generating`/`failed` branches unchanged (refresh / retry buttons).
- `student_history.py`:
  - List rows: the chapter column shows the single chapter name for
    single-chapter sets, or `"{N} chapters"` (with the full list available
    on hover/expand) for multi-chapter sets, using the new `chapters` field.
  - "View" still loads the full row into the same grouped-by-chapter result
    rendering described above.
- `admin_question_generator.py`: unchanged — stays single-chapter (Out of
  Scope).

## 6. Test Strategy

### Unit Tests
- `QuestionSetCreateMulti` validation: rejects empty `chapters`, a
  `num_questions` outside 1..30, a total sum over 60, and duplicate
  `chapter_id`s within the list
- `build_question_paper_pdf`: with 1 chapter's worth of questions, output
  matches today's single-header layout byte-for-byte in structure; with 2+
  chapters, output includes a heading per chapter and every question still
  appears exactly once, in continuous numbering

### Integration Tests
- `POST /subjects/{id}/question-sets` with 2 chapters (e.g. 3 + 2 questions)
  and a `StubLLMProvider` → set reaches `completed`; `GET .../questions`
  returns 5 rows, `question_index` 0..4 continuous, first 3 rows have the
  first chapter's `chapter_id` and last 2 have the second's, in
  `Chapter.order` sequence regardless of selection order in the request
- One chapter's stub response malformed → whole set `status="failed"`,
  `generation_error` names that chapter; the other chapter's retrieval/LLM
  call is not required to have run (all-or-nothing short-circuit is
  acceptable, matching today's single-chapter contract)
- `POST /chapters/{chapter_id}/question-sets` (existing endpoint) still
  produces a set with exactly one `QuestionSetChapter` row and
  `QuestionSet.chapter_id` populated — regression check that the shared
  creation path didn't change external behavior
- `chapters` referencing a `chapter_id` from a different subject → `400`
- `chapters` with a duplicate `chapter_id` → `400`; empty `chapters` or
  total over 60 → `422`
- `GET /question-sets?subject_id=X` includes a multi-chapter set for that
  subject (previously would have been excluded since it has no single
  `chapter_id` to join through)
- `GET /question-sets?chapter_id=Y` includes a multi-chapter set that
  includes chapter Y, not just sets scoped entirely to Y
- `GET /question-sets/{id}/pdf` on a multi-chapter completed set → `200`,
  PDF text includes each chapter's name as a section heading

### Manual Verification
- [ ] Generate a paper across 2 chapters of the same subject (e.g. 3 + 4
      questions) from the Student page against a real `GROQ_API_KEY`;
      confirm the result view shows both chapter sections with the correct
      per-chapter counts and questions on-topic for their own chapter
- [ ] Confirm total-questions guard: selecting chapters whose per-chapter
      counts sum past 60 disables the submit button with a clear message
- [ ] Download the PDF for that multi-chapter paper and confirm it has a
      section heading per chapter with continuous question numbering
- [ ] Confirm History page shows the multi-chapter set with a "N chapters"
      summary, and that Subject/Chapter filters still surface it correctly
- [ ] Confirm the pre-existing single-chapter flow (Student page, one
      chapter selected) still works end-to-end unchanged, and that the
      Admin generator page (still single-chapter only) is unaffected

## 7. Acceptance Criteria

- [ ] All integration tests above pass
- [ ] A real multi-chapter paper generated end-to-end against the live Groq
      API, verified in-browser on the Student page including PDF export and
      History filtering
- [ ] Existing single-chapter flows (Student page, Admin page, and the
      `POST /chapters/{chapter_id}/question-sets` endpoint) remain fully
      functional with no behavior change
