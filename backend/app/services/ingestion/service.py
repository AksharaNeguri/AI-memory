from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.auth import User
from app.models.memory import Document, DocumentChunk
from app.services.embeddings import SearchService
from app.services.ingestion.chunking import TextChunker
from app.services.ingestion.cleaning import clean_text
from app.services.ingestion.extractors import ExtractorRegistry, UrlExtractor
from app.services.ingestion.types import ExtractedDocument


class DocumentStatus:
    uploaded = "UPLOADED"
    processing = "PROCESSING"
    completed = "COMPLETED"
    failed = "FAILED"


class SourceType:
    file = "FILE"
    text = "TEXT"
    url = "URL"


class IngestionService:
    def __init__(
        self,
        db: Session,
        *,
        registry: ExtractorRegistry | None = None,
        chunker: TextChunker | None = None,
        search_service: SearchService | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or ExtractorRegistry()
        self.chunker = chunker or TextChunker()
        self.search_service = search_service
        self.max_bytes = settings.max_upload_mb * 1024 * 1024

    def ingest_upload(self, user: User, upload: UploadFile) -> Document:
        content = upload.file.read()
        self._validate_size(len(content))
        self._validate_non_empty(content)
        extractor = self.registry.for_file(upload.filename, upload.content_type)
        document = self._create_document(
            user=user,
            title=upload.filename or "Uploaded document",
            source_type=SourceType.file,
            mime_type=upload.content_type,
            original_filename=upload.filename,
            file_size_bytes=len(content),
        )
        file_path = self._persist_upload(user.id, document.id, upload.filename, content)
        document.file_path = str(file_path)
        self.db.commit()

        extracted = extractor.extract(content, filename=upload.filename, mime_type=upload.content_type)
        return self._process_extracted(document, extracted)

    def ingest_text(
        self,
        user: User,
        *,
        title: str,
        content: str,
        source_type: str = SourceType.text,
        metadata: dict | None = None,
    ) -> Document:
        encoded = content.encode("utf-8")
        self._validate_size(len(encoded))
        if not content.strip():
            raise AppError("Text content cannot be empty.")
        document = self._create_document(
            user=user,
            title=title,
            source_type=source_type,
            mime_type="text/plain",
            file_size_bytes=len(encoded),
        )
        extracted = ExtractedDocument(
            text=content,
            metadata={"extractor": "plain_text", **(metadata or {})},
        )
        return self._process_extracted(document, extracted)

    def ingest_url(self, user: User, *, url: str, title: str | None = None) -> Document:
        document = self._create_document(
            user=user,
            title=title or url,
            source_type=SourceType.url,
            source_url=url,
        )
        try:
            extracted = UrlExtractor(max_response_bytes=self.max_bytes).extract(url)
            if not title and extracted.metadata.get("title"):
                document.title = extracted.metadata["title"][:255]
            return self._process_extracted(document, extracted)
        except Exception as exc:
            self._mark_failed(document, exc)
            raise

    def list_documents(self, user: User) -> list[Document]:
        return (
            self.db.query(Document)
            .filter(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
            .all()
        )

    def get_document(self, user: User, document_id: UUID) -> Document:
        document = (
            self.db.query(Document)
            .filter(Document.id == document_id, Document.user_id == user.id)
            .first()
        )
        if document is None:
            raise AppError("Document not found.", status.HTTP_404_NOT_FOUND)
        return document

    def _process_extracted(self, document: Document, extracted: ExtractedDocument) -> Document:
        document.processing_status = DocumentStatus.processing
        document.error_message = None
        self.db.commit()
        try:
            cleaned = clean_text(extracted.text)
            if not cleaned:
                raise AppError("No extractable text was found.")
            chunks = self.chunker.chunk(cleaned)
            if not chunks:
                raise AppError("No chunks were produced from extracted text.")
            checksum = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
            document.summary = cleaned[:500]
            document.document_metadata = {
                **(document.document_metadata or {}),
                **extracted.metadata,
                "character_count": len(cleaned),
                "chunk_count": len(chunks),
                "sha256": checksum,
            }
            self.db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
            chunk_models = [
                DocumentChunk(
                    document_id=document.id,
                    user_id=document.user_id,
                    content=chunk.content,
                    chunk_index=chunk.index,
                    chunk_metadata={
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "character_count": len(chunk.content),
                    },
                )
                for chunk in chunks
            ]
            search_service = self.search_service or SearchService(self.db)
            search_service.embed_chunks(chunk_models)
            document.processing_status = DocumentStatus.completed
            self.db.add_all(chunk_models)
            self.db.commit()
            self.db.refresh(document)
            return document
        except Exception as exc:
            self._mark_failed(document, exc)
            raise

    def _create_document(
        self,
        *,
        user: User,
        title: str,
        source_type: str,
        source_url: str | None = None,
        mime_type: str | None = None,
        original_filename: str | None = None,
        file_size_bytes: int | None = None,
    ) -> Document:
        document = Document(
            user_id=user.id,
            title=title[:255],
            source_type=source_type,
            source_url=source_url,
            mime_type=mime_type,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            processing_status=DocumentStatus.uploaded,
            document_metadata={},
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def _persist_upload(
        self,
        user_id: UUID,
        document_id: UUID,
        filename: str | None,
        content: bytes,
    ) -> Path:
        safe_name = Path(filename or "upload.bin").name
        upload_dir = Path(settings.upload_dir) / str(user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / f"{document_id}_{safe_name}"
        with path.open("wb") as output:
            output.write(content)
        return path

    def _validate_size(self, size: int) -> None:
        if size > self.max_bytes:
            raise AppError(
                f"Input exceeds maximum size of {settings.max_upload_mb} MB.",
                status.HTTP_413_CONTENT_TOO_LARGE,
            )

    def _validate_non_empty(self, content: bytes) -> None:
        if not content:
            raise AppError("Uploaded file cannot be empty.")

    def _mark_failed(self, document: Document, exc: Exception) -> None:
        document.processing_status = DocumentStatus.failed
        document.error_message = str(exc)
        self.db.commit()


def clear_uploads(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
