class StubLLMProvider:
    def __init__(self, response: str = "stub response", should_fail: bool = False):
        self.response = response
        self.should_fail = should_fail

    def generate(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        if self.should_fail:
            raise RuntimeError("stub LLM failure")
        return self.response


class StubVisionExtractor:
    def __init__(self, response: str = "[]", should_fail: bool = False):
        self.response = response
        self.should_fail = should_fail

    def extract_raw(self, image_bytes: bytes, mime_type: str) -> str:
        if self.should_fail:
            raise RuntimeError("stub vision extraction failure")
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
