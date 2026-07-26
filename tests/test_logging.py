import json
import logging

from fakes import StubLLMProvider, StubVisionExtractor
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.logging import (
    APP_LOGGER_NAME,
    JsonFormatter,
    bind_request_id,
    configure_logging,
    current_request_id,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services import llm as llm_module
from backend.app.services import vision_extractor as vision_extractor_module
from backend.app.services.llm import OpenAICompatibleLLMProvider


class FakeHTTPResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Physics"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Motion"}).json()


def _seed_question_bank_item(client, chapter_id: int, difficulty: str = "easy") -> dict:
    original = vision_extractor_module.vision_extractor
    vision_extractor_module.vision_extractor = StubVisionExtractor(
        response=json.dumps(
            [
                {
                    "question_type": "mcq",
                    "stem": "What is velocity?",
                    "concept": "kinematics",
                    "options": ["Speed", "Speed with direction", "Distance", "Time"],
                    "answer": "Speed with direction",
                    "difficulty": difficulty,
                }
            ]
        )
    )
    try:
        return client.post(
            f"/chapters/{chapter_id}/question-bank/import",
            data={"class_grade": "8", "source": "unknown"},
            files={"images": ("page.png", b"fake-image-bytes", "image/png")},
        ).json()
    finally:
        vision_extractor_module.vision_extractor = original


def _valid_llm_response(count: int = 1) -> str:
    return json.dumps(
        [{"type": "mcq", "text": f"Question {i}", "options": ["A", "B", "C", "D"]} for i in range(count)]
    )


# --- configure_logging / JsonFormatter / request_id plumbing ---


def test_configure_logging_sets_level_and_attaches_handlers_once(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(settings, "log_level", "DEBUG")

    configure_logging()
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    assert app_logger.level == logging.DEBUG
    assert len(app_logger.handlers) == 2

    configure_logging()
    assert len(app_logger.handlers) == 2
    assert (tmp_path / "logs" / "app.log").exists()


def test_json_formatter_outputs_valid_json_with_required_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="backend.app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="something.happened",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.custom_field = "value"

    output = json.loads(formatter.format(record))

    assert output["level"] == "INFO"
    assert output["logger"] == "backend.app.test"
    assert output["message"] == "something.happened"
    assert output["request_id"] == "req-123"
    assert output["custom_field"] == "value"
    assert "timestamp" in output


def test_bind_request_id_scopes_value_to_context():
    assert current_request_id() is None
    with bind_request_id() as request_id:
        assert request_id
        assert current_request_id() == request_id
    assert current_request_id() is None


def test_bind_request_id_accepts_explicit_value():
    with bind_request_id("fixed-id") as request_id:
        assert request_id == "fixed-id"


def test_request_id_filter_stamps_records_only_within_binding(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(settings, "log_level", "INFO")
    configure_logging()
    caplog.set_level(logging.INFO)

    probe_logger = logging.getLogger("backend.app.services.probe")
    with bind_request_id("trace-xyz"):
        probe_logger.info("inside context")
    probe_logger.info("outside context")

    records = {
        record.getMessage(): record.request_id
        for record in caplog.records
        if record.name == "backend.app.services.probe"
    }
    assert records["inside context"] == "trace-xyz"
    assert records["outside context"] is None


# --- LLM provider logging ---


def test_openai_compatible_provider_logs_request_and_token_usage(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "logs"))
    configure_logging()
    caplog.set_level(logging.INFO)

    monkeypatch.setattr(settings, "llm_api_key", "secret-test-key")
    fake_payload = {
        "choices": [{"message": {"content": "hello world"}}],
        "usage": {"prompt_tokens": 42, "completion_tokens": 7, "total_tokens": 49},
    }
    monkeypatch.setattr(llm_module.requests, "post", lambda *args, **kwargs: FakeHTTPResponse(fake_payload))

    provider = OpenAICompatibleLLMProvider()
    result = provider.generate("a test prompt")

    assert result == "hello world"

    request_records = [r for r in caplog.records if getattr(r, "event", None) == "llm.request"]
    response_records = [r for r in caplog.records if getattr(r, "event", None) == "llm.response"]
    assert len(request_records) == 1
    assert len(response_records) == 1
    assert response_records[0].prompt_tokens == 42
    assert response_records[0].completion_tokens == 7
    assert response_records[0].total_tokens == 49

    for record in caplog.records:
        assert "secret-test-key" not in json.dumps(record.__dict__, default=str)


# --- generation pipeline logging ---


def test_generation_pipeline_logs_prompt_with_shared_request_id(client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    chapter = _create_chapter(client)
    _seed_question_bank_item(client, chapter["id"])

    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_valid_llm_response(1)))
    caplog.clear()

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    assert response.status_code == 202
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    lookup_records = [r for r in caplog.records if getattr(r, "event", None) == "question_bank.lookup"]
    prompt_records = [r for r in caplog.records if getattr(r, "event", None) == "prompt.built"]
    assert len(lookup_records) == 1
    assert len(prompt_records) == 1

    lookup_record = lookup_records[0]
    assert lookup_record.chapter_id == chapter["id"]
    assert lookup_record.result_count == 1

    prompt_record = prompt_records[0]
    assert prompt_record.chapter_id == chapter["id"]
    assert prompt_record.prompt_char_len == len(prompt_record.prompt)
    assert "mcq" in prompt_record.prompt

    request_ids = {lookup_record.request_id, prompt_record.request_id}
    assert len(request_ids) == 1
    assert next(iter(request_ids)) is not None


def test_generation_pipeline_logs_error_with_stage_and_traceback(client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response="not valid json"))
    chapter = _create_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "failed"

    error_records = [r for r in caplog.records if getattr(r, "event", None) == "generation.error"]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.levelname == "ERROR"
    assert record.stage == "parsing"
    assert record.question_set_id == question_set_id
    assert record.chapter == chapter["name"]
    assert record.exc_info is not None


# --- request correlation middleware / global exception handler ---


def test_response_includes_request_id_header(client):
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_response_echoes_incoming_request_id_header(client):
    response = client.get("/health", headers={"X-Request-ID": "caller-supplied-id"})
    assert response.headers["X-Request-ID"] == "caller-supplied-id"


def test_unhandled_exception_returns_500_with_logged_traceback(client, caplog):
    # Starlette's ServerErrorMiddleware always re-raises after invoking a
    # registered error handler (so real ASGI servers can still log it) —
    # raise_server_exceptions=False on this second client (same app,
    # already-configured DB/lifespan from the `client` fixture) lets us
    # observe the 500 response instead of the exception propagating here.
    caplog.set_level(logging.ERROR)

    def _broken_get_db():
        raise RuntimeError("simulated boom")
        yield  # pragma: no cover - unreachable, keeps this a generator like the real dependency

    app.dependency_overrides[get_db] = _broken_get_db
    lenient_client = TestClient(app, raise_server_exceptions=False)
    response = lenient_client.get("/subjects")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}

    error_records = [r for r in caplog.records if getattr(r, "event", None) == "http.unhandled_error"]
    assert len(error_records) == 1
    assert error_records[0].path == "/subjects"
    assert error_records[0].exc_info is not None


def test_existing_http_exceptions_are_unaffected_by_global_handler(client):
    response = client.get("/subjects/999")
    assert response.status_code == 404
