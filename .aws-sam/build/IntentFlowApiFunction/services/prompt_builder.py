"""Prompt construction for Amazon Bedrock (Claude) integration.

Builds the system and user prompts that constrain the model to the shopping
domain and instruct it to extract attributes from user messages.
"""

import json

# Maximum number of conversation history messages to include in the prompt
MAX_HISTORY_MESSAGES = 20

SYSTEM_PROMPT = """You are an AI shopping assistant for Amazon Now. Your ONLY job is to help customers find and purchase products. Do NOT engage in off-topic conversations.

RESPONSE CONSTRAINTS:
- Questions must be at most 2 sentences.
- When presenting options, format them as a numbered list with at most 5 items, each no longer than 10 words.
- Non-question responses (acknowledgments, explanations, transitions) must be at most 3 sentences.
- Use first-person language, contractions, and plain vocabulary. No technical jargon.

OUTPUT FORMAT:
You MUST return a valid JSON object with the following fields:
- "extracted_attributes": A dictionary of product attributes extracted from the user's latest message. Keys may include: category, subcategory, brand, priceRange, size, color, type, gender, dietary, powerSource, connectivity. Only include attributes clearly stated or implied by the user. Use an empty dict if none found.
- "response_text": Your conversational response to the user (string). Follow the response constraints above.
- "options": An optional list of strings representing choices for the user. Each option must be at most 10 words. Maximum 5 options. Omit this field or set to null if no options are needed.

OFF-TOPIC HANDLING:
If the user's message is not related to shopping, product discovery, or purchasing, respond with:
{"extracted_attributes": {}, "response_text": "I'm here to help you shop! What product are you looking for today?", "options": null}

Do NOT answer questions about weather, news, politics, coding, math, personal advice, or any non-shopping topic."""


def build_prompt(
    conversation_history: list, extracted_attributes: dict, user_message: str
) -> tuple[str, str]:
    """Construct the system and user prompts for Bedrock invocation.

    Args:
        conversation_history: List of message dicts with 'role' and 'text' keys.
        extracted_attributes: Currently known product attributes for the session.
        user_message: The new message from the user.

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    # Take the last 20 messages from conversation history (or all if fewer)
    recent_history = conversation_history[-MAX_HISTORY_MESSAGES:]

    # Format conversation history for the prompt
    history_text = _format_conversation_history(recent_history)

    # Format extracted attributes as JSON
    attributes_text = json.dumps(extracted_attributes, indent=2)

    # Build the user prompt
    user_prompt_parts = []

    if recent_history:
        user_prompt_parts.append("CONVERSATION HISTORY:")
        user_prompt_parts.append(history_text)
        user_prompt_parts.append("")

    user_prompt_parts.append("CURRENTLY KNOWN ATTRIBUTES:")
    user_prompt_parts.append(attributes_text)
    user_prompt_parts.append("")

    user_prompt_parts.append("NEW USER MESSAGE:")
    user_prompt_parts.append(user_message)
    user_prompt_parts.append("")

    user_prompt_parts.append("INSTRUCTIONS:")
    user_prompt_parts.append(
        "1. Identify any NEW product attributes from the user's latest message."
    )
    user_prompt_parts.append(
        "2. Generate an appropriate conversational response following the response constraints."
    )
    user_prompt_parts.append(
        "3. Return your response as a JSON object with extracted_attributes, response_text, and options fields."
    )

    user_prompt = "\n".join(user_prompt_parts)

    return SYSTEM_PROMPT, user_prompt


def _format_conversation_history(messages: list) -> str:
    """Format conversation messages into a readable text block.

    Args:
        messages: List of message dicts with 'role' and 'text' keys.

    Returns:
        Formatted string with each message on its own line.
    """
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        text = msg.get("text", "")
        lines.append(f"[{role}]: {text}")
    return "\n".join(lines)
