"""Session data model for IntentFlow."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ConversationMessage(BaseModel):
    """A single message in the conversation history."""

    role: str = Field(..., description="Message role: 'user' or 'agent'")
    text: str = Field(..., description="Message text content")
    timestamp: str = Field(..., description="ISO 8601 timestamp")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("user", "agent"):
            raise ValueError("role must be 'user' or 'agent'")
        return v


class Session(BaseModel):
    """Session state persisted in DynamoDB."""

    session_id: str = Field(..., alias="sessionId", description="UUID v4 session identifier")
    user_id: str = Field(..., alias="userId", description="User identifier from X-User-Id header")
    conversation_history: list[ConversationMessage] = Field(
        default_factory=list,
        alias="conversationHistory",
        description="Messages in the session (max 50)",
    )
    extracted_attributes: dict[str, Any] = Field(
        default_factory=dict,
        alias="extractedAttributes",
        description="Known attributes extracted from conversation",
    )
    confidence_score: float = Field(
        default=0.0,
        alias="confidenceScore",
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    question_count: int = Field(
        default=0,
        alias="questionCount",
        ge=0,
        le=5,
        description="Number of questions asked this session (max 5)",
    )
    created_at: str = Field(
        ...,
        alias="createdAt",
        description="ISO 8601 session creation timestamp",
    )
    updated_at: str = Field(
        ...,
        alias="updatedAt",
        description="ISO 8601 last update timestamp",
    )
    ttl: int = Field(
        ...,
        description="Unix epoch TTL (updatedAt + 30 minutes)",
    )

    model_config = {"populate_by_name": True}

    @field_validator("conversation_history")
    @classmethod
    def validate_history_length(cls, v: list[ConversationMessage]) -> list[ConversationMessage]:
        if len(v) > 50:
            raise ValueError("conversation history cannot exceed 50 messages")
        return v
