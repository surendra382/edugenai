from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app import models  # noqa: F401  registers models with Base.metadata
from backend.app.api.chapters import router as chapters_router
from backend.app.api.health import router as health_router
from backend.app.api.llm import router as llm_router
from backend.app.api.question_bank import router as question_bank_router
from backend.app.api.questions import router as questions_router
from backend.app.api.subjects import router as subjects_router
from backend.app.core.logging import bind_request_id, configure_logging, current_request_id, get_logger
from backend.app.db.session import create_tables

logger = get_logger(__name__)


class RequestIdMiddleware:
    """Plain ASGI middleware (not BaseHTTPMiddleware) so exceptions raised
    downstream propagate straight up to Starlette's ServerErrorMiddleware /
    our registered exception handler, rather than through
    BaseHTTPMiddleware's task-group wrapping, which mangles exception
    propagation for unhandled errors.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming_request_id = Headers(scope=scope).get("x-request-id")

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("X-Request-ID", current_request_id() or "")
            await send(message)

        with bind_request_id(incoming_request_id):
            await self.app(scope, receive, send_wrapper)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    create_tables()
    yield


app = FastAPI(title="EduGenAI", lifespan=lifespan)

app.include_router(health_router)
app.include_router(subjects_router)
app.include_router(chapters_router)
app.include_router(llm_router)
app.include_router(question_bank_router)
app.include_router(questions_router)

app.add_middleware(RequestIdMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "http.unhandled_error",
        extra={
            "event": "http.unhandled_error",
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
