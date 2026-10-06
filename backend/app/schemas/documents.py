from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class TextIngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class UrlIngestRequest(BaseModel):
    url: HttpUrl
    title: str | None = Field(default=None, max_length=255)


class DocumentChunkRead(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    chunk_metadata: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentRead(BaseModel):
    id: UUID
    title: str
    source_type: str
    source_url: str | None
    file_path: str | None
    original_filename: str | None
    file_size_bytes: int | None
    mime_type: str | None
    summary: str | None
    processing_status: str
    error_message: str | None
    document_metadata: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailRead(DocumentRead):
    chunks: list[DocumentChunkRead]


class DocumentStatusRead(BaseModel):
    id: UUID
    processing_status: str
    error_message: str | None
    document_metadata: dict

    model_config = {"from_attributes": True}
