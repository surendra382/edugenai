import pytest
from pydantic import ValidationError

from backend.app.schemas.subject import SubjectCreate


def test_schema_rejects_empty_name():
    with pytest.raises(ValidationError):
        SubjectCreate(name="")


def test_schema_rejects_whitespace_only_name():
    with pytest.raises(ValidationError):
        SubjectCreate(name="   ")


def test_create_subject_returns_201_and_appears_in_list(client):
    response = client.post("/subjects", json={"name": "Mathematics"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Mathematics"
    assert "id" in body

    list_response = client.get("/subjects")
    assert list_response.status_code == 200
    assert "Mathematics" in [s["name"] for s in list_response.json()]


def test_create_duplicate_name_case_insensitive_returns_409(client):
    client.post("/subjects", json={"name": "Science"})
    response = client.post("/subjects", json={"name": "science"})
    assert response.status_code == 409


def test_list_subjects_sorted_by_name(client):
    client.post("/subjects", json={"name": "Zoology"})
    client.post("/subjects", json={"name": "Algebra"})

    response = client.get("/subjects")
    names = [s["name"] for s in response.json()]
    assert names == sorted(names)


def test_get_subject_by_id(client):
    created = client.post("/subjects", json={"name": "History"}).json()
    response = client.get(f"/subjects/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "History"


def test_get_nonexistent_subject_returns_404(client):
    response = client.get("/subjects/999")
    assert response.status_code == 404


def test_update_subject_name(client):
    created = client.post("/subjects", json={"name": "Geography"}).json()
    response = client.put(f"/subjects/{created['id']}", json={"name": "Geo"})
    assert response.status_code == 200
    assert response.json()["name"] == "Geo"

    fetched = client.get(f"/subjects/{created['id']}")
    assert fetched.json()["name"] == "Geo"


def test_update_subject_name_collision_returns_409(client):
    client.post("/subjects", json={"name": "Physics"})
    other = client.post("/subjects", json={"name": "Chemistry"}).json()

    response = client.put(f"/subjects/{other['id']}", json={"name": "physics"})
    assert response.status_code == 409


def test_update_nonexistent_subject_returns_404(client):
    response = client.put("/subjects/999", json={"name": "Anything"})
    assert response.status_code == 404


def test_delete_subject_with_no_chapters(client):
    created = client.post("/subjects", json={"name": "Biology"}).json()
    response = client.delete(f"/subjects/{created['id']}")
    assert response.status_code == 204

    list_response = client.get("/subjects")
    assert "Biology" not in [s["name"] for s in list_response.json()]


def test_delete_nonexistent_subject_returns_404(client):
    response = client.delete("/subjects/999")
    assert response.status_code == 404
