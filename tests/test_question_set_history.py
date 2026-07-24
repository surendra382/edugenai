import json

from fakes import StubLLMProvider

from backend.app.services import llm as llm_module


def _valid_llm_response(count: int = 1) -> str:
    return json.dumps(
        [{"type": "mcq", "text": f"Question {i}", "options": ["A", "B", "C", "D"]} for i in range(count)]
    )


def _get_or_create_subject(client, subject_name: str) -> dict:
    response = client.post("/subjects", json={"name": subject_name})
    if response.status_code == 409:
        return next(s for s in client.get("/subjects").json() if s["name"] == subject_name)
    return response.json()


def _create_chapter(client, subject_name: str, chapter_name: str) -> dict:
    subject = _get_or_create_subject(client, subject_name)
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": chapter_name}).json()


def _generate(client, chapter_id: int, difficulty: str = "easy") -> dict:
    response = client.post(
        f"/chapters/{chapter_id}/question-sets",
        json={"difficulty": difficulty, "question_types": ["mcq"], "num_questions": 1},
    )
    return response.json()


def test_list_all_question_sets_spans_multiple_subjects_and_chapters(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    math_chapter = _create_chapter(client, "Mathematics", "Algebra")
    science_chapter = _create_chapter(client, "Science", "Force")

    _generate(client, math_chapter["id"])
    _generate(client, science_chapter["id"])

    response = client.get("/question-sets")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    subject_names = {row["subject_name"] for row in body}
    chapter_names = {row["chapter_name"] for row in body}
    assert subject_names == {"Mathematics", "Science"}
    assert chapter_names == {"Algebra", "Force"}


def test_list_all_question_sets_newest_first(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    chapter = _create_chapter(client, "Mathematics", "Algebra")
    first = _generate(client, chapter["id"])
    second = _generate(client, chapter["id"])

    response = client.get("/question-sets")
    body = response.json()
    assert [row["id"] for row in body] == [second["id"], first["id"]]


def test_list_all_question_sets_filters_by_subject(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    math_chapter = _create_chapter(client, "Mathematics", "Algebra")
    science_chapter = _create_chapter(client, "Science", "Force")
    _generate(client, math_chapter["id"])
    _generate(client, science_chapter["id"])

    response = client.get("/question-sets", params={"subject_id": math_chapter["subject_id"]})
    body = response.json()
    assert len(body) == 1
    assert body[0]["subject_name"] == "Mathematics"


def test_list_all_question_sets_filters_by_chapter(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    chapter_a = _create_chapter(client, "Mathematics", "Algebra")
    chapter_b = _create_chapter(client, "Mathematics", "Geometry")
    _generate(client, chapter_a["id"])
    _generate(client, chapter_b["id"])

    response = client.get("/question-sets", params={"chapter_id": chapter_a["id"]})
    body = response.json()
    assert len(body) == 1
    assert body[0]["chapter_name"] == "Algebra"


def test_list_all_question_sets_filters_by_status(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response="not valid json"))
    failed_chapter = _create_chapter(client, "Mathematics", "Algebra")
    _generate(client, failed_chapter["id"])

    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    completed_chapter = _create_chapter(client, "Science", "Force")
    _generate(client, completed_chapter["id"])

    response = client.get("/question-sets", params={"status": "completed"})
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "completed"


def test_list_all_question_sets_respects_limit(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    chapter = _create_chapter(client, "Mathematics", "Algebra")
    for _ in range(3):
        _generate(client, chapter["id"])

    response = client.get("/question-sets", params={"limit": 2})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_all_question_sets_invalid_limit_returns_400(client):
    response = client.get("/question-sets", params={"limit": 0})
    assert response.status_code == 400

    response = client.get("/question-sets", params={"limit": 201})
    assert response.status_code == 400


def test_list_all_question_sets_unknown_subject_returns_empty_list(client):
    response = client.get("/question-sets", params={"subject_id": 999})
    assert response.status_code == 200
    assert response.json() == []


def test_list_all_question_sets_empty_when_none_generated(client):
    response = client.get("/question-sets")
    assert response.status_code == 200
    assert response.json() == []
