from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

import httpx
from fastapi import status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.auth import User
from app.models.memory import Document, DocumentChunk, SearchHistory


class EmbeddingProvider(ABC):
    model: str
    dimensions: int

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.embedding_api_key or settings.llm_api_key
        self.model = model or settings.embedding_model
        self.dimensions = dimensions or settings.embedding_dimensions
        if settings.embedding_provider != "openai":
            raise AppError(
                f"Unsupported embedding provider: {settings.embedding_provider}.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not self.api_key:
            raise AppError(
                "Embedding API credentials are not configured. Set EMBEDDING_API_KEY or LLM_API_KEY.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        try:
            response = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError("Embedding provider request failed.", status.HTTP_502_BAD_GATEWAY) from exc
        data = response.json().get("data", [])
        embeddings = [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]
        if len(embeddings) != len(texts):
            raise AppError("Embedding provider returned an unexpected response.", status.HTTP_502_BAD_GATEWAY)
        return embeddings


def get_embedding_provider() -> EmbeddingProvider:
    return OpenAIEmbeddingProvider()


def serialize_embedding(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


def deserialize_embedding(value: str | None) -> list[float] | None:
    if not value:
        return None
    parsed = json.loads(value)
    return [float(item) for item in parsed]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


class SearchService:
    def __init__(self, db: Session, *, provider: EmbeddingProvider | None = None) -> None:
        self.db = db
        self.provider = provider or get_embedding_provider()

    def embed_chunks(self, chunks: list[DocumentChunk]) -> None:
        texts = [chunk.content for chunk in chunks]
        embeddings = self.provider.embed_texts(texts)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk.embedding = serialize_embedding(embedding)
            chunk.embedding_model = self.provider.model
            chunk.embedding_dimensions = len(embedding)

    def search(
        self,
        user: User,
        *,
        query: str,
        limit: int = 10,
        document_id: UUID | None = None,
        source_type: str | None = None,
        metadata: dict | None = None,
        hybrid: bool = False,
    ) -> list[dict]:
        if not query.strip():
            raise AppError("Search query cannot be empty.")
        query_embedding = self.provider.embed_texts([query])[0]
        self.db.add(SearchHistory(user_id=user.id, query=query, filters=self._filters(document_id, source_type, metadata)))
        self.db.commit()
        if self.db.bind and self.db.bind.dialect.name == "postgresql" and not hybrid:
            return self._search_postgres(user, query_embedding, limit, document_id, source_type, metadata)
        return self._search_python(user, query, query_embedding, limit, document_id, source_type, metadata, hybrid)

    def _search_python(
        self,
        user: User,
        query_text: str,
        query_embedding: list[float],
        limit: int,
        document_id: UUID | None,
        source_type: str | None,
        metadata: dict | None,
        hybrid: bool,
    ) -> list[dict]:
        query = (
            self.db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(DocumentChunk.user_id == user.id, DocumentChunk.embedding.isnot(None))
        )
        if document_id:
            query = query.filter(Document.id == document_id)
        if source_type:
            query = query.filter(Document.source_type == source_type)
        results = []
        for chunk, document in query.all():
            if metadata and not self._metadata_matches(document.document_metadata or {}, metadata):
                continue
            embedding = deserialize_embedding(chunk.embedding)
            if embedding is None:
                continue
            semantic_score = cosine_similarity(query_embedding, embedding)
            keyword_score = self._keyword_score(query_text, chunk.content) if hybrid else 0.0
            score = (semantic_score * 0.75) + (keyword_score * 0.25) if hybrid else semantic_score
            result = self._result(chunk, document, score)
            result["semantic_score"] = semantic_score
            result["keyword_score"] = keyword_score
            results.append(result)
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    def _search_postgres(
        self,
        user: User,
        query_embedding: list[float],
        limit: int,
        document_id: UUID | None,
        source_type: str | None,
        metadata: dict | None,
    ) -> list[dict]:
        clauses = ["dc.user_id = :user_id", "dc.embedding IS NOT NULL"]
        params: dict[str, Any] = {
            "user_id": user.id,
            "embedding": serialize_embedding(query_embedding),
            "limit": limit,
        }
        if document_id:
            clauses.append("d.id = :document_id")
            params["document_id"] = document_id
        if source_type:
            clauses.append("d.source_type = :source_type")
            params["source_type"] = source_type
        if metadata:
            clauses.append("CAST(d.metadata AS jsonb) @> CAST(:metadata AS jsonb)")
            params["metadata"] = json.dumps(metadata)
        sql = text(
            "SELECT dc.id AS chunk_id, dc.content, dc.chunk_index, dc.metadata AS chunk_metadata, "
            "d.id AS document_id, d.title, d.source_type, d.source_url, "
            "1 - (dc.embedding <=> CAST(:embedding AS vector)) AS score "
            "FROM document_chunks dc JOIN documents d ON d.id = dc.document_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY dc.embedding <=> CAST(:embedding AS vector) LIMIT :limit"
        )
        return [dict(row._mapping) for row in self.db.execute(sql, params)]

    def _result(self, chunk: DocumentChunk, document: Document, score: float) -> dict:
        return {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "title": document.title,
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
            "score": score,
            "source_type": document.source_type,
            "source_url": document.source_url,
            "chunk_metadata": chunk.chunk_metadata,
        }

    def _filters(self, document_id: UUID | None, source_type: str | None, metadata: dict | None) -> dict:
        return {
            "document_id": str(document_id) if document_id else None,
            "source_type": source_type,
            "metadata": metadata or {},
        }

    def _metadata_matches(self, source: dict, expected: dict) -> bool:
        return all(source.get(key) == value for key, value in expected.items())

    def _keyword_score(self, query: str, content: str) -> float:
        terms = {term.lower() for term in query.split() if term.strip()}
        if not terms:
            return 0.0
        content_lower = content.lower()
        matches = sum(1 for term in terms if term in content_lower)
        return matches / len(terms)
