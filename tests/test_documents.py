from pathlib import Path

from backend.app.api.documents import _exceeds_max_size, _infer_file_type
from backend.app.core.config import settings


def test_infer_file_type_rejects_disallowed_extension():
    assert _infer_file_type("virus.exe") is None


def test_infer_file_type_accepts_images_and_pdfs():
    assert _infer_file_type("page.PNG") == "image"
    assert _infer_file_type("page.jpg") == "image"
    assert _infer_file_type("sheet.pdf") == "pdf"


def test_exceeds_max_size_true_when_over_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    assert _exceeds_max_size(2 * 1024 * 1024) is True


def test_exceeds_max_size_false_when_within_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    assert _exceeds_max_size(1024) is False


def _create_subject_and_chapter(client) -> tuple[dict, dict]:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    chapter = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()
    return subject, chapter


def test_upload_valid_image_returns_201_and_appears_in_list(client):
    _, chapter = _create_subject_and_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "textbook_page"},
        files={"file": ("page1.png", b"fake-image-bytes", "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["file_type"] == "image"
    assert body["material_type"] == "textbook_page"
    assert body["status"] == "ocr_processing"

    list_response = client.get(f"/chapters/{chapter['id']}/documents")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    stored_files = list(Path(settings.knowledge_base_dir).rglob("*.png"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == b"fake-image-bytes"


def test_upload_valid_pdf_returns_201(client):
    _, chapter = _create_subject_and_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "worksheet"},
        files={"file": ("sheet.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["file_type"] == "pdf"


def test_upload_under_nonexistent_chapter_returns_404(client):
    response = client.post(
        "/chapters/999/documents",
        data={"material_type": "worksheet"},
        files={"file": ("sheet.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 404


def test_upload_disallowed_file_type_returns_415(client):
    _, chapter = _create_subject_and_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "worksheet"},
        files={"file": ("virus.exe", b"binary", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_upload_oversized_file_returns_413(client, monkeypatch):
    _, chapter = _create_subject_and_chapter(client)
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)

    response = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "worksheet"},
        files={"file": ("sheet.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 413


def test_delete_document_removes_row_and_file(client):
    _, chapter = _create_subject_and_chapter(client)
    created = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "worksheet"},
        files={"file": ("sheet.pdf", b"%PDF-1.4 fake", "application/pdf")},
    ).json()

    assert len(list(Path(settings.knowledge_base_dir).rglob("*.pdf"))) == 1

    response = client.delete(f"/documents/{created['id']}")
    assert response.status_code == 204

    list_response = client.get(f"/chapters/{chapter['id']}/documents")
    assert list_response.json() == []
    assert len(list(Path(settings.knowledge_base_dir).rglob("*.pdf"))) == 0


def test_delete_nonexistent_document_returns_404(client):
    response = client.delete("/documents/999")
    assert response.status_code == 404


def test_delete_document_removes_metadata_and_chunks(client):
    _, chapter = _create_subject_and_chapter(client)
    created = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "notes"},
        files={"file": ("notes.png", b"data", "image/png")},
    ).json()
    assert client.get(f"/documents/{created['id']}/metadata").status_code == 200

    response = client.delete(f"/documents/{created['id']}")
    assert response.status_code == 204

    assert client.get(f"/documents/{created['id']}/metadata").status_code == 404
    assert client.get(f"/documents/{created['id']}/chunks").status_code == 404


def test_reupload_after_deleting_only_document_succeeds(client):
    """SQLite reuses the freed id once a table is empty; the recreated
    document's auto-created DocumentMetadata row would collide with an
    orphaned row left behind by an incomplete delete.
    """
    _, chapter = _create_subject_and_chapter(client)
    first = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "notes"},
        files={"file": ("first.png", b"data", "image/png")},
    ).json()
    client.delete(f"/documents/{first['id']}")

    second_response = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "notes"},
        files={"file": ("second.png", b"data", "image/png")},
    )
    assert second_response.status_code == 201


def test_get_document_by_id(client):
    _, chapter = _create_subject_and_chapter(client)
    created = client.post(
        f"/chapters/{chapter['id']}/documents",
        data={"material_type": "notes"},
        files={"file": ("notes.png", b"data", "image/png")},
    ).json()

    response = client.get(f"/documents/{created['id']}")
    assert response.status_code == 200
    assert response.json()["original_filename"] == "notes.png"


def test_get_nonexistent_document_returns_404(client):
    response = client.get("/documents/999")
    assert response.status_code == 404
