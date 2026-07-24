import requests
from fastapi import APIRouter

from backend.app.core.config import settings
from backend.app.services import llm as llm_module

router = APIRouter(tags=["llm"])


@router.get("/llm/health")
def llm_health() -> dict[str, str]:
    try:
        llm_module.llm_provider.generate("Respond with the single word: ready", max_tokens=5)
    except (RuntimeError, requests.RequestException):
        return {"status": "unavailable", "model": settings.llm_model}
    return {"status": "ok", "model": settings.llm_model}
