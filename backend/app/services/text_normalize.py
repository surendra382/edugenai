import re

_SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

_SQRT_RE = re.compile(r"\\sqrt(?:\[(\d+)\])?\{([^{}]*)\}")
_FRAC_RE = re.compile(r"\\frac\{([^{}]*)\}\{([^{}]*)\}")
_TEXT_RE = re.compile(r"\\text\{([^{}]*)\}")
_BRACED_EXPONENT_RE = re.compile(r"\^\{([^{}]*)\}")
_BARE_EXPONENT_DIGIT_RE = re.compile(r"\^(\d)")
_DELIMITER_RE = re.compile(r"\$\$?")
_UNKNOWN_COMMAND_RE = re.compile(r"\\([a-zA-Z]+)")

_SYMBOL_MAP = {
    r"\times": "×",
    r"\div": "÷",
    r"\pm": "±",
    r"\mp": "∓",
    r"\cdot": "·",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\approx": "≈",
    r"\infty": "∞",
    r"\pi": "π",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\theta": "θ",
    r"\leftarrow": "←",
    r"\rightarrow": "→",
    r"\Leftarrow": "⇐",
    r"\Rightarrow": "⇒",
    r"\Leftrightarrow": "⇔",
    r"\left": "",
    r"\right": "",
    r"\%": "%",
    r"\&": "&",
    r"\_": "_",
    r"\{": "{",
    r"\}": "}",
    r"\qquad": "  ",
    r"\quad": " ",
    r"\,": " ",
    r"\;": " ",
    r"\!": "",
}


def _is_atomic(content: str) -> bool:
    """Whether content needs no extra parens when placed after √ etc. — a
    bare token, or something already fully wrapped by a prior substitution
    (e.g. the "(1/4)" that _replace_frac just produced)."""
    return content.isalnum() or (content.startswith("(") and content.endswith(")"))


def _replace_sqrt(match: re.Match) -> str:
    root, content = match.group(1), match.group(2)
    wrapped = content if _is_atomic(content) else f"({content})"
    if root == "3":
        return f"∛{wrapped}"
    if root and root != "2":
        return f"{root}√{wrapped}"
    return f"√{wrapped}"


def _replace_frac(match: re.Match) -> str:
    numerator, denominator = match.group(1), match.group(2)
    return f"({numerator}/{denominator})"


def _replace_braced_exponent(match: re.Match) -> str:
    content = match.group(1)
    if content.isdigit():
        return content.translate(_SUPERSCRIPT_DIGITS)
    return f"^({content})"


def normalize_math_notation(text: str) -> str:
    """Converts LaTeX math notation (as Gemini sometimes emits despite being
    asked not to) into plain unicode text, applied to every extracted
    question-bank field before storage so downstream prompt-building never
    needs to know LaTeX exists. Best-effort regex substitution rather than a
    full LaTeX parser: covers common constructs (sqrt, frac, exponents,
    symbols), applied repeatedly so simple nesting (e.g. a sqrt inside a
    frac) still resolves.
    """
    previous = None
    while previous != text:
        previous = text
        # \text{} unwraps first each pass: \frac/\sqrt's own regexes can't
        # match through nested braces (e.g. \frac{\text{Profit}}{...}), so
        # peeling \text{} off first is what lets the next pass see a
        # brace-free argument.
        text = _TEXT_RE.sub(r"\1", text)
        text = _SQRT_RE.sub(_replace_sqrt, text)
        text = _FRAC_RE.sub(_replace_frac, text)

    text = _BRACED_EXPONENT_RE.sub(_replace_braced_exponent, text)
    text = _BARE_EXPONENT_DIGIT_RE.sub(lambda m: m.group(1).translate(_SUPERSCRIPT_DIGITS), text)

    for command, replacement in _SYMBOL_MAP.items():
        text = text.replace(command, replacement)

    text = _DELIMITER_RE.sub("", text)
    # Catch-all: any remaining \command we didn't explicitly map — drop the
    # backslash rather than leaving LaTeX noise in the stored text.
    text = _UNKNOWN_COMMAND_RE.sub(r"\1", text)
    return text
