from uuid import UUID

from pydantic import BaseModel, Field


class GraphExtractResponse(BaseModel):
    document_id: UUID
    concepts: int
    topics: int
    entities: int
    relationships: int


class GraphNodeRead(BaseModel):
    id: str
    labels: list[str]
    name: str
    properties: dict


class GraphRelationshipRead(BaseModel):
    source: str
    target: str
    type: str
    properties: dict


class GraphSearchResponse(BaseModel):
    nodes: list[GraphNodeRead]
    relationships: list[GraphRelationshipRead]


class RelatedConceptsResponse(BaseModel):
    source_id: str
    source_name: str | None = None
    related: list[dict] = Field(default_factory=list)
