from fpdf import FPDF
from fpdf.enums import XPos, YPos

QUESTION_TYPE_LABELS = {
    "mcq": "Multiple Choice",
    "fill_blank": "Fill in the Blanks",
    "true_false": "True/False",
    "short_answer": "Short Answer",
    "long_answer": "Long Answer",
    "numerical": "Numerical Problem",
}

OPTION_LETTERS = "ABCDEFGHIJ"

# The core PDF fonts only support latin-1. LLM-generated question text
# regularly includes math/typographic symbols outside that range (e.g. "√2",
# "π") — translate the common ones to an ASCII equivalent so the PDF never
# fails to render; anything left over falls back to "?" via the encode step.
_UNICODE_REPLACEMENTS = {
    "√": "sqrt",
    "π": "pi",
    "×": "x",
    "÷": "/",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "–": "-",
    "—": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    "°": " deg",
}


def _safe_text(text: str) -> str:
    for source, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    return text.encode("latin-1", "replace").decode("latin-1")


def _line(pdf: FPDF, height: float, text: str) -> None:
    # new_x/new_y must be pinned back to the left margin — fpdf2's default
    # leaves the cursor at the right edge after a multi_cell, which then
    # starves the next call of horizontal space to render into.
    pdf.multi_cell(0, height, _safe_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def build_question_paper_pdf(
    *,
    subject_name: str,
    chapters: list[dict],
    difficulty: str,
    questions: list[dict],
    include_answers: bool,
) -> bytes:
    pdf = FPDF()
    pdf.set_compression(False)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    is_multi_chapter = len(chapters) > 1
    title = subject_name if is_multi_chapter else f"{subject_name} - {chapters[0]['chapter_name']}"

    pdf.set_font("Helvetica", "B", 16)
    _line(pdf, 10, title)
    pdf.set_font("Helvetica", size=11)
    _line(pdf, 8, f"Difficulty: {difficulty.capitalize()}")
    pdf.ln(4)

    questions_by_chapter: dict[int, list[dict]] = {}
    for question in questions:
        questions_by_chapter.setdefault(question["chapter_id"], []).append(question)

    for chapter in chapters:
        chapter_questions = questions_by_chapter.get(chapter["chapter_id"], [])
        if is_multi_chapter:
            pdf.set_font("Helvetica", "B", 13)
            _line(pdf, 9, f"Chapter: {chapter['chapter_name']} ({len(chapter_questions)} questions)")
            pdf.ln(1)
        for question in chapter_questions:
            label = QUESTION_TYPE_LABELS.get(question["question_type"], question["question_type"])
            pdf.set_font("Helvetica", "B", 12)
            _line(pdf, 8, f"Q{question['question_index'] + 1}. ({label}) {question['text']}")
            pdf.set_font("Helvetica", size=12)
            options = question.get("options")
            if options:
                for index, option in enumerate(options):
                    letter = OPTION_LETTERS[index] if index < len(OPTION_LETTERS) else str(index + 1)
                    _line(pdf, 7, f"   {letter}) {option}")
            pdf.ln(2)

    if include_answers:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        _line(pdf, 10, "Answer Key")
        for chapter in chapters:
            chapter_questions = questions_by_chapter.get(chapter["chapter_id"], [])
            if is_multi_chapter:
                pdf.set_font("Helvetica", "B", 12)
                _line(pdf, 8, chapter["chapter_name"])
            pdf.set_font("Helvetica", size=12)
            for question in chapter_questions:
                _line(pdf, 8, f"Q{question['question_index'] + 1}: {question.get('answer') or ''}")

    return bytes(pdf.output())
