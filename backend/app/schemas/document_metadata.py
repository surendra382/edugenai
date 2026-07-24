from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Difficulty = Literal["easy", "medium", "hard"]


class DocumentMetadataUpdate(BaseModel):
    board: str | None = None
    class_level: str | None = None
    keywords: str | None = None
    learning_objectives: str | None = None
    question_types: str | None = None
    difficulty: Difficulty | None = None
    source: str | None = None


class DocumentMetadataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    board: str | None = None
    class_level: str | None = None
    keywords: str | None = None
    learning_objectives: str | None = None
    question_types: str | None = None
    difficulty: str | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime
