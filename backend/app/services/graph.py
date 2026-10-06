from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

import httpx
from fastapi import status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.auth import User
from app.models.memory import Document, DocumentChunk


class GraphConcept(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None


class GraphTopic(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None


class GraphEntity(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    entity_type: str = Field(min_length=1, max_length=80)
    description: str | None = None


class GraphRelationship(BaseModel):
    source_name: str = Field(min_length=1, max_length=160)
    source_kind: str = Field(pattern="^(concept|topic|entity)$")
    target_name: str = Field(min_length=1, max_length=160)
    target_kind: str = Field(pattern="^(concept|topic|entity)$")
    relationship_type: str = Field(min_length=1, max_length=80)
    evidence: str = Field(min_length=1, max_length=500)


class KnowledgeGraphExtraction(BaseModel):
    concepts: list[GraphConcept] = Field(default_factory=list)
    topics: list[GraphTopic] = Field(default_factory=list)
    entities: list[GraphEntity] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)


class GraphLLMProvider(ABC):
    @abstractmethod
    def extract_graph(self, text: str) -> KnowledgeGraphExtraction:
        raise NotImplementedError


class OpenAIGraphLLMProvider(GraphLLMProvider):
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        if not self.api_key:
            raise AppError(
                "LLM API credentials are not configured. Set LLM_API_KEY.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    def extract_graph(self, text: str) -> KnowledgeGraphExtraction:
        schema = KnowledgeGraphExtraction.model_json_schema()
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Extract concepts, topics, entities, and typed relationships from the "
                        "document text. Return only data supported by evidence in the text."
                    ),
                },
                {"role": "user", "content": text[:12000]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "knowledge_graph_extraction",
                    "schema": schema,
                    "strict": False,
                }
            },
        }
        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError("LLM provider request failed.", status.HTTP_502_BAD_GATEWAY) from exc
        try:
            return KnowledgeGraphExtraction.model_validate_json(extract_response_text(response.json()))
        except (KeyError, ValidationError, ValueError) as exc:
            raise AppError("LLM provider returned invalid graph output.", status.HTTP_502_BAD_GATEWAY) from exc


class GraphRepository(ABC):
    @abstractmethod
    def upsert_document_graph(
        self,
        *,
        user_id: UUID,
        document: Document,
        extraction: KnowledgeGraphExtraction,
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    def search_nodes(self, *, user_id: UUID, query: str, limit: int) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_relationships(self, *, user_id: UUID, node_id: str | None = None, limit: int = 100) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def related_concepts(self, *, user_id: UUID, node_id: str, limit: int) -> dict:
        raise NotImplementedError


class Neo4jGraphRepository(GraphRepository):
    def __init__(self) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise AppError("Neo4j driver is not installed.", status.HTTP_503_SERVICE_UNAVAILABLE) from exc
        if not settings.neo4j_uri or not settings.neo4j_username or not settings.neo4j_password:
            raise AppError("Neo4j credentials are not configured.", status.HTTP_503_SERVICE_UNAVAILABLE)
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

    def upsert_document_graph(
        self,
        *,
        user_id: UUID,
        document: Document,
        extraction: KnowledgeGraphExtraction,
    ) -> dict:
        with self.driver.session() as session:
            session.execute_write(self._write_graph, str(user_id), document, extraction)
        return {
            "concepts": len(extraction.concepts),
            "topics": len(extraction.topics),
            "entities": len(extraction.entities),
            "relationships": len(extraction.relationships),
        }

    def search_nodes(self, *, user_id: UUID, query: str, limit: int) -> list[dict]:
        cypher = """
        MATCH (n {user_id: $user_id})
        WHERE toLower(n.name) CONTAINS toLower($query)
        RETURN elementId(n) AS id, labels(n) AS labels, n.name AS name, properties(n) AS properties
        LIMIT $limit
        """
        with self.driver.session() as session:
            return [dict(record) for record in session.run(cypher, user_id=str(user_id), query=query, limit=limit)]

    def get_relationships(self, *, user_id: UUID, node_id: str | None = None, limit: int = 100) -> list[dict]:
        if node_id:
            cypher = """
            MATCH (a {user_id: $user_id})-[r]-(b {user_id: $user_id})
            WHERE elementId(a) = $node_id
            RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type, properties(r) AS properties
            LIMIT $limit
            """
        else:
            cypher = """
            MATCH (a {user_id: $user_id})-[r]->(b {user_id: $user_id})
            RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type, properties(r) AS properties
            LIMIT $limit
            """
        with self.driver.session() as session:
            return [
                dict(record)
                for record in session.run(cypher, user_id=str(user_id), node_id=node_id, limit=limit)
            ]

    def related_concepts(self, *, user_id: UUID, node_id: str, limit: int) -> dict:
        cypher = """
        MATCH (n {user_id: $user_id})-[r]-(m {user_id: $user_id})
        WHERE elementId(n) = $node_id
        RETURN elementId(n) AS source_id, n.name AS source_name,
               collect({id: elementId(m), name: m.name, labels: labels(m), relationship: type(r)})[..$limit] AS related
        """
        with self.driver.session() as session:
            record = session.run(cypher, user_id=str(user_id), node_id=node_id, limit=limit).single()
            return dict(record) if record else {"source_id": node_id, "related": []}

    @staticmethod
    def _write_graph(tx: Any, user_id: str, document: Document, extraction: KnowledgeGraphExtraction) -> None:
        tx.run(
            """
            MERGE (d:Document {user_id: $user_id, document_id: $document_id})
            SET d.name = $title, d.title = $title, d.source_type = $source_type, d.source_url = $source_url
            """,
            user_id=user_id,
            document_id=str(document.id),
            title=document.title,
            source_type=document.source_type,
            source_url=document.source_url,
        )
        for item in extraction.concepts:
            Neo4jGraphRepository._merge_node(tx, user_id, document, "Concept", item.name, item.model_dump())
        for item in extraction.topics:
            Neo4jGraphRepository._merge_node(tx, user_id, document, "Topic", item.name, item.model_dump())
        for item in extraction.entities:
            props = item.model_dump()
            props["entity_type"] = item.entity_type
            Neo4jGraphRepository._merge_node(tx, user_id, document, "Entity", item.name, props)
        for relationship in extraction.relationships:
            Neo4jGraphRepository._merge_relationship(tx, user_id, document, relationship)

    @staticmethod
    def _merge_node(tx: Any, user_id: str, document: Document, label: str, name: str, props: dict) -> None:
        cypher = f"""
        MERGE (n:{label} {{user_id: $user_id, name: $name}})
        SET n += $props
        WITH n
        MATCH (d:Document {{user_id: $user_id, document_id: $document_id}})
        MERGE (d)-[:MENTIONS]->(n)
        """
        tx.run(cypher, user_id=user_id, name=name, props=props, document_id=str(document.id))

    @staticmethod
    def _merge_relationship(
        tx: Any,
        user_id: str,
        document: Document,
        relationship: GraphRelationship,
    ) -> None:
        rel_type = sanitize_relationship_type(relationship.relationship_type)
        source_label = kind_to_label(relationship.source_kind)
        target_label = kind_to_label(relationship.target_kind)
        cypher = f"""
        MATCH (a:{source_label} {{user_id: $user_id, name: $source_name}})
        MATCH (b:{target_label} {{user_id: $user_id, name: $target_name}})
        MERGE (a)-[r:{rel_type} {{user_id: $user_id, document_id: $document_id}}]->(b)
        SET r.evidence = $evidence
        """
        tx.run(
            cypher,
            user_id=user_id,
            source_name=relationship.source_name,
            target_name=relationship.target_name,
            document_id=str(document.id),
            evidence=relationship.evidence,
        )


class GraphService:
    def __init__(
        self,
        db: Session,
        *,
        llm: GraphLLMProvider | None = None,
        repository: GraphRepository | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        self.repository = repository

    def extract_document_graph(self, user: User, document_id: UUID) -> dict:
        document = (
            self.db.query(Document)
            .filter(Document.id == document_id, Document.user_id == user.id)
            .first()
        )
        if document is None:
            raise AppError("Document not found.", status.HTTP_404_NOT_FOUND)
        chunks = (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document.id, DocumentChunk.user_id == user.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        if not chunks:
            raise AppError("Document has no chunks to extract.")
        text = "\n\n".join(chunk.content for chunk in chunks)
        extraction = (self.llm or OpenAIGraphLLMProvider()).extract_graph(text)
        summary = (self.repository or Neo4jGraphRepository()).upsert_document_graph(
            user_id=user.id,
            document=document,
            extraction=extraction,
        )
        document.document_metadata = {
            **(document.document_metadata or {}),
            "graph": {
                **summary,
                "extraction": json.loads(extraction.model_dump_json()),
            },
        }
        self.db.commit()
        return summary

    def search_nodes(self, user: User, *, query: str, limit: int = 25) -> list[dict]:
        return (self.repository or Neo4jGraphRepository()).search_nodes(
            user_id=user.id,
            query=query,
            limit=limit,
        )

    def relationships(self, user: User, *, node_id: str | None = None, limit: int = 100) -> list[dict]:
        return (self.repository or Neo4jGraphRepository()).get_relationships(
            user_id=user.id,
            node_id=node_id,
            limit=limit,
        )

    def related_concepts(self, user: User, *, node_id: str, limit: int = 25) -> dict:
        return (self.repository or Neo4jGraphRepository()).related_concepts(
            user_id=user.id,
            node_id=node_id,
            limit=limit,
        )


def sanitize_relationship_type(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip().upper())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "RELATED_TO"


def kind_to_label(kind: str) -> str:
    return {"concept": "Concept", "topic": "Topic", "entity": "Entity"}[kind]


def extract_response_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return str(content["text"])
    raise KeyError("output_text")
