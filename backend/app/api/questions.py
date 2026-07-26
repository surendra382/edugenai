import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.chapter import Chapter
from backend.app.models.question import Question
from backend.app.models.question_set import QuestionSet
from backend.app.models.question_set_chapter import QuestionSetChapter
from backend.app.models.subject import Subject
from backend.app.schemas.question import QuestionRead
from backend.app.schemas.question_set import (
    QuestionSetCreate,
    QuestionSetCreateMulti,
    QuestionSetHistoryRead,
    QuestionSetRead,
)
from backend.app.services.generation_pipeline import run_generation
from backend.app.services.pdf_export import build_question_paper_pdf

router = APIRouter(tags=["questions"])


def _get_subject_or_404(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    return subject


def _get_chapter_or_404(db: Session, chapter_id: int) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return chapter


def _get_question_set_or_404(db: Session, question_set_id: int) -> QuestionSet:
    question_set = db.get(QuestionSet, question_set_id)
    if question_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question set not found")
    return question_set


def _can_retry_generation(status_value: str) -> bool:
    return status_value == "failed"


def _create_question_set(
    db: Session,
    *,
    subject_id: int,
    chapter_selections: list[tuple[int, int]],
    difficulty: str,
    question_types: list[str],
    include_answer_key: bool,
    source: str | None = None,
) -> QuestionSet:
    question_set = QuestionSet(
        subject_id=subject_id,
        chapter_id=chapter_selections[0][0] if len(chapter_selections) == 1 else None,
        difficulty=difficulty,
        source=source,
        question_types=",".join(question_types),
        num_questions=sum(num_questions for _, num_questions in chapter_selections),
        include_answer_key=include_answer_key,
        status="generating",
    )
    db.add(question_set)
    db.flush()

    for chapter_id, num_questions in chapter_selections:
        db.add(
            QuestionSetChapter(
                question_set_id=question_set.id,
                chapter_id=chapter_id,
                num_questions=num_questions,
            )
        )
    db.commit()
    db.refresh(question_set)
    return question_set


@router.post(
    "/chapters/{chapter_id}/question-sets",
    response_model=QuestionSetRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_question_set(
    chapter_id: int,
    payload: QuestionSetCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> QuestionSet:
    chapter = _get_chapter_or_404(db, chapter_id)

    question_set = _create_question_set(
        db,
        subject_id=chapter.subject_id,
        chapter_selections=[(chapter_id, payload.num_questions)],
        difficulty=payload.difficulty,
        question_types=payload.question_types,
        include_answer_key=payload.include_answer_key,
        source=payload.source,
    )

    background_tasks.add_task(run_generation, question_set_id=question_set.id, db=db)
    return question_set


@router.post(
    "/subjects/{subject_id}/question-sets",
    response_model=QuestionSetRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_multi_chapter_question_set(
    subject_id: int,
    payload: QuestionSetCreateMulti,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> QuestionSet:
    _get_subject_or_404(db, subject_id)

    chapter_ids = [selection.chapter_id for selection in payload.chapters]
    if len(chapter_ids) != len(set(chapter_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chapters must not contain duplicate chapter_id values",
        )

    chapters_by_id = {
        chapter.id: chapter
        for chapter in db.query(Chapter).filter(Chapter.id.in_(chapter_ids)).all()
    }
    for chapter_id in chapter_ids:
        chapter = chapters_by_id.get(chapter_id)
        if chapter is None or chapter.subject_id != subject_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chapter {chapter_id} does not belong to subject {subject_id}",
            )

    question_set = _create_question_set(
        db,
        subject_id=subject_id,
        chapter_selections=[(s.chapter_id, s.num_questions) for s in payload.chapters],
        difficulty=payload.difficulty,
        question_types=payload.question_types,
        include_answer_key=payload.include_answer_key,
        source=payload.source,
    )

    background_tasks.add_task(run_generation, question_set_id=question_set.id, db=db)
    return question_set


@router.get("/chapters/{chapter_id}/question-sets", response_model=list[QuestionSetRead])
def list_question_sets(chapter_id: int, db: Session = Depends(get_db)) -> list[QuestionSet]:
    _get_chapter_or_404(db, chapter_id)
    return (
        db.query(QuestionSet)
        .filter(QuestionSet.chapter_id == chapter_id)
        .order_by(QuestionSet.created_at.desc())
        .all()
    )


@router.get("/question-sets", response_model=list[QuestionSetHistoryRead])
def list_all_question_sets(
    subject_id: int | None = None,
    chapter_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[dict]:
    if not 1 <= limit <= 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 200"
        )

    query = (
        db.query(QuestionSet, Subject.name.label("subject_name"), Chapter.name.label("chapter_name"))
        .join(Subject, QuestionSet.subject_id == Subject.id)
        .outerjoin(Chapter, QuestionSet.chapter_id == Chapter.id)
    )
    if subject_id is not None:
        query = query.filter(QuestionSet.subject_id == subject_id)
    if chapter_id is not None:
        matching_set_ids = db.query(QuestionSetChapter.question_set_id).filter(
            QuestionSetChapter.chapter_id == chapter_id
        )
        query = query.filter(QuestionSet.id.in_(matching_set_ids))
    if status_filter is not None:
        query = query.filter(QuestionSet.status == status_filter)

    rows = (
        query.order_by(QuestionSet.created_at.desc(), QuestionSet.id.desc())
        .limit(limit)
        .all()
    )

    question_set_ids = [question_set.id for question_set, _, _ in rows]
    chapter_breakdown: dict[int, list[dict]] = {}
    if question_set_ids:
        breakdown_rows = (
            db.query(QuestionSetChapter, Chapter.name)
            .join(Chapter, QuestionSetChapter.chapter_id == Chapter.id)
            .filter(QuestionSetChapter.question_set_id.in_(question_set_ids))
            .order_by(QuestionSetChapter.id)
            .all()
        )
        for question_set_chapter, chapter_name in breakdown_rows:
            chapter_breakdown.setdefault(question_set_chapter.question_set_id, []).append(
                {
                    "chapter_id": question_set_chapter.chapter_id,
                    "chapter_name": chapter_name,
                    "num_questions": question_set_chapter.num_questions,
                }
            )

    return [
        {
            "id": question_set.id,
            "subject_id": question_set.subject_id,
            "chapter_id": question_set.chapter_id,
            "chapters": chapter_breakdown.get(question_set.id, []),
            "difficulty": question_set.difficulty,
            "source": question_set.source,
            "question_types": question_set.question_types,
            "num_questions": question_set.num_questions,
            "include_answer_key": question_set.include_answer_key,
            "status": question_set.status,
            "generation_error": question_set.generation_error,
            "created_at": question_set.created_at,
            "updated_at": question_set.updated_at,
            "chapter_name": chapter_name,
            "subject_name": subject_name,
        }
        for question_set, subject_name, chapter_name in rows
    ]


@router.get("/question-sets/{question_set_id}", response_model=QuestionSetRead)
def get_question_set(question_set_id: int, db: Session = Depends(get_db)) -> QuestionSet:
    return _get_question_set_or_404(db, question_set_id)


@router.get("/question-sets/{question_set_id}/questions", response_model=list[QuestionRead])
def list_questions(question_set_id: int, db: Session = Depends(get_db)) -> list[Question]:
    _get_question_set_or_404(db, question_set_id)
    return (
        db.query(Question)
        .filter(Question.question_set_id == question_set_id)
        .order_by(Question.question_index)
        .all()
    )


@router.post(
    "/question-sets/{question_set_id}/retry",
    response_model=QuestionSetRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_question_set(
    question_set_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> QuestionSet:
    question_set = _get_question_set_or_404(db, question_set_id)
    if not _can_retry_generation(question_set.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Question set is not in a failed state",
        )

    question_set.status = "generating"
    question_set.generation_error = None
    db.commit()
    db.refresh(question_set)

    background_tasks.add_task(run_generation, question_set_id=question_set.id, db=db)
    return question_set


@router.get("/question-sets/{question_set_id}/pdf")
def export_question_set_pdf(
    question_set_id: int, include_answers: bool = True, db: Session = Depends(get_db)
) -> Response:
    question_set = _get_question_set_or_404(db, question_set_id)
    if question_set.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Question set is not completed",
        )

    subject = db.get(Subject, question_set.subject_id)
    chapter_rows = (
        db.query(QuestionSetChapter, Chapter.name)
        .join(Chapter, QuestionSetChapter.chapter_id == Chapter.id)
        .filter(QuestionSetChapter.question_set_id == question_set_id)
        .order_by(Chapter.order)
        .all()
    )
    chapters = [
        {"chapter_id": question_set_chapter.chapter_id, "chapter_name": chapter_name}
        for question_set_chapter, chapter_name in chapter_rows
    ]

    questions = (
        db.query(Question)
        .filter(Question.question_set_id == question_set_id)
        .order_by(Question.question_index)
        .all()
    )

    pdf_bytes = build_question_paper_pdf(
        subject_name=subject.name,
        chapters=chapters,
        difficulty=question_set.difficulty,
        questions=[
            {
                "question_index": q.question_index,
                "chapter_id": q.chapter_id,
                "question_type": q.question_type,
                "text": q.text,
                "options": json.loads(q.options) if q.options else None,
                "answer": q.answer,
            }
            for q in questions
        ],
        include_answers=include_answers and question_set.include_answer_key,
        source=question_set.source,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="question_set_{question_set_id}.pdf"'
        },
    )
