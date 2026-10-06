from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatHistoryMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: UUID | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list)
    stream: bool = False
    limit: int = Field(default=8, ge=1, le=20)


class SourceCitation(BaseModel):
    citation_id: int
    document_id: UUID
    chunk_id: UUID
    title: str
    chunk_index: int
    source_type: str
    source_url: str | None = None
    quote: str
    score: float


class ChatMessageRead(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    message_metadata: dict

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    citations: list[SourceCitation]
    grounded: bool
    retrieval: dict
