"""Unit tests for session store service (local/in-memory mode)."""

import os
import time
from unittest.mock import patch

import pytest


# Ensure local mode is active for tests
os.environ["USE_LOCAL_STORE"] = "true"

from backend.models.session import ConversationMessage, Session
from backend.services import session_store
from backend.services.session_store import (
    _calculate_ttl,
    _local_store,
    create_session,
    get_session,
    update_session,
)


@pytest.fixture(autouse=True)
def clear_local_store():
    """Clear in-memory store before each test."""
    _local_store.clear()
    yield
    _local_store.clear()


class TestCreateSession:
    """Tests for create_session function."""

    def test_creates_session_with_valid_id(self):
        session = create_session("test-session-1", "user-abc")
        assert session.session_id == "test-session-1"
        assert session.user_id == "user-abc"

    def test_creates_session_with_empty_conversation(self):
        session = create_session("test-session-2", "user-abc")
        assert session.conversation_history == []

    def test_creates_session_with_zero_confidence(self):
        session = create_session("test-session-3", "user-abc")
        assert session.confidence_score == 0.0

    def test_creates_session_with_zero_question_count(self):
        session = create_session("test-session-4", "user-abc")
        assert session.question_count == 0

    def test_creates_session_with_category(self):
        session = create_session("test-session-5", "user-abc", category="Fashion")
        assert session.extracted_attributes == {"category": "Fashion"}

    def test_creates_session_without_category(self):
        session = create_session("test-session-6", "user-abc", category=None)
        assert session.extracted_attributes == {}

    def test_creates_session_with_timestamps(self):
        session = create_session("test-session-7", "user-abc")
        assert session.created_at is not None
        assert session.updated_at is not None
        assert session.created_at == session.updated_at

    def test_creates_session_with_valid_ttl(self):
        session = create_session("test-session-8", "user-abc")
        # TTL should be updatedAt + 1800
        expected_ttl = _calculate_ttl(session.updated_at)
        assert session.ttl == expected_ttl

    def test_session_persisted_in_local_store(self):
        create_session("test-session-9", "user-abc")
        assert "test-session-9" in _local_store


class TestGetSession:
    """Tests for get_session function."""

    def test_returns_existing_session(self):
        create_session("get-test-1", "user-abc")
        session = get_session("get-test-1")
        assert session is not None
        assert session.session_id == "get-test-1"

    def test_returns_none_for_nonexistent_session(self):
        session = get_session("nonexistent")
        assert session is None

    def test_returns_none_for_expired_session(self):
        create_session("expired-1", "user-abc")
        # Manually set TTL to past
        _local_store["expired-1"]["ttl"] = int(time.time()) - 100
        session = get_session("expired-1")
        assert session is None

    def test_preserves_all_session_fields(self):
        created = create_session("roundtrip-1", "user-xyz", category="Electronics")
        retrieved = get_session("roundtrip-1")
        assert retrieved is not None
        assert retrieved.session_id == created.session_id
        assert retrieved.user_id == created.user_id
        assert retrieved.extracted_attributes == created.extracted_attributes
        assert retrieved.confidence_score == created.confidence_score
        assert retrieved.question_count == created.question_count
        assert retrieved.created_at == created.created_at
        assert retrieved.updated_at == created.updated_at
        assert retrieved.ttl == created.ttl


class TestUpdateSession:
    """Tests for update_session function."""

    def test_updates_updated_at_timestamp(self):
        session = create_session("update-1", "user-abc")
        original_updated_at = session.updated_at
        # Small delay to ensure different timestamp
        import time as t
        t.sleep(0.01)
        update_session(session)
        assert session.updated_at >= original_updated_at

    def test_recalculates_ttl(self):
        session = create_session("update-2", "user-abc")
        update_session(session)
        expected_ttl = _calculate_ttl(session.updated_at)
        assert session.ttl == expected_ttl

    def test_persists_modified_attributes(self):
        session = create_session("update-3", "user-abc")
        session.extracted_attributes = {"category": "Fashion", "brand": "Nike"}
        session.confidence_score = 0.6
        update_session(session)

        retrieved = get_session("update-3")
        assert retrieved is not None
        assert retrieved.extracted_attributes == {"category": "Fashion", "brand": "Nike"}
        assert retrieved.confidence_score == 0.6

    def test_persists_conversation_history(self):
        session = create_session("update-4", "user-abc")
        session.conversation_history = [
            ConversationMessage(role="user", text="Hello", timestamp="2024-01-01T00:00:00Z"),
            ConversationMessage(role="agent", text="Hi!", timestamp="2024-01-01T00:00:01Z"),
        ]
        update_session(session)

        retrieved = get_session("update-4")
        assert retrieved is not None
        assert len(retrieved.conversation_history) == 2
        assert retrieved.conversation_history[0].role == "user"
        assert retrieved.conversation_history[0].text == "Hello"
        assert retrieved.conversation_history[1].role == "agent"


class TestCalculateTtl:
    """Tests for _calculate_ttl helper."""

    def test_adds_1800_seconds(self):
        # 2024-01-15T10:00:00Z -> epoch + 1800
        ttl = _calculate_ttl("2024-01-15T10:00:00Z")
        from datetime import datetime, timezone
        dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        expected = int(dt.timestamp()) + 1800
        assert ttl == expected

    def test_handles_z_suffix(self):
        ttl = _calculate_ttl("2024-06-01T12:30:00Z")
        from datetime import datetime, timezone
        dt = datetime(2024, 6, 1, 12, 30, 0, tzinfo=timezone.utc)
        expected = int(dt.timestamp()) + 1800
        assert ttl == expected
