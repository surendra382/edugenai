import io
import time
from typing import Protocol

from google import genai
from PIL import Image

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class VisionExtractor(Protocol):
    def extract_raw(self, image_bytes: bytes, mime_type: str) -> str: ...


class GeminiVisionExtractor:
    """Reads a question-paper image and returns each printed question as a
    structured JSON record, replacing OCR+chunking for this material: the
    upload is a set of discrete questions, not prose, so a vision LLM
    extracting structured fields directly is a better fit than transcribing
    text and slicing it into chunks. Settings are read lazily on each call
    (same pattern as GeminiOCRProvider/OpenAICompatibleLLMProvider), so
    importing this module never requires an API key and tests can swap in a
    stub before any real call happens.
    """

    _PROMPT = (
        "You are extracting questions from a scanned question-paper image. "
        "Return ONLY a JSON array (no markdown fences, no commentary), one "
        "element per question found on the page, each shaped exactly like:\n"
        "{\n"
        '  "question_type": "mcq | true_false | short_answer | numerical | fill_blank",\n'
        '  "stem": "question text, math in plain/unicode (sqrt(16), x^2, ×, ÷, ₹) '
        '— never LaTeX/backslashes",\n'
        '  "concept": "short concept/sub-skill label",\n'
        '  "options": ["opt A text", "opt B text", "..."],\n'
        '  "answer": "correct option text or value, or null if not shown in the image",\n'
        '  "difficulty": "easy | medium | hard"\n'
        "}\n"
        "Omit \"options\" (or set it to null) unless question_type is \"mcq\". "
        "Do not solve, explain, or add questions that aren't printed on the page."
    )

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key
        self._model = model

    def extract_raw(self, image_bytes: bytes, mime_type: str) -> str:
        api_key = self._api_key if self._api_key is not None else settings.gemini_api_key
        model = self._model if self._model is not None else settings.gemini_model

        if not api_key:
            raise RuntimeError("Gemini API key is not configured")

        image = Image.open(io.BytesIO(image_bytes))

        started_at = time.perf_counter()
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=[self._PROMPT, image])
        text = response.text

        logger.info(
            "vision_extract.completed",
            extra={
                "event": "vision_extract.completed",
                "provider": "gemini",
                "model": model,
                "mime_type": mime_type,
                "text_char_len": len(text),
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return text


vision_extractor: VisionExtractor = GeminiVisionExtractor()
