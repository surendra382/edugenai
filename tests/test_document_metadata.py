import pytest
from pydantic import ValidationError

from backend.app.schemas.document_metadata import DocumentMetadataUpdate


def test_schema_rejects_difficulty_outside_allowed_values():
    with pytest.raises(ValidationError):
        DocumentMetadataUpdate(difficulty="extreme")


def _create_subject_chapter_and_document(client) -> dict:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    chapter = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()
    document = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "notes"},
        files={"file": ("notes.png", b"data", "image/png")},
    ).json()
    return document


def test_upload_document_auto_creates_empty_metadata(client):
    document = _create_subject_chapter_and_document(client)

    response = client.get(f"/documents/{document['id']}/metadata")
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document["id"]
    assert body["board"] is None
    assert body["difficulty"] is None


def test_update_metadata_fields_reflected_in_subsequent_get(client):
    document = _create_subject_chapter_and_document(client)

    update_response = client.put(
        f"/documents/{document['id']}/metadata",
        json={
            "board": "CBSE",
            "class_level": "8",
            "keywords": "algebra, equations",
            "learning_objectives": "Solve linear equations",
            "question_types": "Multiple Choice Questions, Short Answer",
            "difficulty": "medium",
            "source": "NCERT Textbook",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["board"] == "CBSE"
    assert update_response.json()["difficulty"] == "medium"

    get_response = client.get(f"/documents/{document['id']}/metadata")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["board"] == "CBSE"
    assert body["class_level"] == "8"
    assert body["difficulty"] == "medium"
    assert body["source"] == "NCERT Textbook"


def test_update_metadata_for_nonexistent_document_returns_404(client):
    response = client.put("/documents/999/metadata", json={"board": "CBSE"})
    assert response.status_code == 404


def test_get_metadata_for_nonexistent_document_returns_404(client):
    response = client.get("/documents/999/metadata")
    assert response.status_code == 404


def test_update_metadata_with_invalid_difficulty_returns_422(client):
    document = _create_subject_chapter_and_document(client)

    response = client.put(
        f"/documents/{document['id']}/metadata", json={"difficulty": "extreme"}
    )
    assert response.status_code == 422
