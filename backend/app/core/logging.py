import contextvars
import json
import logging
import logging.handlers
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from backend.app.core.config import settings

APP_LOGGER_NAME = "backend"

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_RESERVED_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
    "request_id",
    "taskName",
}


def new_request_id() -> str:
    return uuid4().hex


def current_request_id() -> str | None:
    return _request_id_var.get()


@contextmanager
def bind_request_id(request_id: str | None = None) -> Iterator[str]:
    """Binds a request_id to the current context so every log record emitted
    underneath (regardless of which module's logger it comes from) is
    stamped with it, without changing any function signatures.
    """
    token = _request_id_var.set(request_id or new_request_id())
    try:
        yield _request_id_var.get()
    finally:
        _request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        payload = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key in payload:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _build_formatter() -> logging.Formatter:
    if settings.log_json:
        return JsonFormatter()
    return logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")


def configure_logging() -> None:
    """Configures the "backend" logger namespace (parent of every
    backend.app.* module logger) with a console handler and a rotating file
    handler. Deliberately does not touch the root logger, so it never
    interferes with pytest's caplog (which attaches its own handler to the
    root logger) or any other tool's logging setup — records still reach
    caplog via normal propagation. Safe to call more than once (e.g. once
    per app startup in tests): handlers are cleared and rebuilt from current
    settings each time rather than guarded behind a one-shot flag.
    """
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    for handler in list(app_logger.handlers):
        app_logger.removeHandler(handler)
        handler.close()
    app_logger.setLevel(settings.log_level.upper())
    app_logger.propagate = True

    formatter = _build_formatter()
    request_id_filter = RequestIdFilter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_id_filter)
    app_logger.addHandler(console_handler)

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_dir / "app.log"), maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_id_filter)
    app_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
