import json

import pytest
from fakes import StubVisionExtractor
from pydantic import ValidationError

from backend.app.schemas.chapter import ChapterCreate
from backend.app.services import vision_extractor as vision_extractor_module


def test_schema_rejects_empty_name():
    with pytest.raises(ValidationError):
        ChapterCreate(name="")


def test_schema_rejects_whitespace_only_name():
    with pytest.raises(ValidationError):
        ChapterCreate(name="   ")


def test_new_chapter_defaults_order_to_max_plus_one(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()

    first = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()
    second = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Geometry"}).json()

    assert first["order"] == 0
    assert second["order"] == 1


def test_create_chapter_under_subject_returns_201_and_appears_in_list(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()

    response = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"})
    assert response.status_code == 201
    assert response.json()["name"] == "Algebra"

    list_response = client.get(f"/subjects/{subject['id']}/chapters")
    assert list_response.status_code == 200
    assert "Algebra" in [c["name"] for c in list_response.json()]


def test_create_chapter_under_nonexistent_subject_returns_404(client):
    response = client.post("/subjects/999/chapters", json={"name": "Algebra"})
    assert response.status_code == 404


def test_create_duplicate_name_within_same_subject_returns_409(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"})

    response = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"})
    assert response.status_code == 409


def test_same_chapter_name_under_different_subject_allowed(client):
    subject_a = client.post("/subjects", json={"name": "Mathematics"}).json()
    subject_b = client.post("/subjects", json={"name": "Science"}).json()
    client.post(f"/subjects/{subject_a['id']}/chapters", json={"name": "Chapter 1"})

    response = client.post(f"/subjects/{subject_b['id']}/chapters", json={"name": "Chapter 1"})
    assert response.status_code == 201


def test_update_chapter_name(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    chapter = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()

    response = client.put(f"/chapters/{chapter['id']}", json={"name": "Advanced Algebra"})
    assert response.status_code == 200
    assert response.json()["name"] == "Advanced Algebra"

    list_response = client.get(f"/subjects/{subject['id']}/chapters")
    assert "Advanced Algebra" in [c["name"] for c in list_response.json()]


def test_delete_chapter_removes_and_keeps_valid_order(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    first = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Ch1"}).json()
    second = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Ch2"}).json()
    third = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Ch3"}).json()

    response = client.delete(f"/chapters/{second['id']}")
    assert response.status_code == 204

    remaining = client.get(f"/subjects/{subject['id']}/chapters").json()
    assert [c["id"] for c in remaining] == [first["id"], third["id"]]
    assert remaining[0]["order"] < remaining[1]["order"]


def test_delete_chapter_with_question_bank_items_returns_409(client, monkeypatch):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    chapter = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()

    monkeypatch.setattr(
        vision_extractor_module,
        "vision_extractor",
        StubVisionExtractor(
            response=json.dumps(
                [
                    {
                        "question_type": "mcq",
                        "stem": "2+2=?",
                        "concept": "addition",
                        "options": ["3", "4", "5", "6"],
                        "answer": "4",
                        "difficulty": "easy",
                    }
                ]
            )
        ),
    )
    client.post(
        f"/chapters/{chapter['id']}/question-bank/import",
        data={"class_grade": "8", "source": "unknown"},
        files={"images": ("page1.png", b"fake-image-bytes", "image/png")},
    )

    response = client.delete(f"/chapters/{chapter['id']}")
    assert response.status_code == 409

    still_there = client.get(f"/chapters/{chapter['id']}")
    assert still_there.status_code == 200


def test_reorder_submit_new_order_reflected_in_get(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    first = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Ch1"}).json()
    second = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Ch2"}).json()
    third = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Ch3"}).json()

    new_order = [third["id"], first["id"], second["id"]]
    response = client.patch(f"/subjects/{subject['id']}/chapters/reorder", json={"ordered_ids": new_order})
    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == new_order

    list_response = client.get(f"/subjects/{subject['id']}/chapters")
    assert [c["id"] for c in list_response.json()] == new_order


def test_reorder_with_id_not_belonging_to_subject_returns_400(client):
    subject_a = client.post("/subjects", json={"name": "Mathematics"}).json()
    subject_b = client.post("/subjects", json={"name": "Science"}).json()
    chapter_a = client.post(f"/subjects/{subject_a['id']}/chapters", json={"name": "Ch1"}).json()
    chapter_b = client.post(f"/subjects/{subject_b['id']}/chapters", json={"name": "Ch1"}).json()

    response = client.patch(
        f"/subjects/{subject_a['id']}/chapters/reorder",
        json={"ordered_ids": [chapter_a["id"], chapter_b["id"]]},
    )
    assert response.status_code == 400


def test_delete_subject_with_chapters_returns_409(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"})

    response = client.delete(f"/subjects/{subject['id']}")
    assert response.status_code == 409

    still_there = client.get(f"/subjects/{subject['id']}")
    assert still_there.status_code == 200
