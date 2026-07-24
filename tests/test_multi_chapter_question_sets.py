import json

from fakes import QueuedLLMProvider, StubLLMProvider

from backend.app.services import llm as llm_module


def _create_subject(client, name: str = "Mathematics") -> dict:
    return client.post("/subjects", json={"name": name}).json()


def _create_chapter(client, subject_id: int, name: str) -> dict:
    return client.post(f"/subjects/{subject_id}/chapters", json={"name": name}).json()


def _mcq_response(count: int, prefix: str) -> str:
    return json.dumps(
        [
            {"type": "mcq", "text": f"{prefix} Question {i}", "options": ["A", "B", "C", "D"]}
            for i in range(count)
        ]
    )


def test_multi_chapter_generation_orders_by_chapter_order_and_tags_chapter_id(client, monkeypatch):
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")
    geometry = _create_chapter(client, subject["id"], "Geometry")

    # Algebra (order 0) responds first, Geometry (order 1) second, regardless
    # of the order chapters are listed in the request payload below.
    monkeypatch.setattr(
        llm_module,
        "llm_provider",
        QueuedLLMProvider([_mcq_response(3, "Algebra"), _mcq_response(2, "Geometry")]),
    )

    response = client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [
                {"chapter_id": geometry["id"], "num_questions": 2},
                {"chapter_id": algebra["id"], "num_questions": 3},
            ],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    assert response.status_code == 202
    body = response.json()
    question_set_id = body["id"]
    assert body["subject_id"] == subject["id"]
    assert body["chapter_id"] is None
    assert body["num_questions"] == 5
    breakdown = {c["chapter_id"]: c["num_questions"] for c in body["chapters"]}
    assert breakdown == {algebra["id"]: 3, geometry["id"]: 2}

    fetched = client.get(f"/question-sets/{question_set_id}").json()
    assert fetched["status"] == "completed"

    questions = client.get(f"/question-sets/{question_set_id}/questions").json()
    assert len(questions) == 5
    assert [q["question_index"] for q in questions] == [0, 1, 2, 3, 4]
    # Algebra's 3 questions come first (Chapter.order 0), Geometry's 2 after.
    assert [q["chapter_id"] for q in questions] == [algebra["id"]] * 3 + [geometry["id"]] * 2
    assert all("Algebra" in q["text"] for q in questions[:3])
    assert all("Geometry" in q["text"] for q in questions[3:])


def test_multi_chapter_generation_fails_whole_set_when_one_chapter_fails(client, monkeypatch):
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")
    geometry = _create_chapter(client, subject["id"], "Geometry")

    monkeypatch.setattr(
        llm_module,
        "llm_provider",
        QueuedLLMProvider([_mcq_response(1, "Algebra"), "not valid json"]),
    )

    response = client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [
                {"chapter_id": algebra["id"], "num_questions": 1},
                {"chapter_id": geometry["id"], "num_questions": 1},
            ],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    question_set_id = response.json()["id"]

    fetched = client.get(f"/question-sets/{question_set_id}").json()
    assert fetched["status"] == "failed"
    assert "Geometry" in fetched["generation_error"]

    questions = client.get(f"/question-sets/{question_set_id}/questions").json()
    assert questions == []


def test_single_chapter_selected_via_multi_endpoint_populates_chapter_id(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(2, "Algebra")))
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")

    response = client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [{"chapter_id": algebra["id"], "num_questions": 2}],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    body = response.json()
    assert body["chapter_id"] == algebra["id"]
    assert len(body["chapters"]) == 1


def test_existing_single_chapter_endpoint_still_creates_one_chapter_breakdown_row(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(1, "Algebra")))
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")

    response = client.post(
        f"/chapters/{algebra['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    body = response.json()
    assert body["subject_id"] == subject["id"]
    assert body["chapter_id"] == algebra["id"]
    assert body["chapters"] == [
        {"chapter_id": algebra["id"], "chapter_name": "Algebra", "num_questions": 1}
    ]


def test_multi_chapter_create_rejects_duplicate_chapter_ids(client):
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")

    response = client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [
                {"chapter_id": algebra["id"], "num_questions": 1},
                {"chapter_id": algebra["id"], "num_questions": 2},
            ],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    assert response.status_code == 400


def test_multi_chapter_create_rejects_chapter_from_other_subject(client):
    subject_a = _create_subject(client, "Mathematics")
    subject_b = _create_subject(client, "Science")
    chapter_b = _create_chapter(client, subject_b["id"], "Force")

    response = client.post(
        f"/subjects/{subject_a['id']}/question-sets",
        json={
            "chapters": [{"chapter_id": chapter_b["id"], "num_questions": 1}],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    assert response.status_code == 400


def test_multi_chapter_create_rejects_empty_chapters(client):
    subject = _create_subject(client)
    response = client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={"chapters": [], "difficulty": "easy", "question_types": ["mcq"]},
    )
    assert response.status_code == 422


def test_multi_chapter_create_rejects_total_over_cap(client):
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")
    geometry = _create_chapter(client, subject["id"], "Geometry")

    response = client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [
                {"chapter_id": algebra["id"], "num_questions": 30},
                {"chapter_id": geometry["id"], "num_questions": 31},
            ],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    assert response.status_code == 422


def test_multi_chapter_create_on_nonexistent_subject_returns_404(client):
    response = client.post(
        "/subjects/999/question-sets",
        json={
            "chapters": [{"chapter_id": 1, "num_questions": 1}],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    assert response.status_code == 404


def test_history_includes_multi_chapter_set_with_null_chapter_name(client, monkeypatch):
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")
    geometry = _create_chapter(client, subject["id"], "Geometry")

    monkeypatch.setattr(
        llm_module,
        "llm_provider",
        QueuedLLMProvider([_mcq_response(1, "Algebra"), _mcq_response(1, "Geometry")]),
    )
    client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [
                {"chapter_id": algebra["id"], "num_questions": 1},
                {"chapter_id": geometry["id"], "num_questions": 1},
            ],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )

    response = client.get("/question-sets", params={"subject_id": subject["id"]})
    body = response.json()
    assert len(body) == 1
    assert body[0]["chapter_name"] is None
    assert body[0]["subject_name"] == "Mathematics"
    breakdown = {c["chapter_id"]: c["num_questions"] for c in body[0]["chapters"]}
    assert breakdown == {algebra["id"]: 1, geometry["id"]: 1}


def test_history_chapter_filter_matches_multi_chapter_sets_that_include_it(client, monkeypatch):
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")
    geometry = _create_chapter(client, subject["id"], "Geometry")

    monkeypatch.setattr(
        llm_module,
        "llm_provider",
        QueuedLLMProvider([_mcq_response(1, "Algebra"), _mcq_response(1, "Geometry")]),
    )
    client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [
                {"chapter_id": algebra["id"], "num_questions": 1},
                {"chapter_id": geometry["id"], "num_questions": 1},
            ],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )

    response = client.get("/question-sets", params={"chapter_id": geometry["id"]})
    body = response.json()
    assert len(body) == 1
    assert body[0]["chapter_name"] is None


def test_pdf_export_for_multi_chapter_set_groups_by_chapter(client, monkeypatch):
    subject = _create_subject(client)
    algebra = _create_chapter(client, subject["id"], "Algebra")
    geometry = _create_chapter(client, subject["id"], "Geometry")

    monkeypatch.setattr(
        llm_module,
        "llm_provider",
        QueuedLLMProvider([_mcq_response(1, "Algebra"), _mcq_response(1, "Geometry")]),
    )
    response = client.post(
        f"/subjects/{subject['id']}/question-sets",
        json={
            "chapters": [
                {"chapter_id": algebra["id"], "num_questions": 1},
                {"chapter_id": geometry["id"], "num_questions": 1},
            ],
            "difficulty": "easy",
            "question_types": ["mcq"],
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    pdf_response = client.get(f"/question-sets/{question_set_id}/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.content.startswith(b"%PDF")
    assert b"Algebra" in pdf_response.content
    assert b"Geometry" in pdf_response.content
