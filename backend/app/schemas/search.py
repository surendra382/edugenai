from pydantic import BaseModel


class SearchResult(BaseModel):
    chunk_id: int
    document_id: int
    text: str
    score: float
    material_type: str
