from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    material_type: str
    file_type: str
    original_filename: str
    file_size_bytes: int
    status: str
    ocr_error: str | None = None
    embedding_error: str | None = None
    created_at: datetime
    updated_at: datetime
