import json

import pytest
from fakes import StubLLMProvider

from backend.app.services import llm as llm_module
from backend.app.services.prompt_builder import build_prompt
from backend.app.services.question_parser import parse_questions


def test_build_prompt_includes_difficulty_types_and_chapter_name():
    prompt = build_prompt(
        subject_name="Mathematics",
        chapter_name="Algebra",
        difficulty="hard",
        question_types=["mcq", "short_answer"],
        num_questions=5,
        context_chunks=["Algebra is the study of symbols."],
    )
    assert "hard" in prompt
    assert "mcq" in prompt
    assert "short_answer" in prompt
    assert "Algebra" in prompt
    assert "Algebra is the study of symbols." in prompt


def test_build_prompt_falls_back_to_general_knowledge_when_no_context():
    prompt = build_prompt(
        subject_name="Mathematics",
        chapter_name="Algebra",
        difficulty="easy",
        question_types=["mcq"],
        num_questions=3,
        context_chunks=[],
    )
    assert "No uploaded material is available" in prompt
    assert "Algebra" in prompt


def test_parse_questions_accepts_valid_json():
    raw = json.dumps(
        [
            {"type": "mcq", "text": "2+2=?", "options": ["3", "4", "5", "6"]},
            {"type": "short_answer", "text": "Define a variable."},
        ]
    )
    questions = parse_questions(raw, expected_types={"mcq", "short_answer"}, expect_count=2)
    assert questions[0]["type"] == "mcq"
    assert questions[0]["options"] == ["3", "4", "5", "6"]
    assert questions[1]["options"] is None


def test_parse_questions_strips_baked_in_option_letters():
    raw = json.dumps(
        [
            {
                "type": "mcq",
                "text": "Profit or loss?",
                "options": ["A) 5% profit", "B) 10% loss", "C) 5% loss", "D) 10% profit"],
                "answer": "A) 5% profit",
            }
        ]
    )
    questions = parse_questions(
        raw, expected_types={"mcq"}, expect_count=1, expect_answer=True
    )
    assert questions[0]["options"] == ["5% profit", "10% loss", "5% loss", "10% profit"]
    assert questions[0]["answer"] == "5% profit"


def test_parse_questions_strips_code_fences():
    raw = "```json\n" + json.dumps([{"type": "short_answer", "text": "Q1"}]) + "\n```"
    questions = parse_questions(raw, expected_types={"short_answer"}, expect_count=1)
    assert questions[0]["text"] == "Q1"


def test_parse_questions_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_questions("not json", expected_types={"mcq"}, expect_count=1)


def test_parse_questions_recovers_from_latex_style_backslash():
    raw = '[{"type": "short_answer", "text": "Simplify \\sqrt{16}."}]'
    questions = parse_questions(raw, expected_types={"short_answer"}, expect_count=1)
    assert questions[0]["text"] == "Simplify \\sqrt{16}."


def test_parse_questions_rejects_unknown_type():
    raw = json.dumps([{"type": "essay", "text": "Q1"}])
    with pytest.raises(ValueError):
        parse_questions(raw, expected_types={"mcq"}, expect_count=1)


def test_parse_questions_rejects_mcq_without_enough_options():
    raw = json.dumps([{"type": "mcq", "text": "Q1", "options": ["only one"]}])
    with pytest.raises(ValueError):
        parse_questions(raw, expected_types={"mcq"}, expect_count=1)


def test_parse_questions_rejects_count_mismatch():
    raw = json.dumps([{"type": "short_answer", "text": "Q1"}])
    with pytest.raises(ValueError):
        parse_questions(raw, expected_types={"short_answer"}, expect_count=2)


def test_parse_questions_requires_answer_when_expected():
    raw = json.dumps([{"type": "short_answer", "text": "Q1"}])
    with pytest.raises(ValueError):
        parse_questions(raw, expected_types={"short_answer"}, expect_count=1, expect_answer=True)


def test_parse_questions_includes_answer_when_expected():
    raw = json.dumps([{"type": "short_answer", "text": "Q1", "answer": "A1"}])
    questions = parse_questions(
        raw, expected_types={"short_answer"}, expect_count=1, expect_answer=True
    )
    assert questions[0]["answer"] == "A1"


def test_parse_questions_ignores_answer_when_not_expected():
    raw = json.dumps([{"type": "short_answer", "text": "Q1", "answer": "A1"}])
    questions = parse_questions(raw, expected_types={"short_answer"}, expect_count=1)
    assert questions[0]["answer"] is None


def test_build_prompt_instructs_answer_field_when_requested():
    prompt = build_prompt(
        subject_name="Mathematics",
        chapter_name="Algebra",
        difficulty="easy",
        question_types=["mcq"],
        num_questions=1,
        context_chunks=[],
        include_answer_key=True,
    )
    assert '"answer"' in prompt


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()


def _valid_llm_response(count: int = 2) -> str:
    return json.dumps(
        [
            {"type": "mcq", "text": f"Question {i}", "options": ["A", "B", "C", "D"]}
            for i in range(count)
        ]
    )


def test_generate_question_set_completes_with_valid_llm_output(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(2)))
    chapter = _create_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 2},
    )
    assert response.status_code == 202
    question_set_id = response.json()["id"]

    fetched = client.get(f"/question-sets/{question_set_id}").json()
    assert fetched["status"] == "completed"

    questions = client.get(f"/question-sets/{question_set_id}/questions").json()
    assert len(questions) == 2
    assert questions[0]["question_index"] == 0
    assert questions[0]["question_type"] == "mcq"
    assert questions[0]["options"] == ["A", "B", "C", "D"]


def test_generate_question_set_fails_on_malformed_llm_output(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response="not valid json"))
    chapter = _create_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 2},
    )
    question_set_id = response.json()["id"]

    fetched = client.get(f"/question-sets/{question_set_id}").json()
    assert fetched["status"] == "failed"
    assert fetched["generation_error"]


def test_retry_question_set_recovers(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response="not valid json"))
    chapter = _create_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "failed"

    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    retry_response = client.post(f"/question-sets/{question_set_id}/retry")
    assert retry_response.status_code == 202

    fetched = client.get(f"/question-sets/{question_set_id}").json()
    assert fetched["status"] == "completed"
    assert fetched["generation_error"] is None


def test_retry_question_set_rejected_when_not_failed(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    chapter = _create_chapter(client)
    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    question_set_id = response.json()["id"]

    retry_response = client.post(f"/question-sets/{question_set_id}/retry")
    assert retry_response.status_code == 409


def test_generate_on_nonexistent_chapter_returns_404(client):
    response = client.post(
        "/chapters/999/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    assert response.status_code == 404


def test_get_nonexistent_question_set_returns_404(client):
    response = client.get("/question-sets/999")
    assert response.status_code == 404


def _valid_llm_response_with_answers(count: int = 1) -> str:
    return json.dumps(
        [
            {
                "type": "short_answer",
                "text": f"Question {i}",
                "answer": f"Answer {i}",
            }
            for i in range(count)
        ]
    )


def test_generate_with_answer_key_populates_answers(client, monkeypatch):
    monkeypatch.setattr(
        llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response_with_answers(2))
    )
    chapter = _create_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "question_types": ["short_answer"],
            "num_questions": 2,
            "include_answer_key": True,
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    questions = client.get(f"/question-sets/{question_set_id}/questions").json()
    assert all(question["answer"] for question in questions)


def test_generate_without_answer_key_never_persists_answer_even_if_model_returns_one(
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
            "question_types": ["short_answer"],
            "num_questions": 1,
            "include_answer_key": False,
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    questions = client.get(f"/question-sets/{question_set_id}/questions").json()
    assert questions[0]["answer"] is None


def test_generate_with_answer_key_fails_when_model_omits_answer(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    chapter = _create_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "question_types": ["mcq"],
            "num_questions": 1,
            "include_answer_key": True,
        },
    )
    question_set_id = response.json()["id"]

    fetched = client.get(f"/question-sets/{question_set_id}").json()
    assert fetched["status"] == "failed"


def test_list_question_sets_for_chapter(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    chapter = _create_chapter(client)
    client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )

    response = client.get(f"/chapters/{chapter['id']}/question-sets")
    assert response.status_code == 200
    assert len(response.json()) == 1
