"""Session management router for IntentFlow.

Handles session creation with optional category pre-selection.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.session_store import create_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    """Optional request body for session creation."""

    category: str | None = Field(
        default=None,
        max_length=50,
        description="Optional pre-selected category from homepage",
    )


class CreateSessionResponse(BaseModel):
    """Response body for session creation."""

    session_id: str = Field(..., alias="sessionId")
    message: str
    user_id: str = Field(..., alias="userId")

    model_config = {"populate_by_name": True}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session_endpoint(
    request: Request,
    body: CreateSessionRequest | None = None,
):
    """Create a new conversational shopping session.

    Generates a UUID v4 session ID, persists session state,
    and returns the greeting message.
    """
    user_id: str = request.state.user_id
    correlation_id: str = getattr(request.state, "correlation_id", "unknown")

    session_id = str(uuid.uuid4())
    category = body.category if body else None

    try:
        create_session(session_id, user_id, category)
    except Exception:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "PROCESSING_ERROR",
                    "message": "Something went wrong. Please try again.",
                    "correlationId": correlation_id,
                }
            },
        )

    return JSONResponse(
        status_code=201,
        content={
            "sessionId": session_id,
            "message": "Hi! I'm here to help you find exactly what you need. What are you looking for today?",
            "userId": user_id,
        },
    )
