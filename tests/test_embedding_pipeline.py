import pytest
from fakes import StubEmbeddingProvider, StubOCRProvider

from backend.app.api.documents import _can_retry_embedding
from backend.app.services import embeddings as embeddings_module
from backend.app.services import ocr as ocr_module
from backend.app.services.vector_store import get_collection


def test_stub_embedding_provider_returns_fixed_length_vectors():
    provider = StubEmbeddingProvider(dimension=4)
    vectors = provider.embed(["a", "b"])
    assert len(vectors) == 2
    assert all(len(vector) == 4 for vector in vectors)


def test_stub_embedding_provider_raises_when_configured_to_fail():
    provider = StubEmbeddingProvider(should_fail=True)
    with pytest.raises(RuntimeError):
        provider.embed(["a"])


def test_can_retry_embedding_only_when_failed():
    assert _can_retry_embedding("embedding_failed") is True
    assert _can_retry_embedding("embedding_processing") is False
    assert _can_retry_embedding("embedded") is False
    assert _can_retry_embedding("ocr_done") is False


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()


def _upload(client, chapter_id: int) -> dict:
    return client.post(
        f"/chapters/{chapter_id}/documents",
        data={"material_type": "textbook_page"},
        files={"file": ("page.png", b"fake-image-bytes", "image/png")},
    ).json()


def test_document_reaching_ocr_done_triggers_embedding(client, monkeypatch):
    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(text="hello world"))
    chapter = _create_chapter(client)

    uploaded = _upload(client, chapter["id"])
    fetched = client.get(f"/documents/{uploaded['id']}").json()
    assert fetched["status"] == "embedded"

    chunks_response = client.get(f"/documents/{uploaded['id']}/chunks")
    assert chunks_response.status_code == 200
    chunks = chunks_response.json()
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["text"] == "hello world"


def test_get_chunks_for_nonexistent_document_returns_404(client):
    response = client.get("/documents/999/chunks")
    assert response.status_code == 404


def test_embedding_failure_sets_status_and_error(client, monkeypatch):
    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(text="some text"))
    monkeypatch.setattr(
        embeddings_module, "embedding_provider", StubEmbeddingProvider(should_fail=True)
    )
    chapter = _create_chapter(client)

    uploaded = _upload(client, chapter["id"])
    fetched = client.get(f"/documents/{uploaded['id']}").json()

    assert fetched["status"] == "embedding_failed"
    assert fetched["embedding_error"]


def test_retry_embedding_recovers(client, monkeypatch):
    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(text="some text"))
    monkeypatch.setattr(
        embeddings_module, "embedding_provider", StubEmbeddingProvider(should_fail=True)
    )
    chapter = _create_chapter(client)
    uploaded = _upload(client, chapter["id"])
    assert client.get(f"/documents/{uploaded['id']}").json()["status"] == "embedding_failed"

    monkeypatch.setattr(embeddings_module, "embedding_provider", StubEmbeddingProvider())
    retry_response = client.post(f"/documents/{uploaded['id']}/embeddings/retry")
    assert retry_response.status_code == 202

    fetched = client.get(f"/documents/{uploaded['id']}").json()
    assert fetched["status"] == "embedded"
    assert fetched["embedding_error"] is None


def test_retry_embedding_rejected_when_not_failed(client):
    chapter = _create_chapter(client)
    uploaded = _upload(client, chapter["id"])  # default stub succeeds -> embedded

    response = client.post(f"/documents/{uploaded['id']}/embeddings/retry")
    assert response.status_code == 409


def test_retry_embedding_nonexistent_document_returns_404(client):
    response = client.post("/documents/999/embeddings/retry")
    assert response.status_code == 404


def test_chroma_collection_contains_vector_with_correct_metadata(client):
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    chapter = client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()
    uploaded = _upload(client, chapter["id"])

    collection = get_collection()
    result = collection.get(ids=[f"document-{uploaded['id']}-chunk-0"], include=["metadatas"])

    assert result["metadatas"][0]["document_id"] == uploaded["id"]
    assert result["metadatas"][0]["chapter_id"] == chapter["id"]
    assert result["metadatas"][0]["subject_id"] == subject["id"]
    assert result["metadatas"][0]["material_type"] == "textbook_page"
