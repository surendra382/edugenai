from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("question_set_id", "question_index", name="uq_question_set_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_set_id: Mapped[int] = mapped_column(ForeignKey("question_sets.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    options: Mapped[str | None] = mapped_column(String, nullable=True)
    answer: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
