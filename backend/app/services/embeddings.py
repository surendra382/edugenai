from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbeddingProvider:
    """Default embedding engine: a local BGE model via sentence-transformers, per
    the SRS's cost-conscious v1 stack. The model is loaded lazily on first use
    so importing this module (as every test does, transitively) never triggers
    a download — tests swap in a stub before any real embed() call happens.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self._model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._get_model().encode(texts).tolist()


embedding_provider: EmbeddingProvider = SentenceTransformerEmbeddingProvider()
