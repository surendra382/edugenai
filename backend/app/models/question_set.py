from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base
from backend.app.models.question_set_chapter import QuestionSetChapter


class QuestionSet(Base):
    __tablename__ = "question_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    difficulty: Mapped[str] = mapped_column(String, nullable=False)
    question_types: Mapped[str] = mapped_column(String, nullable=False)
    num_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    include_answer_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="generating")
    generation_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    chapters: Mapped[list[QuestionSetChapter]] = relationship(
        QuestionSetChapter,
        cascade="all, delete-orphan",
        order_by=QuestionSetChapter.id,
    )
