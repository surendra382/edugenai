from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

Difficulty = Literal["easy", "medium", "hard"]
QuestionType = Literal[
    "mcq", "fill_blank", "true_false", "short_answer", "long_answer", "numerical"
]

MAX_TOTAL_QUESTIONS = 60


class QuestionSetCreate(BaseModel):
    difficulty: Difficulty
    question_types: list[QuestionType]
    num_questions: int
    include_answer_key: bool = False
    source: str | None = None

    @field_validator("question_types")
    @classmethod
    def _non_empty_types(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("question_types must not be empty")
        return value

    @field_validator("num_questions")
    @classmethod
    def _num_questions_in_range(cls, value: int) -> int:
        if not 1 <= value <= 30:
            raise ValueError("num_questions must be between 1 and 30")
        return value


class ChapterSelection(BaseModel):
    chapter_id: int
    num_questions: int

    @field_validator("num_questions")
    @classmethod
    def _num_questions_in_range(cls, value: int) -> int:
        if not 1 <= value <= 30:
            raise ValueError("num_questions must be between 1 and 30")
        return value


class QuestionSetCreateMulti(BaseModel):
    chapters: list[ChapterSelection]
    difficulty: Difficulty
    question_types: list[QuestionType]
    include_answer_key: bool = False
    source: str | None = None

    @field_validator("question_types")
    @classmethod
    def _non_empty_types(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("question_types must not be empty")
        return value

    @field_validator("chapters")
    @classmethod
    def _validate_chapters(cls, value: list[ChapterSelection]) -> list[ChapterSelection]:
        if not value:
            raise ValueError("chapters must not be empty")
        total = sum(selection.num_questions for selection in value)
        if total > MAX_TOTAL_QUESTIONS:
            raise ValueError(
                f"total num_questions across chapters must not exceed {MAX_TOTAL_QUESTIONS}"
            )
        return value


class QuestionSetChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapter_id: int
    chapter_name: str
    num_questions: int

    @model_validator(mode="before")
    @classmethod
    def _flatten_chapter_name(cls, obj):
        if isinstance(obj, dict):
            return obj
        return {
            "chapter_id": obj.chapter_id,
            "chapter_name": obj.chapter.name,
            "num_questions": obj.num_questions,
        }


class QuestionSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    chapter_id: int | None
    chapters: list[QuestionSetChapterRead]
    difficulty: Difficulty
    source: str | None
    question_types: list[QuestionType]
    num_questions: int
    include_answer_key: bool
    status: str
    generation_error: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("question_types", mode="before")
    @classmethod
    def _split_types(cls, value):
        if isinstance(value, str):
            return value.split(",")
        return value


class QuestionSetHistoryRead(QuestionSetRead):
    chapter_name: str | None
    subject_name: str
