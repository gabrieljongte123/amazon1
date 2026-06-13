"""Message request/response data models for IntentFlow."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from models.product import ProductSummary


class MessageRequest(BaseModel):
    """Request body for POST /sessions/{sessionId}/messages."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="User message text (1-500 characters)",
    )

    @field_validator("text")
    @classmethod
    def validate_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message text cannot be empty or whitespace-only")
        return v


class ResponseContent(BaseModel):
    """Agent response content (question or recommendations)."""

    type: str = Field(..., description="Response type: 'question' or 'recommendations'")
    text: str = Field(..., description="Agent response text")
    options: list[str] | None = Field(
        default=None,
        description="Quick reply options (max 5 items, each max 10 words)",
    )
    products: list[ProductSummary] | None = Field(
        default=None,
        description="Product recommendations (max 5)",
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("question", "recommendations"):
            raise ValueError("type must be 'question' or 'recommendations'")
        return v

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) > 5:
            raise ValueError("options cannot exceed 5 items")
        return v


class ResponseMetadata(BaseModel):
    """Metadata about the agent response."""

    confidence_score: float = Field(
        ...,
        alias="confidenceScore",
        ge=0.0,
        le=1.0,
        description="Current confidence score",
    )
    extracted_attributes: dict[str, Any] = Field(
        ...,
        alias="extractedAttributes",
        description="Currently known attributes",
    )
    question_count: int = Field(
        ...,
        alias="questionCount",
        ge=0,
        description="Number of questions asked so far",
    )

    model_config = {"populate_by_name": True}


class MessageResponse(BaseModel):
    """Response body for POST /sessions/{sessionId}/messages."""

    session_id: str = Field(..., alias="sessionId", description="Session identifier")
    response: ResponseContent = Field(..., description="Agent response content")
    metadata: ResponseMetadata = Field(..., description="Response metadata")

    model_config = {"populate_by_name": True}
