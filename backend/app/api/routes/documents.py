from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.auth import User
from app.models.memory import Document
from app.schemas.documents import (
    DocumentDetailRead,
    DocumentRead,
    DocumentStatusRead,
    TextIngestRequest,
    UrlIngestRequest,
)
from app.services.ingestion import IngestionService

router = APIRouter()


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> Document:
    return IngestionService(db).ingest_upload(current_user, file)


@router.post("/text", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def ingest_text(
    payload: TextIngestRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    return IngestionService(db).ingest_text(
        current_user,
        title=payload.title,
        content=payload.content,
    )


@router.post("/url", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def ingest_url(
    payload: UrlIngestRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    return IngestionService(db).ingest_url(
        current_user,
        url=str(payload.url),
        title=payload.title,
    )


@router.get("", response_model=list[DocumentRead])
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Document]:
    return IngestionService(db).list_documents(current_user)


@router.get("/{document_id}", response_model=DocumentDetailRead)
def get_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    return IngestionService(db).get_document(current_user, document_id)


@router.get("/{document_id}/status", response_model=DocumentStatusRead)
def get_document_status(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    return IngestionService(db).get_document(current_user, document_id)
