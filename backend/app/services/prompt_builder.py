def build_prompt(
    subject_name: str,
    chapter_name: str,
    difficulty: str,
    question_types: list[str],
    num_questions: int,
    context_chunks: list[str],
    include_answer_key: bool = False,
    source: str | None = None,
) -> str:
    if context_chunks:
        context_block = "\n".join(f"- {chunk}" for chunk in context_chunks)
        context_section = (
            "Use the following real exam questions from this chapter's question bank as "
            "your reference for style, format, and difficulty. Draw inspiration from them "
            "but do not copy any of them verbatim:\n"
            f"{context_block}"
        )
    else:
        context_section = (
            "No question bank items are available for this chapter. Use your own general "
            f'knowledge, but stay strictly within the scope of the topic "{chapter_name}" '
            f'in the subject "{subject_name}" for a school student. Do not introduce '
            "concepts outside this chapter."
        )

    types_list = ", ".join(question_types)

    purpose_instruction = (
        f'Write these questions in the style of a "{source}" exam for this subject and chapter.\n'
        if source
        else ""
    )

    if include_answer_key:
        answer_field_instruction = (
            '- "answer": the correct answer — the correct option text for "mcq", '
            '"true" or "false" for "true_false", or the final short answer/value '
            "otherwise. Every question must include this field.\n"
        )
    else:
        answer_field_instruction = ""

    return f"""You are an exam-question generator for a school subject named "{subject_name}", chapter "{chapter_name}".

{context_section}

Generate exactly {num_questions} fresh, original practice questions at "{difficulty}" difficulty.
Use a mix of these question types: {types_list}.
Do not duplicate or lightly paraphrase textbook exercises verbatim — write fresh questions.
Never introduce topics or concepts outside "{chapter_name}".
{purpose_instruction}

Write any mathematical notation in plain text or unicode symbols (e.g. sqrt(16), 2^3, x^2, √, π, ×, ÷) — never LaTeX or backslash commands like \\sqrt or \\frac, since backslashes are not valid inside a JSON string.

Respond with ONLY a JSON array, no other text and no markdown code fences. Each element must be a JSON object with:
- "type": one of {types_list}
- "text": ONLY the question stem itself — never append the answer options or the
  literal words "Options:"/"Answer:" to this field, even if the reference material
  above shows them formatted that way; options and answer belong only in the
  separate fields below
- "options": (ONLY for the "mcq" type) a JSON array of at least 2 answer choices as
  plain strings — do NOT prefix them with "A)", "B)", numbering, or any other label,
  just the answer text itself (labels are added later when the paper is displayed)
{answer_field_instruction}
Example shape (for illustration of format only, do not reuse this content):
[{{"type": "mcq", "text": "...", "options": ["First option text", "Second option text", "Third option text", "Fourth option text"]}}, {{"type": "short_answer", "text": "..."}}]"""
