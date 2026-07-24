from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ChapterBase(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(ChapterBase):
    pass


class ChapterRead(ChapterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    order: int
    created_at: datetime
    updated_at: datetime


class ChapterReorderRequest(BaseModel):
    ordered_ids: list[int]
