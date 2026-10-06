from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.auth import User
from app.schemas.search import SearchRequest, SearchResponse
from app.services.embeddings import SearchService

router = APIRouter()


@router.post("", response_model=SearchResponse)
def semantic_search(
    payload: SearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SearchResponse:
    results = SearchService(db).search(
        current_user,
        query=payload.query,
        limit=payload.limit,
        document_id=payload.document_id,
        source_type=payload.source_type,
        metadata=payload.metadata,
        hybrid=payload.hybrid,
    )
    return SearchResponse(query=payload.query, results=results)
