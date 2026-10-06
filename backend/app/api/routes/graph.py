from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.auth import User
from app.schemas.graph import (
    GraphExtractResponse,
    GraphRelationshipRead,
    GraphSearchResponse,
    RelatedConceptsResponse,
)
from app.services.graph import GraphService

router = APIRouter()


def get_graph_service(db: Annotated[Session, Depends(get_db)]) -> GraphService:
    return GraphService(db)


@router.post("/documents/{document_id}/extract", response_model=GraphExtractResponse)
def extract_document_graph(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[GraphService, Depends(get_graph_service)],
) -> GraphExtractResponse:
    summary = service.extract_document_graph(current_user, document_id)
    return GraphExtractResponse(document_id=document_id, **summary)


@router.get("/nodes", response_model=GraphSearchResponse)
def search_nodes(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[GraphService, Depends(get_graph_service)],
    q: str = Query(default="", max_length=160),
    limit: int = Query(default=25, ge=1, le=100),
) -> GraphSearchResponse:
    nodes = service.search_nodes(current_user, query=q, limit=limit)
    relationships = service.relationships(current_user, limit=100)
    return GraphSearchResponse(nodes=nodes, relationships=relationships)


@router.get("/relationships", response_model=list[GraphRelationshipRead])
def relationships(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[GraphService, Depends(get_graph_service)],
    node_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=250),
) -> list[dict]:
    return service.relationships(current_user, node_id=node_id, limit=limit)


@router.get("/nodes/{node_id}/related", response_model=RelatedConceptsResponse)
def related_concepts(
    node_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[GraphService, Depends(get_graph_service)],
    limit: int = Query(default=25, ge=1, le=100),
) -> dict:
    return service.related_concepts(current_user, node_id=node_id, limit=limit)
