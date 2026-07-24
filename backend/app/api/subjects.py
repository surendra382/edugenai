from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.chapter import Chapter
from backend.app.models.subject import Subject
from backend.app.schemas.subject import SubjectCreate, SubjectRead, SubjectUpdate

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _get_subject_or_404(db: Session, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    return subject


def _name_collision(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = db.query(Subject.id).filter(func.lower(Subject.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(Subject.id != exclude_id)
    return query.first() is not None


@router.post("", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db)) -> Subject:
    if _name_collision(db, payload.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subject name already exists")
    subject = Subject(name=payload.name)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.get("", response_model=list[SubjectRead])
def list_subjects(db: Session = Depends(get_db)) -> list[Subject]:
    return db.query(Subject).order_by(Subject.name).all()


@router.get("/{subject_id}", response_model=SubjectRead)
def get_subject(subject_id: int, db: Session = Depends(get_db)) -> Subject:
    return _get_subject_or_404(db, subject_id)


@router.put("/{subject_id}", response_model=SubjectRead)
def update_subject(subject_id: int, payload: SubjectUpdate, db: Session = Depends(get_db)) -> Subject:
    subject = _get_subject_or_404(db, subject_id)
    if _name_collision(db, payload.name, exclude_id=subject_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subject name already exists")
    subject.name = payload.name
    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, db: Session = Depends(get_db)) -> None:
    subject = _get_subject_or_404(db, subject_id)
    has_chapters = db.query(Chapter.id).filter(Chapter.subject_id == subject_id).first() is not None
    if has_chapters:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete subject with existing chapters",
        )
    db.delete(subject)
    db.commit()
