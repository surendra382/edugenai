import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class QuestionBankItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    class_grade: str
    source: str
    question_type: str
    stem: str
    concept: str | None
    options: list[str] | None
    answer: str | None
    difficulty: str
    source_image: str | None
    created_at: datetime

    @field_validator("options", mode="before")
    @classmethod
    def _parse_options(cls, value):
        if isinstance(value, str):
            return json.loads(value)
        return value


class QuestionBankImportError(BaseModel):
    filename: str
    error: str


class QuestionBankImportResult(BaseModel):
    created: int
    items: list[QuestionBankItemRead]
    errors: list[QuestionBankImportError]
