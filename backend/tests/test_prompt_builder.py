"""Unit tests for prompt_builder module."""

import json

from backend.services.prompt_builder import (
    MAX_HISTORY_MESSAGES,
    SYSTEM_PROMPT,
    build_prompt,
    _format_conversation_history,
)


class TestBuildPrompt:
    """Tests for the build_prompt function."""

    def test_returns_tuple_of_two_strings(self):
        """build_prompt should return a tuple of (system_prompt, user_prompt)."""
        system, user = build_prompt([], {}, "I need shoes")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_prompt_constrains_to_shopping_domain(self):
        """System prompt should instruct the model to only discuss shopping."""
        system, _ = build_prompt([], {}, "hello")
        assert "shopping assistant" in system.lower()
        assert "Do NOT engage in off-topic conversations" in system

    def test_system_prompt_includes_formatting_constraints(self):
        """System prompt should include response formatting rules."""
        system, _ = build_prompt([], {}, "hello")
        assert "2 sentences" in system
        assert "5 items" in system
        assert "10 words" in system

    def test_system_prompt_includes_json_output_format(self):
        """System prompt should instruct model to return JSON with specific fields."""
        system, _ = build_prompt([], {}, "hello")
        assert "extracted_attributes" in system
        assert "response_text" in system
        assert "options" in system

    def test_system_prompt_includes_off_topic_redirect(self):
        """System prompt should instruct model to redirect off-topic messages."""
        system, _ = build_prompt([], {}, "hello")
        assert "I'm here to help you shop!" in system

    def test_user_prompt_includes_user_message(self):
        """User prompt should contain the new user message."""
        _, user = build_prompt([], {}, "I need running shoes")
        assert "I need running shoes" in user

    def test_user_prompt_includes_extracted_attributes(self):
        """User prompt should include all currently known attributes."""
        attrs = {"category": "Fashion", "brand": "Nike"}
        _, user = build_prompt([], attrs, "hello")
        assert '"category": "Fashion"' in user
        assert '"brand": "Nike"' in user

    def test_user_prompt_includes_conversation_history(self):
        """User prompt should include conversation history messages."""
        history = [
            {"role": "user", "text": "I need shoes"},
            {"role": "agent", "text": "What brand do you prefer?"},
        ]
        _, user = build_prompt(history, {}, "Nike")
        assert "[USER]: I need shoes" in user
        assert "[AGENT]: What brand do you prefer?" in user

    def test_user_prompt_limits_history_to_20_messages(self):
        """User prompt should include at most the last 20 messages."""
        history = [
            {"role": "user", "text": f"Message {i}"} for i in range(30)
        ]
        _, user = build_prompt(history, {}, "latest")
        # Messages 0-9 should NOT be included (only last 20: messages 10-29)
        assert "Message 0" not in user
        assert "Message 9" not in user
        # Messages 10-29 should be included
        assert "Message 10" in user
        assert "Message 29" in user

    def test_user_prompt_includes_all_history_when_fewer_than_20(self):
        """User prompt should include all messages when history is short."""
        history = [
            {"role": "user", "text": f"Message {i}"} for i in range(5)
        ]
        _, user = build_prompt(history, {}, "latest")
        for i in range(5):
            assert f"Message {i}" in user

    def test_user_prompt_with_empty_history(self):
        """User prompt should work fine with no conversation history."""
        _, user = build_prompt([], {"category": "Fashion"}, "I need shoes")
        assert "I need shoes" in user
        assert "CONVERSATION HISTORY" not in user

    def test_user_prompt_includes_instructions(self):
        """User prompt should include instructions for attribute extraction."""
        _, user = build_prompt([], {}, "hello")
        assert "NEW product attributes" in user or "new product attributes" in user.lower()
        assert "JSON" in user

    def test_empty_attributes_shown_as_empty_dict(self):
        """Empty extracted attributes should serialize as {}."""
        _, user = build_prompt([], {}, "hello")
        assert "{}" in user


class TestFormatConversationHistory:
    """Tests for the _format_conversation_history helper."""

    def test_empty_list(self):
        """Should return empty string for no messages."""
        result = _format_conversation_history([])
        assert result == ""

    def test_single_message(self):
        """Should format a single message correctly."""
        messages = [{"role": "user", "text": "hello"}]
        result = _format_conversation_history(messages)
        assert result == "[USER]: hello"

    def test_multiple_messages(self):
        """Should format multiple messages with newlines."""
        messages = [
            {"role": "user", "text": "I need shoes"},
            {"role": "agent", "text": "What size?"},
        ]
        result = _format_conversation_history(messages)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "[USER]: I need shoes"
        assert lines[1] == "[AGENT]: What size?"

    def test_missing_role_defaults_to_unknown(self):
        """Should handle messages with missing role."""
        messages = [{"text": "orphan message"}]
        result = _format_conversation_history(messages)
        assert "[UNKNOWN]: orphan message" in result

    def test_missing_text_defaults_to_empty(self):
        """Should handle messages with missing text."""
        messages = [{"role": "user"}]
        result = _format_conversation_history(messages)
        assert "[USER]: " in result


class TestMaxHistoryConstant:
    """Ensure the constant is correct."""

    def test_max_history_is_20(self):
        assert MAX_HISTORY_MESSAGES == 20
