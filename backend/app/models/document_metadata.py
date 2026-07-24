from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), unique=True, nullable=False
    )
    board: Mapped[str | None] = mapped_column(String, nullable=True)
    class_level: Mapped[str | None] = mapped_column(String, nullable=True)
    keywords: Mapped[str | None] = mapped_column(String, nullable=True)
    learning_objectives: Mapped[str | None] = mapped_column(String, nullable=True)
    question_types: Mapped[str | None] = mapped_column(String, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
