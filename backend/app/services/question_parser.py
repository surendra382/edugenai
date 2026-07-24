import json
import re

_OPTION_PREFIX_RE = re.compile(r"^[A-Ja-j][.)]\s+")
_INVALID_ESCAPE_RE = re.compile(r'\\(?!["\\/bfnrtu])')


def _strip_option_prefix(value: str) -> str:
    """Remove a leading 'A) '/'A. ' label the LLM sometimes bakes into option
    text despite the prompt asking for plain text — callers (UI, PDF export)
    add their own letter prefix, so a baked-in one would double up."""
    return _OPTION_PREFIX_RE.sub("", value, count=1).strip()


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


def parse_questions(
    raw_text: str,
    expected_types: set[str],
    expect_count: int,
    expect_answer: bool = False,
) -> list[dict]:
    text = _strip_code_fences(raw_text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        # LLMs writing math/LaTeX (e.g. \sqrt, \frac) often emit a bare
        # backslash, which isn't a valid JSON escape. Retry once with such
        # backslashes doubled up rather than failing the whole generation.
        try:
            parsed = json.loads(_INVALID_ESCAPE_RE.sub(r"\\\\", text))
        except json.JSONDecodeError:
            raise ValueError(f"LLM response is not valid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("LLM response must be a JSON array")

    if len(parsed) != expect_count:
        raise ValueError(f"Expected {expect_count} questions, got {len(parsed)}")

    questions = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Each question must be a JSON object")

        question_type = item.get("type")
        if question_type not in expected_types:
            raise ValueError(f"Unexpected question type: {question_type!r}")

        text_value = item.get("text")
        if not isinstance(text_value, str) or not text_value.strip():
            raise ValueError("Question text must be a non-empty string")

        options = item.get("options")
        if question_type == "mcq":
            if (
                not isinstance(options, list)
                or len(options) < 2
                or not all(isinstance(option, str) for option in options)
            ):
                raise ValueError("mcq questions require at least 2 string options")
            options = [_strip_option_prefix(option) for option in options]
        else:
            options = None

        answer = item.get("answer")
        if expect_answer:
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Question is missing a required answer")
            if question_type == "mcq":
                answer = _strip_option_prefix(answer)
        else:
            answer = None

        questions.append(
            {"type": question_type, "text": text_value, "options": options, "answer": answer}
        )

    return questions
