from pathlib import Path

import pytest
from fakes import StubOCRProvider

from backend.app.api.documents import _can_retry_ocr
from backend.app.services import ocr as ocr_module


def test_stub_ocr_provider_returns_configured_text():
    provider = StubOCRProvider(text="abc")
    assert provider.extract_text(Path("whatever.png"), "image") == "abc"


def test_stub_ocr_provider_raises_when_configured_to_fail():
    provider = StubOCRProvider(should_fail=True)
    with pytest.raises(RuntimeError):
        provider.extract_text(Path("whatever.png"), "image")


def test_can_retry_ocr_only_when_failed():
    assert _can_retry_ocr("ocr_failed") is True
    assert _can_retry_ocr("ocr_processing") is False
    assert _can_retry_ocr("ocr_done") is False
    assert _can_retry_ocr("uploaded") is False


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()


def _upload(client, chapter_id: int) -> dict:
    return client.post(
        f"/chapters/{chapter_id}/documents",
        data={"material_type": "textbook_page"},
        files={"file": ("page.png", b"fake-image-bytes", "image/png")},
    ).json()


def test_upload_triggers_ocr_and_text_is_retrievable(client, monkeypatch):
    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(text="hello world"))
    chapter = _create_chapter(client)

    uploaded = _upload(client, chapter["id"])
    assert uploaded["status"] == "ocr_processing"

    fetched = client.get(f"/documents/{uploaded['id']}").json()
    assert fetched["status"] == "embedded"

    text_response = client.get(f"/documents/{uploaded['id']}/text")
    assert text_response.status_code == 200
    assert text_response.json()["text"] == "hello world"


def test_ocr_failure_sets_status_and_error(client, monkeypatch):
    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(should_fail=True))
    chapter = _create_chapter(client)

    uploaded = _upload(client, chapter["id"])
    fetched = client.get(f"/documents/{uploaded['id']}").json()

    assert fetched["status"] == "ocr_failed"
    assert fetched["ocr_error"]


def test_retry_recovers_failed_document(client, monkeypatch):
    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(should_fail=True))
    chapter = _create_chapter(client)
    uploaded = _upload(client, chapter["id"])
    assert client.get(f"/documents/{uploaded['id']}").json()["status"] == "ocr_failed"

    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(text="recovered text"))
    retry_response = client.post(f"/documents/{uploaded['id']}/ocr/retry")
    assert retry_response.status_code == 202
    assert retry_response.json()["status"] == "ocr_processing"

    fetched = client.get(f"/documents/{uploaded['id']}").json()
    assert fetched["status"] == "embedded"
    assert fetched["ocr_error"] is None


def test_retry_rejected_when_not_failed(client):
    chapter = _create_chapter(client)
    uploaded = _upload(client, chapter["id"])  # default stub succeeds -> embedded

    response = client.post(f"/documents/{uploaded['id']}/ocr/retry")
    assert response.status_code == 409


def test_retry_nonexistent_document_returns_404(client):
    response = client.post("/documents/999/ocr/retry")
    assert response.status_code == 404


def test_get_text_when_ocr_not_successfully_completed_returns_409(client, monkeypatch):
    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(should_fail=True))
    chapter = _create_chapter(client)
    uploaded = _upload(client, chapter["id"])

    response = client.get(f"/documents/{uploaded['id']}/text")
    assert response.status_code == 409


def test_get_text_for_nonexistent_document_returns_404(client):
    response = client.get("/documents/999/text")
    assert response.status_code == 404
