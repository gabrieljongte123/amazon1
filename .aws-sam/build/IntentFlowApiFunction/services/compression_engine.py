"""Intent Compression Engine for IntentFlow.

Handles confidence scoring, information gain calculation,
question selection, attribute merging, and message processing orchestration.
"""

import json
from math import log2
from pathlib import Path
from typing import Any

from config import settings
from models.session import Session
from services.product_catalog import (
    count_matching_products,
    get_category_schema,
    query_products,
)

# Module-level cache: load categories schema once on cold start
_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "products.json"
_categories: dict[str, dict[str, Any]] = {}


def _load_categories() -> None:
    """Load category schemas from the product catalog JSON."""
    global _categories
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    _categories = data.get("categories", {})


# Load on import (cold start)
_load_categories()


def calculate_confidence(session: Session) -> float:
    """Calculate the confidence score for a session.

    Uses a weighted formula based on known vs required/optional attributes
    for the identified category. Required attributes get 2x weight because
    they are more important for narrowing down products.

    Formula: (|known ∩ required| × 2 + |known ∩ optional|) / (|required| × 2 + |optional|)

    Without a known category, uses a rough estimate: len(known_attributes) / 10.0

    Both cases are clamped to [0.0, 1.0].

    Args:
        session: The current session with extracted_attributes.

    Returns:
        A float between 0.0 and 1.0 representing confidence.
    """
    category = session.extracted_attributes.get("category")

    if category is None:
        return min(len(session.extracted_attributes) / 10.0, 1.0)

    category_schema = get_category_schema(category)
    if category_schema is None:
        # Unknown category — fall back to rough estimate
        return min(len(session.extracted_attributes) / 10.0, 1.0)

    required = set(category_schema["requiredAttributes"])
    optional = set(category_schema["optionalAttributes"])
    all_attributes = required | optional

    known = set(session.extracted_attributes.keys()) & all_attributes
    required_known = known & required
    optional_known = known & optional

    weighted_known = (len(required_known) * 2) + len(optional_known)
    weighted_total = (len(required) * 2) + len(optional)

    if weighted_total == 0:
        return 1.0

    return min(weighted_known / weighted_total, 1.0)


def should_recommend(session: Session, confidence: float) -> bool:
    """Decide whether to trigger product recommendations.

    Returns True if any of the following conditions are met:
    - question_count >= MAX_QUESTIONS (default 5) — hard limit
    - confidence >= CONFIDENCE_THRESHOLD (default 0.8)
    - matching products > 0 and < 4 — no point asking more questions

    Args:
        session: The current session state.
        confidence: The current confidence score.

    Returns:
        True if recommendations should be triggered, False otherwise.
    """
    # Hard limit: max questions reached
    if session.question_count >= settings.MAX_QUESTIONS:
        return True

    # Confidence threshold reached
    if confidence >= settings.CONFIDENCE_THRESHOLD:
        return True

    # Few products match — no point asking more questions
    # Filter out internal tracking keys (prefixed with _)
    query_attrs = {k: v for k, v in session.extracted_attributes.items() if not k.startswith("_")}
    matching_count = count_matching_products(query_attrs)
    if matching_count > 0 and matching_count < 4:
        return True

    return False


def calculate_information_gain(candidates: list, attribute: str) -> float:
    """Calculate information gain for an attribute using entropy.

    Higher gain means the attribute values are more evenly distributed
    among candidates, so any answer eliminates roughly half the options.

    Args:
        candidates: List of Product objects to evaluate against.
        attribute: The attribute name to calculate gain for.

    Returns:
        Entropy value (float >= 0.0). Higher means more information gain.
    """
    if not candidates:
        return 0.0

    # Count products per attribute value
    value_counts: dict[str, int] = {}
    for product in candidates:
        # Check top-level attributes first (category, brand, color, size)
        value = getattr(product, attribute, None)
        # Fall back to nested attributes dict
        if value is None:
            value = product.attributes.get(attribute, "unknown")
        value_counts[str(value)] = value_counts.get(str(value), 0) + 1

    total = len(candidates)
    if total == 0:
        return 0.0

    # Calculate entropy (higher entropy = more information gain from asking)
    entropy = 0.0
    for count in value_counts.values():
        if count > 0:
            p = count / total
            entropy -= p * log2(p)

    return entropy


def select_next_question(session: Session) -> str | None:
    """Select the attribute that maximizes information gain.

    Priority logic:
    1. If no category is known, return "category" (highest discriminative power).
    2. Otherwise, get unknown attributes ordered by discriminativeOrder from
       the category schema, calculate info gain for each, return the best.
    3. Return None if no unknown attributes remain.

    Args:
        session: The current session state.

    Returns:
        The attribute name to ask about, or None if all attributes are known.
    """
    category = session.extracted_attributes.get("category")

    # Priority 1: If no category, ask for category first
    if category is None:
        return "category"

    # Get category schema
    category_schema = get_category_schema(category)
    if category_schema is None:
        return None

    # Get candidate products matching known attributes
    candidates = query_products(session.extracted_attributes)

    # Get unknown attributes, ordered by discriminative power
    discriminative_order = category_schema.get("discriminativeOrder", [])
    known_keys = set(session.extracted_attributes.keys())

    unknown_attributes = [a for a in discriminative_order if a not in known_keys]

    if not unknown_attributes:
        return None  # All attributes known — trigger recommendations

    # Select attribute with highest information gain
    best_attribute = None
    best_gain = -1.0

    for attr in unknown_attributes:
        gain = calculate_information_gain(candidates, attr)
        if gain > best_gain:
            best_gain = gain
            best_attribute = attr

    return best_attribute


def merge_attributes(existing: dict, new: dict) -> dict:
    """Merge new extracted attributes into the existing attribute map.

    Semantics:
    - Keys in `new` override corresponding keys in `existing`.
    - Keys in `existing` that are NOT in `new` retain their original values.
    - Does not mutate either input dict.

    Args:
        existing: The current known attributes for the session.
        new: Newly extracted attributes from the latest user message.

    Returns:
        A new dict containing the merged attributes.
    """
    return {**existing, **new}


def process_message(session: Session, new_attributes: dict) -> dict:
    """Process a message by merging attributes and deciding next action.

    Orchestrates the full compression engine flow:
    1. Merge new attributes into session
    2. Calculate confidence score
    3. Decide whether to recommend or ask another question

    Args:
        session: The current session state (will be mutated with new attributes
                 and updated confidence score).
        new_attributes: Newly extracted attributes from the latest message.

    Returns:
        A dict with:
        - {"type": "recommendations"} if should_recommend is True
        - {"type": "question", "attribute": <next_attr>} if more info needed
    """
    # 1. Merge new attributes into session
    session.extracted_attributes = merge_attributes(
        session.extracted_attributes, new_attributes
    )

    # 2. Calculate confidence score
    confidence = calculate_confidence(session)
    session.confidence_score = confidence

    # 3. Determine action
    if should_recommend(session, confidence):
        return {"type": "recommendations"}
    else:
        next_attr = select_next_question(session)
        if next_attr is None:
            # No more attributes to ask about — recommend
            return {"type": "recommendations"}
        return {"type": "question", "attribute": next_attr}
