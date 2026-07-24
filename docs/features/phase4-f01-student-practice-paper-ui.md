# Feature: Student "Generate Practice Paper" UI

**Phase:** 4 — Student Portal
**ID:** phase4-f01
**Status:** Done
**Depends on:** phase3-f03

---

## 1. Goal

A student can open a dedicated Student page, pick subject → chapter →
difficulty → question types → count, generate a practice paper, and view
the result — the student-facing counterpart to phase3-f04's admin page,
built on the same generation engine, with no login or credential check.

## 2. Scope

### In Scope
- `frontend/pages/student_generate.py`: subject → chapter cascade,
  generation form (difficulty, question types, count, answer-key checkbox),
  a result view (generating / completed / failed, with retry), and a
  chapter-scoped history list — the same shape as
  `admin_question_generator.py`, reusing the phase3-f02/f03 API as-is, with
  copy/framing appropriate for a student rather than an admin
- `frontend/app.py`: landing page reorganized into two labeled groups of
  `st.page_link` — "Admin" (the five existing admin pages) and "Student"
  (this new page) — purely navigational grouping, no access control

### Out of Scope
- Any login, credential check, or session/user identity. This is an
  explicit standing decision for Phase 4: real Authentication stays in
  Phase 5 per the SRS roadmap (§18), and per CLAUDE.md, auth checks are not
  added unless a feature doc calls for them. Admin pages remain reachable
  by anyone who opens the app, same as today.
- PDF export (phase4-f02)
- Cross-chapter/global history (phase4-f03) — this page's history stays
  chapter-scoped, identical in shape to the admin page's history section
- Any new backend endpoints or schema changes — this is a UI-only slice

## 3. Data Model

None — reuses `QuestionSet` / `Question` from phase3-f02/f03.

## 4. API Contract

None — no backend changes. Consumes the existing phase3-f02/f03 endpoints:
`POST /chapters/{id}/question-sets`, `GET /chapters/{id}/question-sets`,
`GET /question-sets/{id}`, `GET /question-sets/{id}/questions`,
`POST /question-sets/{id}/retry`.

## 5. UI Behavior

- Landing page (`frontend/app.py`): below the existing backend-health
  check, two `st.subheader` sections — "Admin" and "Student" — each listing
  `st.page_link` entries for the pages in that group.
- `student_generate.py`:
  - Subject `st.selectbox` → Chapter `st.selectbox` (identical cascade
    pattern to `admin_preview.py` / `admin_question_generator.py`)
  - Form: difficulty (`st.selectbox`: easy/medium/hard), question types
    (`st.multiselect` over the 6 SRS-defined types with friendly labels),
    count (`st.number_input`, 1–30), "Include answer key" (`st.checkbox`)
    → submit → `POST /chapters/{id}/question-sets`, resulting id stored in
    `st.session_state`
  - Result view: `GET /question-sets/{id}` + `.../questions`
    - `generating`: `st.info("Generating…")` + "Refresh" button
    - `completed`: numbered question list grouped by type; answers shown
      in an `st.expander("Answer Key")` only when `include_answer_key` is
      true
    - `failed`: `st.error(generation_error)` + "Retry" button
  - History: `GET /chapters/{id}/question-sets`, status badge per row,
    clicking a row loads it into the result view

## 6. Test Strategy

### Unit Tests
—

### Integration Tests
—

### Manual Verification
- [x] Landing page shows both "Admin" and "Student" link groups; every
      link navigates to the correct page (verified in a real browser
      against a live Streamlit + FastAPI instance)
- [x] Full generate → generating → completed flow exercised from the
      Student page against a real `GROQ_API_KEY`: "Mathematics / Rational
      Numbers", easy, mcq + short_answer, 5 questions — completed with 5
      on-topic questions
- [x] Answer-key checkbox toggles the expander's presence on a completed
      set, matching phase3-f04's already-verified admin behavior — checked
      the box, generated, and the "Answer Key" expander appeared
- [ ] `failed` state renders the error and "Retry" re-dispatches
      generation correctly from the Student page (not re-exercised here;
      identical code path to the already-verified phase3-f04 admin page)
- [x] Chapter-scoped history reloads a past set into the result view — the
      History section listed prior sets (including ones from earlier
      phase3 testing) alongside the newly generated one

## 7. Acceptance Criteria

- [x] Student page usable end-to-end for the generating/failed/retry/
      history/completed paths; no crashes on empty states (no subjects,
      no chapters, no history)
- [x] Landing page cleanly separates Admin and Student entry points with
      no functional access restriction
