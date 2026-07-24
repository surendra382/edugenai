import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_set_id: int
    chapter_id: int
    question_index: int
    question_type: str
    text: str
    options: list[str] | None
    answer: str | None
    created_at: datetime

    @field_validator("options", mode="before")
    @classmethod
    def _parse_options(cls, value):
        if isinstance(value, str):
            return json.loads(value)
        return value
