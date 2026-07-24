import time
from typing import Protocol

import requests

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class LLMProvider(Protocol):
    def generate(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 2048) -> str: ...


class OpenAICompatibleLLMProvider:
    """Default LLM engine: any hosted API implementing OpenAI's
    chat-completions wire format (Groq, OpenAI itself, OpenRouter, Together,
    Fireworks, a local Ollama/vLLM server in OpenAI-compat mode, ...).
    Which provider is actually called is entirely a config choice
    (`llm_base_url` / `llm_api_key` / `llm_model` in Settings) rather than a
    code choice, since they all speak the same protocol — swapping vendors
    never requires a new provider class. Settings are read lazily on each
    call so importing this module never requires network access; tests swap
    in a stub before any real generate() call happens.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    def generate(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        api_key = self._api_key if self._api_key is not None else settings.llm_api_key
        model = self._model if self._model is not None else settings.llm_model
        base_url = self._base_url if self._base_url is not None else settings.llm_base_url

        if not api_key:
            raise RuntimeError("LLM API key is not configured")

        logger.info(
            "llm.request",
            extra={
                "event": "llm.request",
                "model": model,
                "base_url": base_url,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "prompt_char_len": len(prompt),
            },
        )

        started_at = time.perf_counter()
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=settings.llm_request_timeout_seconds,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {})
        content = body["choices"][0]["message"]["content"]

        logger.info(
            "llm.response",
            extra={
                "event": "llm.response",
                "model": model,
                "http_status": response.status_code,
                "latency_ms": round(latency_ms, 2),
                "response_char_len": len(content),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        )
        return content


llm_provider: LLMProvider = OpenAICompatibleLLMProvider()
