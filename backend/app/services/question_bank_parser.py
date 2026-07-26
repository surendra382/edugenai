import json
import re

from backend.app.services.text_normalize import normalize_math_notation

_QUESTION_TYPES = {"mcq", "true_false", "short_answer", "numerical", "fill_blank"}
_DIFFICULTIES = {"easy", "medium", "hard"}
_INVALID_ESCAPE_RE = re.compile(r'\\(?!["\\/bfnrtu])')


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _validate_item(item: object) -> dict:
    """Raises ValueError with a human-readable reason if `item` isn't a
    usable question record. Callers catch this per-item so one malformed
    question doesn't discard the rest of a page."""
    if not isinstance(item, dict):
        raise ValueError("item is not a JSON object")

    question_type = item.get("question_type")
    if question_type not in _QUESTION_TYPES:
        raise ValueError(f"unknown question_type: {question_type!r}")

    stem = item.get("stem")
    if not isinstance(stem, str) or not stem.strip():
        raise ValueError("stem must be a non-empty string")

    difficulty = item.get("difficulty")
    if difficulty not in _DIFFICULTIES:
        raise ValueError(f"unknown difficulty: {difficulty!r}")

    options = item.get("options")
    if question_type == "mcq":
        if (
            not isinstance(options, list)
            or len(options) < 2
            or not all(isinstance(option, str) for option in options)
        ):
            raise ValueError("mcq questions require at least 2 string options")
    else:
        options = None

    answer = item.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        answer = None

    concept = item.get("concept")
    if not isinstance(concept, str) or not concept.strip():
        concept = None

    return {
        "question_type": question_type,
        "stem": normalize_math_notation(stem.strip()),
        "concept": normalize_math_notation(concept) if concept else None,
        "options": [normalize_math_notation(option) for option in options] if options else None,
        "answer": normalize_math_notation(answer) if answer else None,
        "difficulty": difficulty,
    }


def parse(raw_text: str) -> tuple[list[dict], list[str]]:
    """Parses a vision extractor's raw response into validated question-bank
    items. Top-level malformed JSON is a hard failure (raises ValueError) —
    there's nothing usable to salvage. Once the response is a JSON array,
    each element is validated independently: invalid items are dropped and
    their reasons collected instead of failing the whole batch, so one bad
    question on a multi-question page doesn't discard the good ones.
    """
    text = _strip_code_fences(raw_text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        try:
            parsed = json.loads(_INVALID_ESCAPE_RE.sub(r"\\\\", text))
        except json.JSONDecodeError:
            raise ValueError(f"response is not valid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("response must be a JSON array")

    items = []
    errors = []
    for index, raw_item in enumerate(parsed):
        try:
            items.append(_validate_item(raw_item))
        except ValueError as exc:
            errors.append(f"item {index}: {exc}")

    return items, errors
