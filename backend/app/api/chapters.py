from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.chapter import Chapter
from backend.app.models.subject import Subject
from backend.app.schemas.chapter import (
    ChapterCreate,
    ChapterRead,
    ChapterReorderRequest,
    ChapterUpdate,
)
from backend.app.schemas.search import SearchResult
from backend.app.services import retriever as retriever_module

router = APIRouter(tags=["chapters"])


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


def _name_collision(db: Session, subject_id: int, name: str, exclude_id: int | None = None) -> bool:
    query = db.query(Chapter.id).filter(Chapter.subject_id == subject_id, Chapter.name == name)
    if exclude_id is not None:
        query = query.filter(Chapter.id != exclude_id)
    return query.first() is not None


@router.post(
    "/subjects/{subject_id}/chapters",
    response_model=ChapterRead,
    status_code=status.HTTP_201_CREATED,
)
def create_chapter(subject_id: int, payload: ChapterCreate, db: Session = Depends(get_db)) -> Chapter:
    _get_subject_or_404(db, subject_id)
    if _name_collision(db, subject_id, payload.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chapter name already exists in this subject",
        )

    max_order = db.query(func.max(Chapter.order)).filter(Chapter.subject_id == subject_id).scalar()
    next_order = 0 if max_order is None else max_order + 1

    chapter = Chapter(subject_id=subject_id, name=payload.name, order=next_order)
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.get("/subjects/{subject_id}/chapters", response_model=list[ChapterRead])
def list_chapters(subject_id: int, db: Session = Depends(get_db)) -> list[Chapter]:
    _get_subject_or_404(db, subject_id)
    return (
        db.query(Chapter)
        .filter(Chapter.subject_id == subject_id)
        .order_by(Chapter.order)
        .all()
    )


@router.get("/chapters/{chapter_id}/search", response_model=list[SearchResult])
def search_chapter(
    chapter_id: int, q: str, limit: int = 10, db: Session = Depends(get_db)
) -> list[SearchResult]:
    _get_chapter_or_404(db, chapter_id)
    return retriever_module.retriever.search(db, chapter_id=chapter_id, query=q, limit=limit)


@router.get("/chapters/{chapter_id}", response_model=ChapterRead)
def get_chapter(chapter_id: int, db: Session = Depends(get_db)) -> Chapter:
    return _get_chapter_or_404(db, chapter_id)


@router.put("/chapters/{chapter_id}", response_model=ChapterRead)
def update_chapter(chapter_id: int, payload: ChapterUpdate, db: Session = Depends(get_db)) -> Chapter:
    chapter = _get_chapter_or_404(db, chapter_id)
    if _name_collision(db, chapter.subject_id, payload.name, exclude_id=chapter_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chapter name already exists in this subject",
        )
    chapter.name = payload.name
    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: int, db: Session = Depends(get_db)) -> None:
    chapter = _get_chapter_or_404(db, chapter_id)
    db.delete(chapter)
    db.commit()


@router.patch("/subjects/{subject_id}/chapters/reorder", response_model=list[ChapterRead])
def reorder_chapters(
    subject_id: int, payload: ChapterReorderRequest, db: Session = Depends(get_db)
) -> list[Chapter]:
    _get_subject_or_404(db, subject_id)
    chapters = db.query(Chapter).filter(Chapter.subject_id == subject_id).all()
    existing_ids = [chapter.id for chapter in chapters]

    if sorted(payload.ordered_ids) != sorted(existing_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ordered_ids must match exactly the subject's chapter ids",
        )

    chapters_by_id = {chapter.id: chapter for chapter in chapters}
    for index, chapter_id in enumerate(payload.ordered_ids):
        chapters_by_id[chapter_id].order = index
    db.commit()

    return (
        db.query(Chapter)
        .filter(Chapter.subject_id == subject_id)
        .order_by(Chapter.order)
        .all()
    )
