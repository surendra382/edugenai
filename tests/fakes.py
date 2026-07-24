from pathlib import Path


class StubOCRProvider:
    def __init__(self, text: str = "stub extracted text", should_fail: bool = False):
        self.text = text
        self.should_fail = should_fail

    def extract_text(self, file_path: Path, file_type: str) -> str:
        if self.should_fail:
            raise RuntimeError("stub OCR failure")
        return self.text


class StubEmbeddingProvider:
    def __init__(self, dimension: int = 8, should_fail: bool = False):
        self.dimension = dimension
        self.should_fail = should_fail

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.should_fail:
            raise RuntimeError("stub embedding failure")
        return [[float(index)] * self.dimension for index in range(len(texts))]


class StubLLMProvider:
    def __init__(self, response: str = "stub response", should_fail: bool = False):
        self.response = response
        self.should_fail = should_fail

    def generate(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        if self.should_fail:
            raise RuntimeError("stub LLM failure")
        return self.response


class QueuedLLMProvider:
    """Returns one response per call, in order — for tests where the pipeline
    makes multiple sequential LLM calls (e.g. one per selected chapter) that
    each need a different response."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[str] = []

    def generate(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("QueuedLLMProvider exhausted")
        return self.responses.pop(0)
