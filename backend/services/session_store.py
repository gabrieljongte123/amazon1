"""DynamoDB session store for IntentFlow.

Provides CRUD operations for session persistence. Supports a local in-memory
mode (USE_LOCAL_STORE=true) for development without AWS credentials.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from config import settings
from models.session import ConversationMessage, Session

# Local mode flag: use in-memory dict instead of real DynamoDB
LOCAL_MODE = os.getenv("USE_LOCAL_STORE", "false").lower() == "true"

# In-memory store for local development
_local_store: dict[str, dict[str, Any]] = {}


def _get_dynamodb_table():
    """Get DynamoDB table resource with configured timeout."""
    boto_config = BotoConfig(
        read_timeout=settings.DYNAMODB_TIMEOUT_SECONDS,
        connect_timeout=settings.DYNAMODB_TIMEOUT_SECONDS,
        retries={"max_attempts": 0},
    )
    kwargs: dict[str, Any] = {
        "region_name": settings.DYNAMODB_REGION,
        "config": boto_config,
    }
    # Support DynamoDB Local for local development
    if settings.DYNAMODB_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.DYNAMODB_ENDPOINT_URL

    dynamodb = boto3.resource("dynamodb", **kwargs)
    return dynamodb.Table(settings.DYNAMODB_TABLE_NAME)


def _calculate_ttl(updated_at_iso: str) -> int:
    """Calculate TTL as updatedAt epoch + 1800 seconds."""
    dt = datetime.fromisoformat(updated_at_iso.replace("Z", "+00:00"))
    return int(dt.timestamp()) + 1800


def _session_to_item(session: Session) -> dict[str, Any]:
    """Convert a Session model to a DynamoDB item dict."""
    return {
        "sessionId": session.session_id,
        "userId": session.user_id,
        "conversationHistory": [
            {"role": msg.role, "text": msg.text, "timestamp": msg.timestamp}
            for msg in session.conversation_history
        ],
        "extractedAttributes": session.extracted_attributes,
        "confidenceScore": str(session.confidence_score),
        "questionCount": session.question_count,
        "createdAt": session.created_at,
        "updatedAt": session.updated_at,
        "ttl": session.ttl,
    }


def _item_to_session(item: dict[str, Any]) -> Session:
    """Convert a DynamoDB item dict to a Session model."""
    return Session(
        sessionId=item["sessionId"],
        userId=item["userId"],
        conversationHistory=[
            ConversationMessage(
                role=msg["role"],
                text=msg["text"],
                timestamp=msg["timestamp"],
            )
            for msg in item.get("conversationHistory", [])
        ],
        extractedAttributes=item.get("extractedAttributes", {}),
        confidenceScore=float(item.get("confidenceScore", 0.0)),
        questionCount=int(item.get("questionCount", 0)),
        createdAt=item["createdAt"],
        updatedAt=item["updatedAt"],
        ttl=int(item["ttl"]),
    )


def create_session(
    session_id: str, user_id: str, category: str | None = None
) -> Session:
    """Create a new session and persist it.

    Args:
        session_id: UUID v4 session identifier.
        user_id: User identifier from X-User-Id header.
        category: Optional pre-selected category from homepage.

    Returns:
        The newly created Session.

    Raises:
        ClientError: If DynamoDB write fails (propagated without modifying state).
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    ttl = _calculate_ttl(now)

    extracted_attributes: dict[str, Any] = {}
    if category:
        extracted_attributes["category"] = category

    session = Session(
        sessionId=session_id,
        userId=user_id,
        conversationHistory=[],
        extractedAttributes=extracted_attributes,
        confidenceScore=0.0,
        questionCount=0,
        createdAt=now,
        updatedAt=now,
        ttl=ttl,
    )

    item = _session_to_item(session)

    if LOCAL_MODE:
        _local_store[session_id] = item
    else:
        table = _get_dynamodb_table()
        table.put_item(Item=item)

    return session


def get_session(session_id: str) -> Session | None:
    """Retrieve a session by ID.

    Returns None if the session is not found or has expired (TTL passed).

    Args:
        session_id: The session ID to look up.

    Returns:
        The Session if found and not expired, None otherwise.

    Raises:
        ClientError: If DynamoDB read fails (propagated without modifying state).
    """
    if LOCAL_MODE:
        item = _local_store.get(session_id)
        if item is None:
            return None
        # Check TTL expiration for local mode
        if item.get("ttl", 0) < int(time.time()):
            del _local_store[session_id]
            return None
        return _item_to_session(item)

    table = _get_dynamodb_table()
    try:
        response = table.get_item(Key={"sessionId": session_id})
    except ClientError:
        raise

    item = response.get("Item")
    if item is None:
        return None

    # Check if TTL has expired (DynamoDB TTL deletion is eventual)
    if int(item.get("ttl", 0)) < int(time.time()):
        return None

    return _item_to_session(item)


def update_session(session: Session) -> None:
    """Update an existing session in the store.

    Sets updatedAt to current time and recalculates TTL.

    Args:
        session: The session with updated state to persist.

    Raises:
        ClientError: If DynamoDB update fails (propagated without modifying state).
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    ttl = _calculate_ttl(now)

    # Update timestamps on the session object
    session.updated_at = now
    session.ttl = ttl

    item = _session_to_item(session)

    if LOCAL_MODE:
        _local_store[session.session_id] = item
    else:
        table = _get_dynamodb_table()
        table.put_item(Item=item)
