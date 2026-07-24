from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base
from backend.app.models.chapter import Chapter


class QuestionSetChapter(Base):
    __tablename__ = "question_set_chapters"
    __table_args__ = (
        UniqueConstraint("question_set_id", "chapter_id", name="uq_question_set_chapter"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_set_id: Mapped[int] = mapped_column(ForeignKey("question_sets.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    num_questions: Mapped[int] = mapped_column(Integer, nullable=False)

    chapter: Mapped[Chapter] = relationship(Chapter)
