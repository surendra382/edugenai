# Feature: Observability & Structured Logging

**Phase:** 5 — Enhancements
**ID:** phase5-f02
**Status:** In Progress
**Depends on:** phase2-f05, phase3-f01, phase3-f02

---

## 1. Goal

A developer can inspect, for any practice-paper generation request, the exact
prompt sent to the LLM, the token usage of that call, and the retrieved
chunks that fed the prompt — all correlated by one request ID in a local log
file — instead of having no visibility beyond the truncated one-line message
currently stored in `QuestionSet.generation_error`. Any exception raised
anywhere in the retrieval/prompt/LLM/parsing pipeline (or in an API request)
is logged with a full stack trace and structured context, closing the
project's current gap of having no logging at all.

## 2. Scope

### In Scope
- `backend/app/core/logging.py` (new): `configure_logging()` sets up the
  root logger once, at app startup, with two handlers — a `StreamHandler`
  (stdout, human-readable) and a `RotatingFileHandler` (`{log_dir}/app.log`,
  `maxBytes=5_000_000`, `backupCount=5`) — plus a custom dependency-free
  `JsonFormatter` (stdlib `logging` + `json` only; no new package, keeping
  with the project's minimal-dependency stance already applied to LLM/OCR
  choices). A `logging.Filter` reads a `request_id` `contextvars.ContextVar`
  and stamps it onto every `LogRecord` so correlation doesn't require
  threading an extra parameter through existing function signatures
  (`prompt_builder.build_prompt`, `retriever.search`, `llm_provider.generate`
  keep their current signatures unchanged).
- New `Settings` fields in `backend/app/core/config.py`: `log_level: str =
  "INFO"`, `log_dir: str = "./logs"`, `log_json: bool = True` (set `false`
  for plain-text console formatting during local dev). Mirrored in
  `.env.example` with a comment block, same convention as the existing `LLM_*`
  block.
- `configure_logging()` called once from `main.py`'s `lifespan` startup,
  before the app starts serving.
- **Request correlation middleware**: an `@app.middleware("http")` in
  `main.py` that generates a `uuid4` per inbound HTTP request (or reuses an
  incoming `X-Request-ID` header if present), sets the `request_id`
  contextvar for the duration of the request, echoes it back as an
  `X-Request-ID` response header, and resets the contextvar in a `finally`
  block.
- **Retrieval logging** — one `logger.info("retrieval.result", extra={...})`
  call added inside `HybridRetriever.search()` (`backend/app/services/retriever.py:78`),
  after fusion, so both existing call sites (`generation_pipeline.py:40` and
  the chapter retrieval-preview endpoint at `backend/app/api/chapters.py:80`)
  get logging for free with no call-site changes. Fields: `chapter_id`,
  `query`, `limit`, `result_count`, `latency_ms`, and a `results` list of
  `{chunk_id, document_id, material_type, score, text_preview}` where
  `text_preview` is the chunk text truncated to 200 chars. The untruncated
  `text` is included only when the effective log level is `DEBUG`, so
  default `INFO` logs stay compact while `LOG_LEVEL=DEBUG` gives full chunk
  content for deep debugging.
- **Prompt logging** — one `logger.info("prompt.built", extra={...})` call
  added in `generation_pipeline.run_generation` (`backend/app/services/generation_pipeline.py:45`,
  right after `prompt_builder.build_prompt(...)` returns) rather than inside
  `prompt_builder.py` itself, so `build_prompt` stays a pure, side-effect-free
  function. Fields: `chapter_id`, `chapter_name`, `subject_name`,
  `difficulty`, `question_types`, `num_questions`, `include_answer_key`,
  `prompt_char_len`, and the full `prompt` string (truncated at 20,000 chars
  as a safety cap against pathological inputs, not a normal-case limit).
- **LLM request/response logging** — two log calls added inside
  `OpenAICompatibleLLMProvider.generate()` (`backend/app/services/llm.py:34`):
  one before the `requests.post` call (`llm.request`: `model`, `base_url`,
  `temperature`, `max_tokens`, `prompt_char_len` — never the API key), one
  after a successful response (`llm.response`: `model`, `latency_ms`,
  `http_status`, `response_char_len`, and `prompt_tokens` /
  `completion_tokens` / `total_tokens` read from `response.json()["usage"]`,
  which Groq's OpenAI-compatible wire format already returns but the code
  currently discards, per `llm.py:54`). The function's return type and the
  `LLMProvider` Protocol stay unchanged (still returns just the content
  string) — token counts are a side-effect of logging, not a new return
  value, so no caller or test that depends on `generate()`'s signature needs
  to change.
- **Error logging** — `generation_pipeline.run_generation`'s existing broad
  `except Exception as exc` (`generation_pipeline.py:64-69`) gains a
  `logger.exception("generation.error", extra={...})` call (captures the
  full traceback) with fields `question_set_id`, `subject_id`, `chapter`
  (the existing `current_chapter_name` var), and a new `stage` string
  (`"retrieval" | "prompt" | "llm" | "parsing"`) set immediately before each
  of the four steps inside the loop, so the log line says which step failed.
  This is **additive** — `question_set.generation_error` keeps being set
  exactly as today (that field is student/admin-facing, per
  `phase4-f03-practice-paper-history`); the log line is the
  developer-facing counterpart with full context and stack trace.
- A global FastAPI exception handler (`@app.exception_handler(Exception)` in
  `main.py`) logging any otherwise-unhandled exception (path, method,
  request_id, full traceback) before returning a generic `500` JSON body —
  there is currently no handler of any kind registered, so unhandled errors
  have no log trail at all today.
- New dependency: **none**. Everything above uses only the stdlib
  (`logging`, `json`, `contextvars`, `uuid`, `time`), matching this
  project's existing avoid-unnecessary-services posture.

### Out of Scope
- Shipping logs to an external aggregator (ELK, Datadog, Sentry, CloudWatch)
  — v1 is local file + stdout only; the project's cost-conscious stance
  (SRS tech-stack table) rules out paid log services for now. A future
  phase could add a shipper behind the same logging config without
  touching call sites.
- A log-viewing UI (e.g. a Streamlit "Logs" admin page) — developers read
  `logs/app.log` directly (`tail -f`, `jq`, grep by `request_id`) or the
  console.
- Redacting/masking chunk or prompt content for privacy — this is an
  internal developer tool over the admin's own uploaded knowledge base, not
  a user-facing data-handling feature. The only mandatory redaction is
  never emitting `llm_api_key` / the `Authorization` header value.
- Distributed tracing / OpenTelemetry spans — `latency_ms` timers on the
  three instrumented calls (retrieval, LLM request, and implicitly the
  whole generation loop via existing timestamps) are enough for v1; no
  span/trace-ID hierarchy beyond the single flat `request_id`.
- Log-based metrics/dashboards (e.g. token-spend-per-day charts) — the log
  file is the raw material; a metrics feature could consume it later but
  isn't built here.
- Changing `question_set.generation_error`'s content, meaning, or the
  History UI that reads it (`phase4-f03`) — unaffected by this feature.
- Structured logging for the Streamlit frontend process — this feature
  covers the FastAPI backend only, since that's where the prompt/retrieval/
  LLM pipeline actually runs.

## 3. Data Model

No new database tables or columns — logs are files, not DB-persisted rows.

**Config additions** (`backend/app/core/config.py`, `Settings`):
```python
log_level: str = "INFO"     # DEBUG | INFO | WARNING | ERROR
log_dir: str = "./logs"     # rotating file handler target directory
log_json: bool = True       # False => plain-text console formatting
```

**Log record schema** (the closest thing this feature has to a "data
model" — one JSON object per line in `{log_dir}/app.log` when `log_json` is
`true`):
```json
{
  "timestamp": "2026-07-23T10:15:32.481Z",
  "level": "INFO",
  "logger": "backend.app.services.retriever",
  "event": "retrieval.result",
  "request_id": "b3f1...e4a2",
  "message": "...",
  "...event-specific fields...": "..."
}
```

Event types and their extra fields, as described in §2:
`retrieval.result`, `prompt.built`, `llm.request`, `llm.response`,
`generation.error`, plus a generic `http.unhandled_error` from the global
exception handler.

## 4. API Contract

No new or changed endpoints. This is a backend-internal, developer-facing
feature — observability comes from reading `logs/app.log` / stdout, not
from a new HTTP surface. The one externally-visible change is a new
`X-Request-ID` response header on every API response (from the correlation
middleware), which existing clients can safely ignore.

## 5. UI Behavior

None — no Streamlit page is added or changed. Developers consume logs via
the filesystem (`logs/app.log`) or console output where the backend runs.

## 6. Test Strategy

### Unit Tests
- `configure_logging()`: root logger level matches `settings.log_level`;
  both a `RotatingFileHandler` (pointed at `settings.log_dir`) and a
  `StreamHandler` are attached; calling it twice doesn't duplicate handlers.
- `JsonFormatter`: formats a `LogRecord` into a single valid JSON line
  containing `timestamp`, `level`, `logger`, `message`, and `request_id`
  (present as `null`/omitted when no request context is bound).
- Request-ID contextvar: a value set via the middleware's helper is visible
  to a `logging.Filter` on a record emitted "during" that context, and is
  absent/different once the context exits (test the contextvar helper
  directly, without spinning up a real HTTP request).
- `HybridRetriever.search()` (`tests/test_retrieval.py`, extended): using
  `caplog`, assert exactly one `retrieval.result` record is emitted per
  call, with `result_count` matching the returned list length and each
  result entry's `chunk_id`/`score`/`material_type` matching the returned
  `SearchResult` objects; assert `text_preview` is truncated but full `text`
  is absent at `INFO`, present at `DEBUG`.
- `OpenAICompatibleLLMProvider.generate()` (`tests/test_llm.py`, extended):
  mock `requests.post` to return a response JSON including a `usage` block;
  assert an `llm.response` record is emitted with `prompt_tokens` /
  `completion_tokens` / `total_tokens` matching the mocked values, and that
  `generate()`'s return value is unchanged (still just the content string).
  Assert no record contains the API key value.
- `generation_pipeline.run_generation` (`tests/test_question_generation.py`,
  extended): force the stub LLM to return malformed output; assert (via
  `caplog`) a `generation.error` record at `ERROR` with `exc_info` populated
  (stack trace present) and `stage` set correctly, while
  `question_set.generation_error` is still populated exactly as before
  (regression check — behavior unchanged, logging is additive).

### Integration Tests
- `POST /chapters/{chapter_id}/question-sets` end-to-end with
  `StubLLMProvider` → `caplog` contains one `retrieval.result` and one
  `prompt.built` event per chapter, sharing the same `request_id`; the
  `prompt.built` event's `prompt` field matches what
  `prompt_builder.build_prompt` would produce for those inputs.
  (`llm.request`/`llm.response` are emitted by `OpenAICompatibleLLMProvider`
  itself, not the pipeline, so they're covered by a dedicated unit test
  against that provider with a mocked HTTP response — `StubLLMProvider`
  bypasses the real provider entirely and correctly emits neither.)
- Same request with a stub forced to raise → a `generation.error` record is
  present with the correct `stage`, and `GET /question-sets/{id}` still
  reports `status="failed"` with its existing `generation_error` message
  (no regression to phase3-f02 / phase5-f01 failure semantics).
- A route made to raise an uncaught exception (e.g. via a test-only
  dependency override) → response is `500`, `X-Request-ID` header present,
  and a `http.unhandled_error` record with a full traceback is logged.
- Two sequential requests produce two distinct `request_id` values, each
  fully self-consistent across its own log lines.

### Manual Verification
- [ ] Run the backend locally, generate a practice paper against a real
      `GROQ_API_KEY`; confirm `logs/app.log` has readable JSON lines for
      retrieval, prompt, and LLM request/response for that request, with
      real (non-zero) `prompt_tokens`/`completion_tokens`/`total_tokens`.
- [ ] Confirm the logged `prompt` field matches the actual prompt sent (spot
      check against the subject/chapter/difficulty/question-type inputs used).
- [ ] Confirm the logged retrieved chunks correspond to real chunks in that
      chapter's knowledge base (cross-check a `chunk_id` against the DB).
- [ ] Set `LLM_BASE_URL` to an invalid host temporarily and trigger a
      generation; confirm `generation.error` in the log shows a full stack
      trace with `stage="llm"`, and that the Student/History UI still shows
      the existing failed-status message unchanged.
- [ ] Set `LOG_LEVEL=DEBUG` and confirm full chunk text now appears in
      `retrieval.result` events; set it back to `INFO` and confirm only
      truncated previews appear.
- [ ] Grep `logs/app.log` for the configured `LLM_API_KEY` value and confirm
      zero matches.
- [ ] Confirm log file rotation config is in effect (`ls -la logs/` shows the
      single active file; rotation itself doesn't need to be manually forced
      to 5MB, just confirm the handler is configured with the right
      `maxBytes`/`backupCount`).

## 7. Acceptance Criteria

- [ ] All unit and integration tests above pass.
- [ ] A real end-to-end generation run against Groq produces a fully
      correlated (single `request_id`) log trail covering retrieval →
      prompt → LLM request/response → completion.
- [ ] A forced failure produces a complete stack trace and stage context in
      the log, in addition to the existing `generation_error` DB field —
      neither replaces the other.
- [ ] No API key or other secret value appears in any log line, verified by
      manual grep.
- [ ] No existing test, endpoint, or UI behavior changes as a result of this
      feature (purely additive instrumentation).
