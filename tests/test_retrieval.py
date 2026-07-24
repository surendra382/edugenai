import pytest
from fakes import StubOCRProvider

from backend.app.services import embeddings as embeddings_module
from backend.app.services import ocr as ocr_module
from backend.app.services.retriever import reciprocal_rank_fusion


def test_reciprocal_rank_fusion_combines_deterministically():
    semantic_ranked = [1, 2, 3]
    keyword_ranked = [2, 1, 4]

    scores = reciprocal_rank_fusion([semantic_ranked, keyword_ranked], k=60)

    assert scores[1] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[2] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[3] == pytest.approx(1 / 63)
    assert scores[4] == pytest.approx(1 / 63)
    assert scores[1] == scores[2]
    assert set(scores) == {1, 2, 3, 4}


def test_reciprocal_rank_fusion_empty_lists_returns_empty_scores():
    assert reciprocal_rank_fusion([[], []]) == {}


class ZeroEmbeddingProvider:
    """All texts map to the same vector, making semantic ranking uninformative
    so tests can prove the keyword path surfaces results independently.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0, 0.0] for _ in texts]


class MappingEmbeddingProvider:
    def __init__(self, mapping: dict[str, list[float]], default: list[float]):
        self.mapping = mapping
        self.default = default

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.mapping.get(text, self.default) for text in texts]


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Biology"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Cells"}).json()


def _upload(client, chapter_id: int, filename: str = "page.png") -> dict:
    return client.post(
        f"/chapters/{chapter_id}/documents",
        data={"material_type": "textbook_page"},
        files={"file": (filename, b"fake-image-bytes", "image/png")},
    ).json()


def test_search_returns_keyword_match_when_semantic_scores_are_uninformative(client, monkeypatch):
    monkeypatch.setattr(embeddings_module, "embedding_provider", ZeroEmbeddingProvider())
    chapter = _create_chapter(client)

    monkeypatch.setattr(
        ocr_module, "ocr_provider", StubOCRProvider(text="The mitochondria is the powerhouse of the cell")
    )
    target = _upload(client, chapter["id"], "target.png")

    monkeypatch.setattr(
        ocr_module, "ocr_provider", StubOCRProvider(text="Unrelated filler distractor content one")
    )
    _upload(client, chapter["id"], "filler1.png")

    monkeypatch.setattr(
        ocr_module, "ocr_provider", StubOCRProvider(text="Another unrelated distractor passage two")
    )
    _upload(client, chapter["id"], "filler2.png")

    response = client.get(
        f"/chapters/{chapter['id']}/search",
        params={"q": "mitochondria is the powerhouse"},
    )
    assert response.status_code == 200
    results = response.json()
    assert any(result["document_id"] == target["id"] for result in results)


def test_search_returns_semantic_match_for_paraphrase_with_no_keyword_overlap(client, monkeypatch):
    photosynthesis_text = "Photosynthesis converts sunlight into chemical energy"
    paraphrase_query = "How do plants turn light into usable energy"
    close_vector = [1.0, 0.0, 0.0, 0.0]
    far_vector = [0.0, 1.0, 0.0, 0.0]

    mapping = {
        photosynthesis_text: close_vector,
        paraphrase_query: close_vector,
    }
    monkeypatch.setattr(
        embeddings_module, "embedding_provider", MappingEmbeddingProvider(mapping, default=far_vector)
    )
    chapter = _create_chapter(client)

    monkeypatch.setattr(ocr_module, "ocr_provider", StubOCRProvider(text=photosynthesis_text))
    target = _upload(client, chapter["id"], "target.png")

    monkeypatch.setattr(
        ocr_module, "ocr_provider", StubOCRProvider(text="Completely unrelated filler passage")
    )
    _upload(client, chapter["id"], "filler.png")

    response = client.get(
        f"/chapters/{chapter['id']}/search",
        params={"q": paraphrase_query},
    )
    assert response.status_code == 200
    results = response.json()
    assert any(result["document_id"] == target["id"] for result in results)


def test_search_scoped_to_chapter_with_no_chunks_returns_empty_list(client):
    chapter = _create_chapter(client)
    response = client.get(f"/chapters/{chapter['id']}/search", params={"q": "anything"})
    assert response.status_code == 200
    assert response.json() == []


def test_search_on_nonexistent_chapter_returns_404(client):
    response = client.get("/chapters/999/search", params={"q": "anything"})
    assert response.status_code == 404
