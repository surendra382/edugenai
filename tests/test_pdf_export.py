import json

from fakes import StubLLMProvider

from backend.app.services import llm as llm_module
from backend.app.services.pdf_export import build_question_paper_pdf


def _chapters() -> list[dict]:
    return [{"chapter_id": 1, "chapter_name": "Algebra"}]


def _questions() -> list[dict]:
    return [
        {
            "question_index": 0,
            "chapter_id": 1,
            "question_type": "mcq",
            "text": "2+2=?",
            "options": ["3", "4", "5", "6"],
            "answer": "4",
        },
        {
            "question_index": 1,
            "chapter_id": 1,
            "question_type": "short_answer",
            "text": "Define a variable.",
            "options": None,
            "answer": "A symbol representing a value.",
        },
    ]


def test_build_question_paper_pdf_returns_pdf_bytes():
    pdf_bytes = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_chapters(),
        difficulty="easy",
        questions=_questions(),
        include_answers=False,
    )
    assert pdf_bytes.startswith(b"%PDF")


def test_build_question_paper_pdf_includes_question_text_and_options():
    pdf_bytes = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_chapters(),
        difficulty="easy",
        questions=_questions(),
        include_answers=False,
    )
    # fpdf2 output is a binary PDF stream; question text/options are encoded
    # inside it as literal bytes for the core (non-embedded) Helvetica font,
    # with PDF string syntax escaping ")" as "\)".
    assert b"2+2" in pdf_bytes
    assert b"Define a variable" in pdf_bytes
    assert b"D\\) 6" in pdf_bytes


def test_build_question_paper_pdf_includes_answer_section_when_requested():
    with_answers = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_chapters(),
        difficulty="easy",
        questions=_questions(),
        include_answers=True,
    )
    without_answers = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_chapters(),
        difficulty="easy",
        questions=_questions(),
        include_answers=False,
    )
    assert b"Answer Key" in with_answers
    assert b"Answer Key" not in without_answers
    assert b"A symbol representing a value" in with_answers
    assert b"A symbol representing a value" not in without_answers


def test_build_question_paper_pdf_handles_non_latin1_symbols_without_crashing():
    questions = [
        {
            "question_index": 0,
            "chapter_id": 1,
            "question_type": "short_answer",
            "text": "Simplify √2 × π",
            "options": None,
            "answer": None,
        }
    ]
    pdf_bytes = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_chapters(),
        difficulty="easy",
        questions=questions,
        include_answers=False,
    )
    assert pdf_bytes.startswith(b"%PDF")


def test_build_question_paper_pdf_renders_rupee_sign_instead_of_question_mark():
    questions = [
        {
            "question_index": 0,
            "chapter_id": 1,
            "question_type": "short_answer",
            "text": "A shirt costs ₹800. Find the sale price.",
            "options": None,
            "answer": None,
        }
    ]
    pdf_bytes = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_chapters(),
        difficulty="easy",
        questions=questions,
        include_answers=False,
    )
    assert b"Rs. 800" in pdf_bytes


def test_build_question_paper_pdf_multi_chapter_groups_by_chapter_with_headings():
    chapters = [
        {"chapter_id": 1, "chapter_name": "Algebra"},
        {"chapter_id": 2, "chapter_name": "Geometry"},
    ]
    questions = [
        {
            "question_index": 0,
            "chapter_id": 1,
            "question_type": "mcq",
            "text": "2+2=?",
            "options": ["3", "4", "5", "6"],
            "answer": "4",
        },
        {
            "question_index": 1,
            "chapter_id": 2,
            "question_type": "short_answer",
            "text": "Define a triangle.",
            "options": None,
            "answer": "A three-sided polygon.",
        },
    ]
    pdf_bytes = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=chapters,
        difficulty="easy",
        questions=questions,
        include_answers=True,
    )
    assert b"Algebra" in pdf_bytes
    assert b"Geometry" in pdf_bytes
    assert b"2+2" in pdf_bytes
    assert b"Define a triangle" in pdf_bytes


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()


def _valid_llm_response_with_answers(count: int = 1) -> str:
    return json.dumps(
        [
            {"type": "mcq", "text": f"Question {i}", "options": ["A", "B", "C", "D"], "answer": "A"}
            for i in range(count)
        ]
    )


def test_export_pdf_for_completed_set_returns_pdf(client, monkeypatch):
    monkeypatch.setattr(
        llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response_with_answers(2))
    )
    chapter = _create_chapter(client)
    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "question_types": ["mcq"],
            "num_questions": 2,
            "include_answer_key": True,
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    pdf_response = client.get(f"/question-sets/{question_set_id}/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content.startswith(b"%PDF")
    assert b"Answer Key" in pdf_response.content


def test_export_pdf_defensive_floor_ignores_include_answers_when_set_has_no_answer_key(
    client, monkeypatch
):
    monkeypatch.setattr(
        llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response_with_answers(1))
    )
    chapter = _create_chapter(client)
    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "question_types": ["mcq"],
            "num_questions": 1,
            "include_answer_key": False,
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    pdf_response = client.get(f"/question-sets/{question_set_id}/pdf?include_answers=true")
    assert pdf_response.status_code == 200
    assert b"Answer Key" not in pdf_response.content


def test_export_pdf_for_missing_question_set_returns_404(client):
    response = client.get("/question-sets/999/pdf")
    assert response.status_code == 404


def test_export_pdf_for_generating_set_returns_409(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response="not valid json"))
    chapter = _create_chapter(client)
    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "failed"

    pdf_response = client.get(f"/question-sets/{question_set_id}/pdf")
    assert pdf_response.status_code == 409
