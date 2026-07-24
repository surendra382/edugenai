# Feature: LLM Provider Integration (OpenAI-compatible)

**Phase:** 3 — AI Question Generator
**ID:** phase3-f01
**Status:** Done
**Depends on:** —

> **Update (Phase 5):** originally shipped as a Groq-specific
> `GroqLLMProvider`. Generalized to `OpenAICompatibleLLMProvider`, driven
> entirely by config (`llm_api_key`/`llm_model`/`llm_base_url`), since Groq,
> OpenAI, and most other hosted-model APIs already speak the same
> chat-completions wire format — switching vendor is now a `.env` change,
> not a code change. Defaults are unchanged (still Groq,
> `llama-3.3-70b-versatile`).

---

## 1. Goal

The backend can call a real LLM through a swappable `LLMProvider` interface,
with a lightweight health check to confirm connectivity — the foundation the
Question Generator (phase3-f02) builds on. No question-generation logic yet.

## 2. Scope

### In Scope
- `LLMProvider` behind a `typing.Protocol`, same swappable pattern as
  `EmbeddingProvider`/`OCRProvider`: `generate(prompt, *, temperature=0.7,
  max_tokens=2048) -> str`
- `OpenAICompatibleLLMProvider`: calls any OpenAI-compatible
  `chat/completions` REST API (Groq, OpenAI, OpenRouter, Together,
  Fireworks, a local Ollama/vLLM server in OpenAI-compat mode, ...) via
  plain `requests` (already a dependency — no new package needed), lazily
  reading config on each call so importing the module never touches the
  network
- Config: `llm_api_key`, `llm_model` (default `llama-3.3-70b-versatile`),
  `llm_base_url` (default `https://api.groq.com/openai/v1`),
  `llm_request_timeout_seconds` (default 60) — see `.env.example` for
  worked examples against Groq/OpenAI/OpenRouter
- `GET /llm/health` diagnostic endpoint
- `StubLLMProvider` in `tests/fakes.py`, wired into the shared `client`
  fixture in `tests/conftest.py`

### Out of Scope
- Prompt engineering / question generation (phase3-f02)
- Non-OpenAI-compatible wire formats (e.g. Anthropic's native Messages API)
  — the interface makes a dedicated provider a drop-in addition later if
  ever needed
- Retry/backoff on transient upstream errors (a single failed call surfaces
  as `unavailable`/an exception; no automatic retry loop in v1)

## 3. Data Model

None.

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| GET | `/llm/health` | — | `200` `{"status": "ok"\|"unavailable", "model": str}` | Always 200 — diagnostic, not a hard gate |

## 5. UI Behavior

None — no UI touches this feature directly (phase3-f04 will surface LLM
failures indirectly through generation status).

## 6. Test Strategy

### Unit Tests
- `StubLLMProvider` returns its configured response; raises `RuntimeError`
  when `should_fail=True`
- `OpenAICompatibleLLMProvider.generate` raises `RuntimeError` when
  `llm_api_key` is empty (no network call required to exercise this)

### Integration Tests
- `GET /llm/health` returns `{"status": "ok", ...}` when the stubbed
  provider succeeds
- `GET /llm/health` returns `{"status": "unavailable", ...}` when the
  stubbed provider is configured to fail

### Manual Verification
- [x] Set a real `GROQ_API_KEY` in `.env`, started the backend, hit
      `GET /llm/health`, confirmed `{"status": "ok", "model": "llama-3.3-70b-versatile"}`

## 7. Acceptance Criteria

- [x] All tests above pass with the stub provider
- [x] `/llm/health` manually confirmed against the real Groq API
