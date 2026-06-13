"""Unit tests for the IntentFlow Agent service."""

import json
import os
from unittest.mock import patch

import pytest

# Enable local mode for tests
os.environ["USE_LOCAL_BEDROCK"] = "true"
os.environ["USE_LOCAL_STORE"] = "true"

from backend.models.session import ConversationMessage, Session
from backend.services.intent_agent import (
    _NO_EXTRACT_COUNT_KEY,
    _build_question_response,
    _build_recommendation_response,
    _generate_recommendation_explanation,
    _handle_no_extract_tracking,
    _parse_bedrock_response,
    process_user_message,
)


def _make_session(**overrides) -> Session:
    """Create a test session with sensible defaults."""
    defaults = {
        "sessionId": "test-session-001",
        "userId": "test-user-001",
        "conversationHistory": [],
        "extractedAttributes": {},
        "confidenceScore": 0.0,
        "questionCount": 0,
        "createdAt": "2024-01-15T10:00:00Z",
        "updatedAt": "2024-01-15T10:00:00Z",
        "ttl": 1705314600,
    }
    defaults.update(overrides)
    return Session(**defaults)


class TestParsBedrockResponse:
    """Tests for _parse_bedrock_response."""

    def test_valid_json_response(self):
        raw = json.dumps({
            "extracted_attributes": {"category": "Fashion", "brand": "Nike"},
            "response_text": "Great choice! What size do you need?",
            "options": ["S", "M", "L", "XL"],
        })
        result = _parse_bedrock_response(raw)
        assert result["extracted_attributes"] == {"category": "Fashion", "brand": "Nike"}
        assert result["response_text"] == "Great choice! What size do you need?"
        assert result["options"] == ["S", "M", "L", "XL"]

    def test_json_with_null_options(self):
        raw = json.dumps({
            "extracted_attributes": {"category": "Electronics"},
            "response_text": "What type of electronics?",
            "options": None,
        })
        result = _parse_bedrock_response(raw)
        assert result["options"] is None

    def test_json_in_code_fence(self):
        raw = '```json\n{"extracted_attributes": {"color": "red"}, "response_text": "Red it is!", "options": null}\n```'
        result = _parse_bedrock_response(raw)
        assert result["extracted_attributes"] == {"color": "red"}
        assert result["response_text"] == "Red it is!"

    def test_json_embedded_in_text(self):
        raw = 'Here is my response: {"extracted_attributes": {}, "response_text": "Hello!", "options": null}'
        result = _parse_bedrock_response(raw)
        assert result["response_text"] == "Hello!"

    def test_non_json_response_fallback(self):
        raw = "I'd love to help you find running shoes!"
        result = _parse_bedrock_response(raw)
        assert result["extracted_attributes"] == {}
        assert "running shoes" in result["response_text"]
        assert result["options"] is None

    def test_empty_extracted_attributes(self):
        raw = json.dumps({
            "extracted_attributes": {},
            "response_text": "Could you tell me more?",
            "options": None,
        })
        result = _parse_bedrock_response(raw)
        assert result["extracted_attributes"] == {}


class TestHandleNoExtractTracking:
    """Tests for consecutive no-extraction tracking."""

    def test_first_no_extract_increments_counter(self):
        session = _make_session()
        attrs, show = _handle_no_extract_tracking(session, {})
        assert show is False
        assert session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] == 1

    def test_second_no_extract_increments_counter(self):
        session = _make_session(extractedAttributes={_NO_EXTRACT_COUNT_KEY: 1})
        attrs, show = _handle_no_extract_tracking(session, {})
        assert show is False
        assert session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] == 2

    def test_third_no_extract_triggers_category_fallback(self):
        session = _make_session(extractedAttributes={_NO_EXTRACT_COUNT_KEY: 2})
        attrs, show = _handle_no_extract_tracking(session, {})
        assert show is True
        # Counter should be reset
        assert session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] == 0

    def test_successful_extraction_resets_counter(self):
        session = _make_session(extractedAttributes={_NO_EXTRACT_COUNT_KEY: 2})
        attrs, show = _handle_no_extract_tracking(
            session, {"category": "Fashion"}
        )
        assert show is False
        assert session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] == 0

    def test_empty_value_not_counted_as_extraction(self):
        session = _make_session()
        attrs, show = _handle_no_extract_tracking(session, {"brand": ""})
        assert show is False
        assert session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] == 1

    def test_none_value_not_counted_as_extraction(self):
        session = _make_session()
        attrs, show = _handle_no_extract_tracking(session, {"size": None})
        assert show is False
        assert session.extracted_attributes[_NO_EXTRACT_COUNT_KEY] == 1


class TestBuildRecommendationResponse:
    """Tests for recommendation response building."""

    def test_returns_recommendations_type(self):
        session = _make_session(extractedAttributes={"category": "Fashion"})
        session.confidence_score = 0.85
        result = _build_recommendation_response(session, "Here are some options!")
        assert result["type"] == "recommendations"

    def test_limits_to_5_products(self):
        session = _make_session(extractedAttributes={"category": "Fashion"})
        session.confidence_score = 0.85
        result = _build_recommendation_response(session, "Top picks!")
        assert len(result.get("products", [])) <= 5

    def test_products_sorted_by_rating_descending(self):
        session = _make_session(extractedAttributes={"category": "Fashion"})
        session.confidence_score = 0.85
        result = _build_recommendation_response(session, "Here you go!")
        products = result.get("products", [])
        if len(products) >= 2:
            ratings = [p["rating"] for p in products]
            assert ratings == sorted(ratings, reverse=True)

    def test_no_matching_products_returns_broadening_message(self):
        session = _make_session(
            extractedAttributes={"category": "Fashion", "brand": "NonExistentBrand123"}
        )
        session.confidence_score = 0.85
        result = _build_recommendation_response(session, "")
        assert result["type"] == "recommendations"
        assert "broaden" in result["text"].lower() or "couldn't find" in result["text"].lower()
        assert result["products"] == []

    def test_includes_metadata(self):
        session = _make_session(extractedAttributes={"category": "Fashion"})
        session.confidence_score = 0.85
        session.question_count = 3
        result = _build_recommendation_response(session, "Picks!")
        assert "metadata" in result
        assert result["metadata"]["confidenceScore"] == 0.85
        assert result["metadata"]["questionCount"] == 3

    def test_internal_key_excluded_from_metadata(self):
        session = _make_session(
            extractedAttributes={"category": "Fashion", _NO_EXTRACT_COUNT_KEY: 1}
        )
        session.confidence_score = 0.5
        result = _build_recommendation_response(session, "Here!")
        assert _NO_EXTRACT_COUNT_KEY not in result["metadata"]["extractedAttributes"]


class TestBuildQuestionResponse:
    """Tests for question response building."""

    def test_returns_question_type(self):
        session = _make_session()
        result = _build_question_response(session, "What category?", None)
        assert result["type"] == "question"

    def test_includes_response_text(self):
        session = _make_session()
        result = _build_question_response(session, "What brand?", None)
        assert result["text"] == "What brand?"

    def test_includes_options(self):
        session = _make_session()
        options = ["Nike", "Adidas", "Puma"]
        result = _build_question_response(session, "Which brand?", options)
        assert result["options"] == ["Nike", "Adidas", "Puma"]

    def test_truncates_options_to_5(self):
        session = _make_session()
        options = ["A", "B", "C", "D", "E", "F", "G"]
        result = _build_question_response(session, "Pick one", options)
        assert len(result["options"]) == 5

    def test_excludes_internal_key_from_metadata(self):
        session = _make_session(
            extractedAttributes={"category": "Tools", _NO_EXTRACT_COUNT_KEY: 2}
        )
        result = _build_question_response(session, "What type?", None)
        assert _NO_EXTRACT_COUNT_KEY not in result["metadata"]["extractedAttributes"]


class TestGenerateRecommendationExplanation:
    """Tests for recommendation explanation generation."""

    def test_includes_category(self):
        result = _generate_recommendation_explanation({"category": "Fashion"})
        assert "Fashion" in result

    def test_includes_brand(self):
        result = _generate_recommendation_explanation(
            {"category": "Fashion", "brand": "Nike"}
        )
        assert "Nike" in result

    def test_empty_attributes_returns_generic(self):
        result = _generate_recommendation_explanation({})
        assert "recommendations" in result.lower() or "picks" in result.lower()


class TestProcessUserMessage:
    """Integration tests for the full process_user_message flow."""

    def test_returns_valid_response_dict(self):
        session = _make_session()
        result = process_user_message(session, "I need running shoes")
        assert "type" in result
        assert result["type"] in ("question", "recommendations")
        assert "text" in result
        assert "metadata" in result

    def test_appends_messages_to_history(self):
        session = _make_session()
        process_user_message(session, "I want shoes")
        # Should have at least user + agent messages
        assert len(session.conversation_history) >= 2
        roles = [msg.role for msg in session.conversation_history]
        assert "user" in roles
        assert "agent" in roles

    def test_metadata_contains_required_fields(self):
        session = _make_session()
        result = process_user_message(session, "Looking for electronics")
        meta = result["metadata"]
        assert "confidenceScore" in meta
        assert "extractedAttributes" in meta
        assert "questionCount" in meta

    def test_bedrock_failure_raises_agent_processing_error(self):
        from backend.services.bedrock_client import AgentProcessingError

        session = _make_session()
        with patch(
            "backend.services.intent_agent.invoke_bedrock",
            side_effect=AgentProcessingError("Service unavailable"),
        ):
            with pytest.raises(AgentProcessingError):
                process_user_message(session, "hello")
