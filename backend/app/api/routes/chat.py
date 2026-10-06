import json
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.auth import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.assistant import ChatAssistantService

router = APIRouter()


def get_chat_service(db: Annotated[Session, Depends(get_db)]) -> ChatAssistantService:
    return ChatAssistantService(db)


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChatAssistantService, Depends(get_chat_service)],
) -> ChatResponse | StreamingResponse:
    result = service.answer(
        current_user,
        message=payload.message,
        conversation_id=payload.conversation_id,
        history=payload.history,
        limit=payload.limit,
    )
    if not payload.stream:
        return result

    def events():
        for token in result["answer"].split(" "):
            yield json.dumps({"type": "answer_delta", "delta": token + " "}) + "\n"
        yield json.dumps(
            {
                "type": "done",
                "conversation_id": str(result["conversation_id"]),
                "message_id": str(result["message_id"]),
                "citations": [citation.model_dump(mode="json") for citation in result["citations"]],
                "grounded": result["grounded"],
                "retrieval": result["retrieval"],
            }
        ) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
