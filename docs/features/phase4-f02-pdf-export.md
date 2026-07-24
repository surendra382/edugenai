# Feature: PDF Export

**Phase:** 4 — Student Portal
**ID:** phase4-f02
**Status:** Done
**Depends on:** phase4-f01, phase3-f03

---

## 1. Goal

A completed practice paper — and its answer key, when one was generated —
can be downloaded as a PDF from both the admin and student pages, per the
SRS roadmap's Phase 4 "PDF export" item.

## 2. Scope

### In Scope
- `fpdf2` added to `requirements/base.txt` (pure-Python, no system
  dependencies, matching the project's cost-conscious/low-footprint stance)
- `backend/app/services/pdf_export.py`:
  `build_question_paper_pdf(question_set, questions, include_answers) -> bytes`
  — title block (subject name, chapter name, difficulty), questions
  numbered in generation order with lettered MCQ options, and a separate
  "Answer Key" section appended at the end only when `include_answers` is
  `True`
- API: `GET /question-sets/{id}/pdf?include_answers=bool` (default `true`)
  — streams the PDF as `application/pdf`
- "Download PDF" button wired into both `admin_question_generator.py` and
  `student_generate.py`'s `completed` result view; an "include answers"
  toggle next to it, shown only when the set has an answer key

### Out of Scope
- Any layout templating beyond a plain, readable single-column paper — no
  letterhead, branding, or watermarking
- Export formats other than PDF (e.g. DOCX) — not called for by the SRS
- Batch/bulk export of multiple question sets in one request
- Step-by-step solutions in the export (still "future" per SRS Module 9,
  same as phase3-f03)

## 3. Data Model

None — reads existing `QuestionSet` / `Question` rows.

## 4. API Contract

| Method | Path | Query | Response | Notes |
|--------|------|-------|----------|-------|
| GET | `/question-sets/{id}/pdf` | `include_answers: bool = true` | `200` binary, `Content-Type: application/pdf`, `Content-Disposition: attachment` | `404` if the set doesn't exist; `409` if `status != "completed"`. `include_answers` is forced to `false` server-side whenever the set's `include_answer_key` is `false`, regardless of the query value — same defensive-floor pattern phase3-f03 uses for the `answer` field, so a paper generated without an answer key can never leak one through this endpoint either. |

## 5. UI Behavior

- In the `completed` branch of both result views: a "Download PDF" button.
  If the set has `include_answer_key == true`, an adjacent checkbox
  "Include answers in PDF" (default checked) controls the `include_answers`
  query param; the checkbox is not rendered at all when the set has no
  answer key (nothing to toggle).
- Implementation pattern: `requests.get(..., params={"include_answers": ...})`
  to fetch the bytes, then `st.download_button(data=..., file_name=...,
  mime="application/pdf")` — Streamlit requires the bytes in hand before
  rendering the download button, so this is a two-step fetch-then-offer
  flow, not a direct link.

## 6. Test Strategy

### Unit Tests
- `build_question_paper_pdf` returns bytes starting with the `%PDF` magic
  header
- Output includes every question's text and, for `mcq` items, its options
- `include_answers=True` output includes an answer-key section with every
  question's answer; `include_answers=False` output has no such section
  and does not otherwise leak answer text

### Integration Tests
- `GET /question-sets/{id}/pdf` on a `completed` set → `200`,
  `Content-Type: application/pdf`, body starts with `%PDF`
- Set with `include_answer_key=False` + `?include_answers=true` → still
  `200`, PDF has no answer section (defensive floor, mirroring the
  phase3-f03 integration test for the JSON endpoint)
- `GET /question-sets/999/pdf` → `404`
- `GET .../pdf` on a `generating` or `failed` set → `409`

### Manual Verification
- [x] Downloaded a PDF for a real completed paper ("Mathematics / Rational
      Numbers", 5 questions with an answer key) from the Student page in a
      real browser: `st.download_button` produced `question_set_6.pdf`
      (2803 bytes) in the Downloads folder, starting with the `%PDF-1.3`
      header and containing 2 pages (`/Count 2`), confirming the
      Answer Key page was appended. Chrome's extension sandbox couldn't
      navigate to a local `file://` URL to screenshot the rendered page,
      so layout was confirmed structurally (page count, byte header, text
      content) rather than visually — no rendering issues expected given
      the unit tests already assert every question/option/answer's text is
      present in the stream.
- [x] Confirmed the "include answers" checkbox is present (default
      checked) on a set generated with an answer key
- [x] Confirmed the defensive floor end-to-end: `GET
      /question-sets/3/pdf?include_answers=true` against a real set with
      `include_answer_key=false` returned `200` with no "Answer Key" text
      anywhere in the output, matching the integration test
- [ ] Admin page's PDF button (identical code path to the student page's,
      already verified above) not re-clicked manually in this session

## 7. Acceptance Criteria

- [x] All integration tests above pass
- [x] Manual PDF structural verification and defensive-floor check
      confirmed against a real generated paper
