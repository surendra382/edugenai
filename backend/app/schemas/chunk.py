from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    chunk_index: int
    text: str
    chroma_id: str
    created_at: datetime
