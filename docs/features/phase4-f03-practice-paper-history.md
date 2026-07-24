# Feature: Practice Paper History

**Phase:** 4 — Student Portal
**ID:** phase4-f03
**Status:** Done
**Depends on:** phase4-f01

---

## 1. Goal

A student (or admin) can browse one combined, cross-subject list of every
practice paper ever generated — filterable by subject, chapter, and status
— without first having to know which chapter it belongs to, closing out
the SRS roadmap's Phase 4 "Session history" item.

## 2. Scope

### In Scope
- Backend: `GET /question-sets` — optional `subject_id`, `chapter_id`,
  `status` filters, newest-first, capped by `limit` (default 50, max 200).
  Each row is enriched with `chapter_name` and `subject_name` (via a join)
  so the UI needs no separate per-row lookups.
- New schema `QuestionSetHistoryRead` (extends `QuestionSetRead` with
  `chapter_name: str`, `subject_name: str`)
- `frontend/pages/student_history.py`: subject/chapter/status filter
  dropdowns (each optional, defaulting to "All"), a list of matching
  papers (subject, chapter, difficulty, question types, status), and a
  "View" action per row that renders the result inline on the same page
  (questions, answer key if present, PDF download) — built as a standalone
  page rather than round-tripping through `student_generate.py`, which
  sidesteps having to sync that page's Subject/Chapter widgets to a
  specific historical selection just to display one paper

### Out of Scope
- Per-student/per-user-scoped history — there is no identity concept in
  Phase 4 (per the no-auth decision in phase4-f01), so this is the one
  shared history across all generated papers, matching the project's
  current single-implicit-student scope. Real per-user history becomes
  possible once Phase 5 adds Authentication.
- Pagination UI beyond a simple limit/"show more" bump — no infinite
  scroll or virtualization
- Editing or deleting past papers from history — no delete endpoint is
  added by this feature

## 3. Data Model

None new — read-only query joining the existing `QuestionSet`, `Chapter`,
and `Subject` tables.

## 4. API Contract

| Method | Path | Query | Response | Notes |
|--------|------|-------|----------|-------|
| GET | `/question-sets` | `subject_id: int?`, `chapter_id: int?`, `status: str?`, `limit: int = 50` (max 200) | `200` `QuestionSetHistoryRead[]` | Newest first (`created_at desc`). No filters → every question set across every subject/chapter. `subject_id` filters via a join through `Chapter`; `chapter_id` narrows further/independently. Unknown `subject_id`/`chapter_id` simply yields an empty list (no 404 — this is a list/filter endpoint, not a resource lookup). |

## 5. UI Behavior

- Three optional filter controls at the top: Subject `st.selectbox`
  (options = subjects + "All"), Chapter `st.selectbox` (options = that
  subject's chapters + "All", only populated once a subject is picked),
  Status `st.selectbox` ("All" / generating / completed / failed).
- Below the filters, a list (one row per question set): subject name,
  chapter name, difficulty, question types, status badge, and a "View"
  button.
- Clicking "View" stores the full row (already fetched — no extra round
  trip) in `st.session_state["history_active_question_set"]`; a "Result"
  section renders below using the same generating/failed/completed
  branching as `student_generate.py`'s result view, including the answer
  key expander and the PDF download button (with the same
  include-answers-when-the-set-has-one toggle from phase4-f02) for a
  `completed` set.
- Empty state: `st.info("No practice papers generated yet")` when the
  filtered list is empty.

## 6. Test Strategy

### Unit Tests
—

### Integration Tests
- `GET /question-sets` with no filters → returns sets from multiple
  chapters/subjects, newest first, each with correct `chapter_name` /
  `subject_name`
- `subject_id` filter → only that subject's sets, across all its chapters
- `chapter_id` filter → identical result set to the existing
  `GET /chapters/{id}/question-sets` endpoint, just reshaped with the
  added name fields
- `status` filter → only matching-status rows
- `limit` respected; omitted `limit` defaults to 50
- Filtering by a nonexistent `subject_id`/`chapter_id` → `200` empty list,
  not `404`

### Manual Verification
- [x] Generated practice papers in two different subjects/chapters
      ("Mathematics / Rational Numbers" and a newly created
      "Social Science / Geography Basics", both against the real Groq
      API) and confirmed both appear together in one unfiltered list,
      newest first, with correct subject/chapter names
- [x] Filtered by Subject ("Social Science") in the real UI and confirmed
      the list narrowed to just that subject's one entry
- [x] Clicked "View" on the "Social Science" `completed` entry and
      confirmed the inline Result section rendered the correct 2 MCQ
      questions plus a working "Download PDF" button (no answer-key
      expander, correctly, since that set was generated without one)
- [ ] Status filter narrowing exercised only via the integration test, not
      re-clicked manually in this session (identical dropdown/query-param
      mechanism to the already-verified Subject filter)

## 7. Acceptance Criteria

- [x] All integration tests above pass
- [x] Manual cross-subject browsing and filter verification confirmed
      against real generated data
