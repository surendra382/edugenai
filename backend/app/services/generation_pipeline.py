import json

from sqlalchemy.orm import Session

from backend.app.core.logging import bind_request_id, get_logger
from backend.app.models.chapter import Chapter
from backend.app.models.question import Question
from backend.app.models.question_set import QuestionSet
from backend.app.models.question_set_chapter import QuestionSetChapter
from backend.app.models.subject import Subject
from backend.app.services import llm as llm_module
from backend.app.services import prompt_builder
from backend.app.services import question_parser
from backend.app.services import retriever as retriever_module

logger = get_logger(__name__)

MAX_LOGGED_PROMPT_CHARS = 20_000


def run_generation(question_set_id: int, db: Session) -> None:
    with bind_request_id():
        _run_generation(question_set_id, db)


def _run_generation(question_set_id: int, db: Session) -> None:
    question_set = db.get(QuestionSet, question_set_id)
    if question_set is None:
        return

    subject = db.get(Subject, question_set.subject_id)
    question_types = question_set.question_types.split(",")

    selections = (
        db.query(QuestionSetChapter)
        .join(Chapter, QuestionSetChapter.chapter_id == Chapter.id)
        .filter(QuestionSetChapter.question_set_id == question_set.id)
        .order_by(Chapter.order)
        .all()
    )

    generated: list[tuple[int, dict]] = []
    current_chapter_name: str | None = None
    stage: str | None = None

    try:
        for selection in selections:
            chapter = db.get(Chapter, selection.chapter_id)
            current_chapter_name = chapter.name

            stage = "retrieval"
            context_results = retriever_module.retriever.search(
                db, chapter_id=selection.chapter_id, query=chapter.name, limit=8
            )
            context_chunks = [result.text for result in context_results]

            stage = "prompt"
            prompt = prompt_builder.build_prompt(
                subject_name=subject.name,
                chapter_name=chapter.name,
                difficulty=question_set.difficulty,
                question_types=question_types,
                num_questions=selection.num_questions,
                context_chunks=context_chunks,
                include_answer_key=question_set.include_answer_key,
            )
            logger.info(
                "prompt.built",
                extra={
                    "event": "prompt.built",
                    "question_set_id": question_set.id,
                    "chapter_id": selection.chapter_id,
                    "chapter_name": chapter.name,
                    "subject_name": subject.name,
                    "difficulty": question_set.difficulty,
                    "question_types": question_types,
                    "num_questions": selection.num_questions,
                    "include_answer_key": question_set.include_answer_key,
                    "prompt_char_len": len(prompt),
                    "prompt": prompt[:MAX_LOGGED_PROMPT_CHARS],
                },
            )

            stage = "llm"
            raw_response = llm_module.llm_provider.generate(prompt)

            stage = "parsing"
            parsed_questions = question_parser.parse_questions(
                raw_response,
                expected_types=set(question_types),
                expect_count=selection.num_questions,
                expect_answer=question_set.include_answer_key,
            )
            for item in parsed_questions:
                generated.append((selection.chapter_id, item))
    except Exception as exc:
        label = f" ({current_chapter_name})" if current_chapter_name else ""
        logger.exception(
            "generation.error",
            extra={
                "event": "generation.error",
                "question_set_id": question_set.id,
                "subject_id": question_set.subject_id,
                "chapter": current_chapter_name,
                "stage": stage,
            },
        )
        question_set.status = "failed"
        question_set.generation_error = f"Generation failed{label}: {exc}"
        db.commit()
        return

    for index, (chapter_id, item) in enumerate(generated):
        options_json = json.dumps(item["options"]) if item["options"] is not None else None
        answer = item["answer"] if question_set.include_answer_key else None
        db.add(
            Question(
                question_set_id=question_set.id,
                chapter_id=chapter_id,
                question_index=index,
                question_type=item["type"],
                text=item["text"],
                options=options_json,
                answer=answer,
            )
        )

    question_set.status = "completed"
    question_set.generation_error = None
    db.commit()
