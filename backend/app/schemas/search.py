from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    document_id: UUID | None = None
    source_type: str | None = None
    metadata: dict | None = None
    hybrid: bool = False


class SearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    content: str
    chunk_index: int
    score: float
    source_type: str
    source_url: str | None
    chunk_metadata: dict
    semantic_score: float | None = None
    keyword_score: float | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
