from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import chat as chat_routes
from app.core.config import settings
from app.models.memory import Document, Message
from app.services.assistant import ChatAssistantService, ChatLLMProvider
from tests.test_ingestion import TestEmbeddingProvider


@pytest.fixture(autouse=True)
def chat_providers(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(
        "app.services.embeddings.get_embedding_provider",
        lambda: TestEmbeddingProvider(),
    )


class FakeChatLLM(ChatLLMProvider):
    def generate(self, *, question: str, context: str, history: list[dict[str, str]]) -> str:
        assert "Sources:" in context
        assert "[1]" in context
        lowered = question.lower()
        if "last month" in lowered:
            return "Last month, your saved notes say you learned that APIs expose endpoints and request/response contracts. [1]"
        if "fastapi" in lowered:
            return "FastAPI connects to what you know about APIs: it lets Python define HTTP endpoints and request/response behavior. [1]"
        if "which documents" in lowered:
            return "The retrieved documents that mention Python include **Python ML Notes** and **FastAPI Bridge**. [1] [2]"
        if "machine learning" in lowered:
            return "Python is connected to machine learning in your notes through scikit-learn workflows and model training examples. [1]"
        return "The saved memory context supports this answer. [1]"


class FakeGraphService:
    def search_nodes(self, user, *, query: str, limit: int = 25) -> list[dict]:
        if query in {"python", "machine", "learning", "fastapi", "api"}:
            return [
                {
                    "id": "python-node",
                    "labels": ["Concept"],
                    "name": "Python",
                    "properties": {"user_id": str(user.id)},
                },
                {
                    "id": "ml-node",
                    "labels": ["Concept"],
                    "name": "Machine Learning",
                    "properties": {"user_id": str(user.id)},
                },
            ][:limit]
        return []

    def relationships(self, user, *, node_id: str | None = None, limit: int = 100) -> list[dict]:
        return [
            {
                "source": "python-node",
                "target": "ml-node",
                "type": "USED_FOR",
                "properties": {"evidence": "Python examples use scikit-learn for model training."},
            }
        ][:limit]


def override_chat_service(db_session: Session) -> ChatAssistantService:
    return ChatAssistantService(db_session, llm=FakeChatLLM(), graph_service=FakeGraphService())


def ingest_memory_documents(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    api_doc = client.post(
        "/documents/text",
        headers=auth_headers,
        json={
            "title": "API Learning Log",
            "content": "I learned that APIs expose endpoints and request response contracts.",
        },
    ).json()
    document = db_session.get(Document, UUID(api_doc["id"]))
    assert document is not None
    document.created_at = datetime(2026, 9, 12, tzinfo=UTC)
    document.updated_at = datetime(2026, 9, 12, tzinfo=UTC)

    client.post(
        "/documents/text",
        headers=auth_headers,
        json={
            "title": "FastAPI Bridge",
            "content": "FastAPI uses Python to define API endpoints and response models.",
        },
    )
    client.post(
        "/documents/text",
        headers=auth_headers,
        json={
            "title": "Python ML Notes",
            "content": "Python connects to machine learning through scikit-learn model training.",
        },
    )
    db_session.commit()


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "What did I learn about APIs last month?",
            "APIs expose endpoints",
        ),
        (
            "Explain FastAPI using what I already know.",
            "Python define HTTP endpoints",
        ),
        (
            "Which documents mention Python?",
            "Python ML Notes",
        ),
        (
            "How is Python connected to machine learning?",
            "scikit-learn workflows",
        ),
    ],
)
def test_chat_answers_are_grounded_with_citations(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    question: str,
    expected: str,
) -> None:
    ingest_memory_documents(client, auth_headers, db_session)
    client.app.dependency_overrides[chat_routes.get_chat_service] = lambda: override_chat_service(db_session)
    try:
        response = client.post("/chat", headers=auth_headers, json={"message": question})
    finally:
        client.app.dependency_overrides.pop(chat_routes.get_chat_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert expected in payload["answer"]
    assert payload["grounded"] is True
    assert payload["citations"]
    assert "[1]" in payload["answer"]

    messages = db_session.query(Message).filter_by(conversation_id=UUID(payload["conversation_id"])).all()
    assert [message.role for message in messages] == ["user", "assistant"]
    assistant = messages[-1]
    assert assistant.message_metadata["citations"]
    assert assistant.message_metadata["grounded"] is True


def test_chat_refuses_to_invent_without_retrieved_memories(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    client.app.dependency_overrides[chat_routes.get_chat_service] = lambda: override_chat_service(db_session)
    try:
        response = client.post("/chat", headers=auth_headers, json={"message": "What did I learn about Rust?"})
    finally:
        client.app.dependency_overrides.pop(chat_routes.get_chat_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["grounded"] is False
    assert payload["citations"] == []
    assert "avoid guessing" in payload["answer"]
