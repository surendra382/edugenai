import pytest
from fakes import StubLLMProvider

from backend.app.core.config import settings
from backend.app.services import llm as llm_module
from backend.app.services.llm import OpenAICompatibleLLMProvider


def test_stub_llm_provider_returns_configured_response():
    provider = StubLLMProvider(response="hello")
    assert provider.generate("any prompt") == "hello"


def test_stub_llm_provider_raises_when_configured_to_fail():
    provider = StubLLMProvider(should_fail=True)
    with pytest.raises(RuntimeError):
        provider.generate("any prompt")


def test_openai_compatible_provider_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    provider = OpenAICompatibleLLMProvider()
    with pytest.raises(RuntimeError):
        provider.generate("any prompt")


def test_llm_health_ok_when_provider_succeeds(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider())
    response = client.get("/llm/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_llm_health_unavailable_when_provider_fails(client, monkeypatch):
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(should_fail=True))
    response = client.get("/llm/health")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
