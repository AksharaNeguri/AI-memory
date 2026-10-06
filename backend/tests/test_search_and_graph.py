from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import graph as graph_routes
from app.core.config import settings
from app.models.memory import Document
from app.services.embeddings import OpenAIEmbeddingProvider
from app.services.graph import (
    GraphConcept,
    GraphEntity,
    GraphLLMProvider,
    GraphRelationship,
    GraphRepository,
    GraphService,
    GraphTopic,
    KnowledgeGraphExtraction,
)
from tests.test_ingestion import TestEmbeddingProvider


@pytest.fixture(autouse=True)
def providers(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(
        "app.services.embeddings.get_embedding_provider",
        lambda: TestEmbeddingProvider(),
    )


class FakeGraphLLM(GraphLLMProvider):
    def extract_graph(self, text: str) -> KnowledgeGraphExtraction:
        assert "vector search" in text.lower()
        return KnowledgeGraphExtraction(
            concepts=[GraphConcept(name="Semantic Search", description="Meaning-based retrieval")],
            topics=[GraphTopic(name="Memory Systems")],
            entities=[GraphEntity(name="pgvector", entity_type="technology")],
            relationships=[
                GraphRelationship(
                    source_name="Semantic Search",
                    source_kind="concept",
                    target_name="pgvector",
                    target_kind="entity",
                    relationship_type="uses",
                    evidence="The document says vector search uses pgvector.",
                )
            ],
        )


class FakeGraphRepository(GraphRepository):
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.relationship_items: list[dict] = []
        self.user_id: str | None = None

    def upsert_document_graph(self, *, user_id, document: Document, extraction: KnowledgeGraphExtraction) -> dict:
        self.user_id = str(user_id)
        self.nodes = {
            "concept-1": {
                "id": "concept-1",
                "labels": ["Concept"],
                "name": extraction.concepts[0].name,
                "properties": {"user_id": str(user_id), "document_id": str(document.id)},
            },
            "entity-1": {
                "id": "entity-1",
                "labels": ["Entity"],
                "name": extraction.entities[0].name,
                "properties": {"user_id": str(user_id), "document_id": str(document.id)},
            },
        }
        self.relationship_items = [
            {
                "source": "concept-1",
                "target": "entity-1",
                "type": "USES",
                "properties": {"user_id": str(user_id), "document_id": str(document.id)},
            }
        ]
        return {
            "concepts": len(extraction.concepts),
            "topics": len(extraction.topics),
            "entities": len(extraction.entities),
            "relationships": len(extraction.relationships),
        }

    def search_nodes(self, *, user_id, query: str, limit: int) -> list[dict]:
        assert str(user_id) == self.user_id
        return [node for node in self.nodes.values() if query.lower() in node["name"].lower()][:limit]

    def get_relationships(self, *, user_id, node_id: str | None = None, limit: int = 100) -> list[dict]:
        assert str(user_id) == self.user_id
        if node_id:
            return [
                item
                for item in self.relationship_items
                if item["source"] == node_id or item["target"] == node_id
            ][:limit]
        return self.relationship_items[:limit]

    def related_concepts(self, *, user_id, node_id: str, limit: int) -> dict:
        assert str(user_id) == self.user_id
        return {
            "source_id": node_id,
            "source_name": self.nodes[node_id]["name"],
            "related": [{"id": "entity-1", "name": "pgvector", "relationship": "USES"}],
        }


def test_missing_embedding_credentials_raise_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "embedding_api_key", None)
    monkeypatch.setattr(settings, "llm_api_key", None)
    with pytest.raises(Exception, match="Embedding API credentials are not configured"):
        OpenAIEmbeddingProvider()


def test_graph_pipeline_end_to_end(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    created = client.post(
        "/documents/text",
        headers=auth_headers,
        json={
            "title": "Graph Source",
            "content": "Vector search uses pgvector in memory systems.",
        },
    ).json()
    repository = FakeGraphRepository()

    def override_graph_service() -> GraphService:
        return GraphService(db_session, llm=FakeGraphLLM(), repository=repository)

    client.app.dependency_overrides[graph_routes.get_graph_service] = override_graph_service
    try:
        extract = client.post(f"/graph/documents/{created['id']}/extract", headers=auth_headers)
        assert extract.status_code == 200
        assert extract.json()["concepts"] == 1
        assert extract.json()["relationships"] == 1

        document = db_session.get(Document, UUID(created["id"]))
        assert document is not None
        assert document.document_metadata["graph"]["entities"] == 1

        nodes = client.get("/graph/nodes?q=semantic", headers=auth_headers)
        assert nodes.status_code == 200
        assert nodes.json()["nodes"][0]["name"] == "Semantic Search"
        assert nodes.json()["relationships"][0]["type"] == "USES"

        relationships = client.get("/graph/relationships?node_id=concept-1", headers=auth_headers)
        assert relationships.status_code == 200
        assert relationships.json()[0]["target"] == "entity-1"

        related = client.get("/graph/nodes/concept-1/related", headers=auth_headers)
        assert related.status_code == 200
        assert related.json()["related"][0]["name"] == "pgvector"
    finally:
        client.app.dependency_overrides.pop(graph_routes.get_graph_service, None)
