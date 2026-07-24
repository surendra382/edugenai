# Feature: Admin "Generate Practice Paper" UI

**Phase:** 3 — AI Question Generator
**ID:** phase3-f04
**Status:** Done
**Depends on:** phase3-f03

---

## 1. Goal

An admin can generate, view, retry, and revisit past practice papers from
the Streamlit UI — closing out Phase 3 with an end-to-end, manually
verifiable slice, the same way `admin_preview.py` closed out Phase 2.

## 2. Scope

### In Scope
- `frontend/pages/admin_question_generator.py`: subject → chapter cascade
  (same pattern as `admin_preview.py`), a generation form (difficulty,
  question types, count, answer-key checkbox), a result view with manual
  refresh + retry, and a history list of past question sets for the chapter

### Out of Scope
- PDF/text export (Phase 4 per the SRS roadmap)
- Student-facing UI (Phase 4)
- Auto-polling/websockets — status is refreshed on demand via a button,
  matching the existing OCR/embedding admin pages' convention

## 3. Data Model

None — UI only, consumes the phase3-f02/f03 API.

## 4. API Contract

None — no backend changes.

## 5. UI Behavior

- Subject `st.selectbox` → Chapter `st.selectbox` (reuses the cascading
  pattern from `admin_preview.py`)
- Form: difficulty (`st.selectbox`: easy/medium/hard), question types
  (`st.multiselect` over the 6 SRS-defined types), count (`st.number_input`,
  1–30), "Include answer key" (`st.checkbox`) → submit → `POST
  /chapters/{id}/question-sets`, resulting id stored in `st.session_state`
- Result view: `GET /question-sets/{id}` + `.../questions`
  - `generating`: `st.info("Generating…")` + "Refresh" button
  - `completed`: numbered question list grouped by type; answers shown in
    an `st.expander("Answer Key")` only when `include_answer_key` is true
  - `failed`: `st.error(generation_error)` + "Retry" button
- History: `GET /chapters/{id}/question-sets`, status badge per row,
  clicking a row loads it into the result view

## 6. Test Strategy

### Unit Tests
—

### Integration Tests
—

### Manual Verification
- [x] Verified in a real browser (subject/chapter cascade, difficulty
      select, question-type multiselect with friendly labels, answer-key
      checkbox, number input) against a live backend + Streamlit instance:
      submitting dispatches generation, the History section immediately
      shows a `generating` row, and the Result panel shows the
      "Generating…" state with a working Refresh button
- [x] Verified the `failed` state renders `generation_error` (a real
      `Groq API key is not configured` error, since no key is configured in
      this environment) and that Retry flips it back to `generating` and
      re-dispatches generation, both in the Result panel and the History
      row
- [ ] Generate a full paper end-to-end for each difficulty level and at
      least three question types in one request, and confirm the
      answer-key toggle reveals/hides answers on a `completed` set — both
      require a real `GROQ_API_KEY`, not available in this environment
- [ ] Confirm history reloads a past `completed` set into the result view
      (exercised above for `generating`/`failed`; not yet exercised for
      `completed`, pending a real API key)

## 7. Acceptance Criteria

- [x] Page usable end-to-end from the Streamlit UI for the
      generating/failed/retry/history paths; no crashes on empty states
- [ ] Full completed-paper + answer-key rendering confirmed manually
      (pending a real `GROQ_API_KEY`)
