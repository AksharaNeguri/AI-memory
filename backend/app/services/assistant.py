from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from fastapi import status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.auth import User
from app.models.memory import Conversation, Document, DocumentChunk, Message
from app.schemas.chat import ChatHistoryMessage, SourceCitation
from app.services.embeddings import SearchService
from app.services.graph import GraphService, extract_response_text

STOPWORDS = {
    "about",
    "already",
    "and",
    "are",
    "connected",
    "did",
    "documents",
    "explain",
    "for",
    "how",
    "i",
    "is",
    "last",
    "learn",
    "mention",
    "mentions",
    "month",
    "my",
    "the",
    "using",
    "what",
    "which",
    "with",
}


@dataclass(frozen=True)
class QuestionUnderstanding:
    question: str
    keywords: list[str]
    intent: str
    start_date: datetime | None = None
    end_date: datetime | None = None


class ChatLLMProvider(ABC):
    @abstractmethod
    def generate(self, *, question: str, context: str, history: list[dict[str, str]]) -> str:
        raise NotImplementedError


class OpenAIChatLLMProvider(ChatLLMProvider):
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        if settings.llm_provider != "openai":
            raise AppError(
                f"Unsupported LLM provider: {settings.llm_provider}.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not self.api_key:
            raise AppError(
                "LLM API credentials are not configured. Set LLM_API_KEY.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    def generate(self, *, question: str, context: str, history: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a context-aware memory assistant. Answer in Markdown using only "
                        "the supplied user memory context. Never invent user memories. If the "
                        "context is insufficient, say that the saved memories do not contain enough "
                        "information. Cite every memory-backed claim with bracket citations like [1]."
                    ),
                },
                *history[-8:],
                {
                    "role": "user",
                    "content": f"Memory context:\n{context}\n\nQuestion: {question}",
                },
            ],
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
            return extract_response_text(response.json()).strip()
        except KeyError as exc:
            raise AppError("LLM provider returned an empty response.", status.HTTP_502_BAD_GATEWAY) from exc


class ChatAssistantService:
    def __init__(
        self,
        db: Session,
        *,
        llm: ChatLLMProvider | None = None,
        search_service: SearchService | None = None,
        graph_service: GraphService | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        self.search_service = search_service
        self.graph_service = graph_service

    def answer(
        self,
        user: User,
        *,
        message: str,
        conversation_id: UUID | None = None,
        history: list[ChatHistoryMessage] | None = None,
        limit: int = 8,
    ) -> dict:
        understanding = understand_question(message)
        conversation = self._get_or_create_conversation(user, conversation_id, message)
        persisted_history = self._conversation_history(conversation)
        explicit_history = [item.model_dump() for item in history or []]
        self.db.add(Message(conversation_id=conversation.id, role="user", content=message))
        self.db.flush()

        retrieval = self._retrieve(user, understanding, limit)
        citations = self._citations(retrieval["ranked_chunks"])
        if not citations:
            answer = (
                "I do not have any saved memories that answer this yet. "
                "I will avoid guessing because no retrieved document chunks support it."
            )
            grounded = False
        else:
            context = assemble_context(citations, retrieval["graph"])
            answer = (self.llm or OpenAIChatLLMProvider()).generate(
                question=message,
                context=context,
                history=[*persisted_history, *explicit_history],
            )
            grounded = True

        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            message_metadata={
                "citations": [citation.model_dump(mode="json") for citation in citations],
                "grounded": grounded,
                "retrieval": retrieval["metadata"],
            },
        )
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(assistant_message)
        return {
            "conversation_id": conversation.id,
            "message_id": assistant_message.id,
            "answer": answer,
            "citations": citations,
            "grounded": grounded,
            "retrieval": retrieval["metadata"],
        }

    def _retrieve(self, user: User, understanding: QuestionUnderstanding, limit: int) -> dict:
        vector_results = self._vector_retrieval(user, understanding, limit)
        keyword_results = self._keyword_retrieval(user, understanding, limit)
        graph = self._graph_retrieval(user, understanding)
        ranked_chunks = rank_results(vector_results, keyword_results, graph)
        return {
            "ranked_chunks": ranked_chunks[:limit],
            "graph": graph,
            "metadata": {
                "intent": understanding.intent,
                "keywords": understanding.keywords,
                "date_range": {
                    "start": understanding.start_date.isoformat() if understanding.start_date else None,
                    "end": understanding.end_date.isoformat() if understanding.end_date else None,
                },
                "vector_results": len(vector_results),
                "keyword_results": len(keyword_results),
                "graph_nodes": len(graph["nodes"]),
                "graph_relationships": len(graph["relationships"]),
            },
        }

    def _vector_retrieval(self, user: User, understanding: QuestionUnderstanding, limit: int) -> list[dict]:
        try:
            results = (self.search_service or SearchService(self.db)).search(
                user,
                query=understanding.question,
                limit=limit * 2,
                hybrid=True,
            )
        except AppError:
            return []
        return filter_results_by_date(results, understanding.start_date, understanding.end_date, self.db)

    def _keyword_retrieval(self, user: User, understanding: QuestionUnderstanding, limit: int) -> list[dict]:
        terms = expand_terms(understanding.keywords)
        if not terms:
            return []
        query = (
            self.db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(DocumentChunk.user_id == user.id)
        )
        if understanding.start_date:
            query = query.filter(Document.created_at >= understanding.start_date)
        if understanding.end_date:
            query = query.filter(Document.created_at < understanding.end_date)
        filters = [DocumentChunk.content.ilike(f"%{term}%") for term in terms]
        filters.extend(Document.title.ilike(f"%{term}%") for term in terms)
        query = query.filter(or_(*filters))
        results = []
        for chunk, document in query.limit(limit * 5).all():
            score = keyword_score(terms, f"{document.title}\n{chunk.content}")
            results.append(result_from_chunk(chunk, document, score, channel="keyword"))
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[: limit * 2]

    def _graph_retrieval(self, user: User, understanding: QuestionUnderstanding) -> dict:
        graph_service = self.graph_service or GraphService(self.db)
        nodes: list[dict] = []
        relationships: list[dict] = []
        seen_nodes: set[str] = set()
        for keyword in understanding.keywords[:4]:
            try:
                for node in graph_service.search_nodes(user, query=keyword, limit=8):
                    node_id = str(node.get("id"))
                    if node_id not in seen_nodes:
                        seen_nodes.add(node_id)
                        nodes.append(node)
            except AppError:
                break
        if nodes:
            try:
                relationships = graph_service.relationships(user, limit=50)
            except AppError:
                relationships = []
        return {"nodes": nodes, "relationships": relationships}

    def _get_or_create_conversation(
        self,
        user: User,
        conversation_id: UUID | None,
        message: str,
    ) -> Conversation:
        if conversation_id:
            conversation = (
                self.db.query(Conversation)
                .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
                .first()
            )
            if conversation is None:
                raise AppError("Conversation not found.", status.HTTP_404_NOT_FOUND)
            return conversation
        title = re.sub(r"\s+", " ", message).strip()[:80] or "New chat"
        conversation = Conversation(user_id=user.id, title=title)
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def _conversation_history(self, conversation: Conversation) -> list[dict[str, str]]:
        messages = (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(8)
            .all()
        )
        return [
            {"role": message.role, "content": message.content}
            for message in reversed(messages)
            if message.role in {"user", "assistant"}
        ]

    def _citations(self, ranked_chunks: list[dict]) -> list[SourceCitation]:
        citations = []
        for index, item in enumerate(ranked_chunks, start=1):
            citations.append(
                SourceCitation(
                    citation_id=index,
                    document_id=item["document_id"],
                    chunk_id=item["chunk_id"],
                    title=item["title"],
                    chunk_index=item["chunk_index"],
                    source_type=item["source_type"],
                    source_url=item.get("source_url"),
                    quote=snippet(item["content"]),
                    score=item["score"],
                )
            )
        return citations


def understand_question(question: str, *, now: datetime | None = None) -> QuestionUnderstanding:
    now = now or datetime.now(UTC)
    lowered = question.lower()
    start_date = None
    end_date = None
    if "last month" in lowered:
        first_this_month = datetime(now.year, now.month, 1, tzinfo=UTC)
        last_month_end = first_this_month
        previous_day = first_this_month - timedelta(days=1)
        start_date = datetime(previous_day.year, previous_day.month, 1, tzinfo=UTC)
        end_date = last_month_end
    keywords = [
        normalize_keyword(token)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*", lowered)
        if normalize_keyword(token) and normalize_keyword(token) not in STOPWORDS
    ]
    keywords = list(dict.fromkeys(keywords))[:10]
    if lowered.startswith("which documents") or "documents mention" in lowered:
        intent = "document_lookup"
    elif "connected" in lowered or "connection" in lowered:
        intent = "relationship"
    elif "explain" in lowered:
        intent = "explanation"
    else:
        intent = "question_answering"
    return QuestionUnderstanding(
        question=question,
        keywords=keywords,
        intent=intent,
        start_date=start_date,
        end_date=end_date,
    )


def normalize_keyword(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 3 and value.endswith("s"):
        return value[:-1]
    return value


def expand_terms(terms: list[str]) -> list[str]:
    expanded = set(terms)
    for term in terms:
        if term == "api":
            expanded.add("apis")
        elif len(term) > 2:
            expanded.add(f"{term}s")
    return list(expanded)


def filter_results_by_date(
    results: list[dict],
    start_date: datetime | None,
    end_date: datetime | None,
    db: Session,
) -> list[dict]:
    if not start_date and not end_date:
        return results
    filtered = []
    for result in results:
        document = db.get(Document, result["document_id"])
        if document is None:
            continue
        created_at = document.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if start_date and created_at < start_date:
            continue
        if end_date and created_at >= end_date:
            continue
        filtered.append(result)
    return filtered


def result_from_chunk(chunk: DocumentChunk, document: Document, score: float, *, channel: str) -> dict:
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
        "channels": {channel},
    }


def rank_results(vector_results: list[dict], keyword_results: list[dict], graph: dict) -> list[dict]:
    combined: dict[Any, dict] = {}
    scores: defaultdict[Any, float] = defaultdict(float)
    graph_terms = {str(node.get("name", "")).lower() for node in graph["nodes"]}
    for channel, results, weight in (("vector", vector_results, 0.65), ("keyword", keyword_results, 0.45)):
        for item in results:
            key = item["chunk_id"]
            combined.setdefault(key, {**item, "channels": set()})
            combined[key]["channels"].add(channel)
            scores[key] += float(item.get("score") or 0.0) * weight
            content = f"{item.get('title', '')} {item.get('content', '')}".lower()
            if any(term and term in content for term in graph_terms):
                scores[key] += 0.15
    ranked = []
    for key, item in combined.items():
        ranked.append({**item, "score": scores[key], "channels": sorted(item["channels"])})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def keyword_score(terms: list[str], text: str) -> float:
    haystack = text.lower()
    if not terms:
        return 0.0
    return sum(1 for term in terms if term in haystack) / len(terms)


def snippet(content: str, *, max_length: int = 320) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 1].rstrip()}..."


def assemble_context(citations: list[SourceCitation], graph: dict) -> str:
    source_lines = [
        (
            f"[{citation.citation_id}] {citation.title} "
            f"(document_id={citation.document_id}, chunk={citation.chunk_index}): "
            f"{citation.quote}"
        )
        for citation in citations
    ]
    graph_lines = []
    for node in graph["nodes"][:10]:
        graph_lines.append(f"- Node: {node.get('name')} labels={node.get('labels', [])}")
    for relationship in graph["relationships"][:10]:
        graph_lines.append(
            f"- Relationship: {relationship.get('source')} -[{relationship.get('type')}]-> {relationship.get('target')}"
        )
    graph_context = "\n".join(graph_lines) if graph_lines else "No graph context retrieved."
    return "Sources:\n" + "\n".join(source_lines) + "\n\nGraph context:\n" + graph_context
