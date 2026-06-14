"""Unit tests for the compression engine."""

from datetime import datetime, timezone

from backend.models.session import Session
from backend.services.compression_engine import calculate_confidence, merge_attributes


def _make_session(extracted_attributes: dict) -> Session:
    """Helper to create a Session with given extracted attributes."""
    now = datetime.now(timezone.utc).isoformat()
    return Session(
        sessionId="test-session-id",
        userId="test-user",
        extractedAttributes=extracted_attributes,
        confidenceScore=0.0,
        questionCount=0,
        createdAt=now,
        updatedAt=now,
        ttl=int(datetime.now(timezone.utc).timestamp()) + 1800,
    )


# --- calculate_confidence tests ---


def test_confidence_no_category_empty_attributes():
    session = _make_session({})
    assert calculate_confidence(session) == 0.0


def test_confidence_no_category_some_attributes():
    session = _make_session({"brand": "Nike", "color": "Red", "size": "9"})
    assert calculate_confidence(session) == 0.3  # 3 / 10.0


def test_confidence_no_category_clamped_to_one():
    # 11 attributes without category should clamp to 1.0
    attrs = {f"attr{i}": f"val{i}" for i in range(11)}
    session = _make_session(attrs)
    assert calculate_confidence(session) == 1.0


def test_confidence_fashion_category_only():
    # Fashion: required=["category", "subcategory"], optional=["brand","size","color","priceRange","gender"]
    # weighted_total = 2*2 + 5 = 9
    # known & required = {"category"} -> 1, known & optional = {} -> 0
    # weighted_known = 1*2 + 0 = 2
    # confidence = 2/9
    session = _make_session({"category": "Fashion"})
    result = calculate_confidence(session)
    assert abs(result - 2 / 9) < 1e-9


def test_confidence_fashion_all_required():
    # known & required = {"category", "subcategory"} -> 2
    # weighted_known = 2*2 + 0 = 4, weighted_total = 9
    session = _make_session({"category": "Fashion", "subcategory": "shoes"})
    result = calculate_confidence(session)
    assert abs(result - 4 / 9) < 1e-9


def test_confidence_fashion_all_attributes():
    # All required + optional known
    # required_known = 2, optional_known = 5
    # weighted_known = 2*2 + 5 = 9, weighted_total = 9
    session = _make_session({
        "category": "Fashion",
        "subcategory": "shoes",
        "brand": "Nike",
        "size": "9",
        "color": "Black",
        "priceRange": "2000-3000",
        "gender": "unisex",
    })
    result = calculate_confidence(session)
    assert result == 1.0


def test_confidence_grocery_category():
    # Grocery: required=["category"], optional=["brand","priceRange","dietary"]
    # weighted_total = 1*2 + 3 = 5
    # known & required = {"category"} -> 1, known & optional = {"brand"} -> 1
    # weighted_known = 1*2 + 1 = 3
    session = _make_session({"category": "Grocery", "brand": "Amul"})
    result = calculate_confidence(session)
    assert abs(result - 3 / 5) < 1e-9


def test_confidence_ignores_unknown_attributes():
    # Extra attributes not in schema should not count
    session = _make_session({
        "category": "Grocery",
        "brand": "Amul",
        "unknownAttr": "something",
    })
    result = calculate_confidence(session)
    # Same as if unknownAttr wasn't there: 3/5
    assert abs(result - 3 / 5) < 1e-9


def test_confidence_unknown_category_value_fallback():
    # Category set but not in catalog schema -> fallback to rough estimate
    session = _make_session({"category": "NonExistentCategory", "brand": "X"})
    result = calculate_confidence(session)
    assert abs(result - 2 / 10.0) < 1e-9


def test_confidence_always_between_zero_and_one():
    # Verify clamping for various inputs
    session_empty = _make_session({})
    assert 0.0 <= calculate_confidence(session_empty) <= 1.0

    session_full = _make_session({
        "category": "Electronics",
        "type": "headphones",
        "brand": "Sony",
        "priceRange": "20000-30000",
        "size": "large",
        "connectivity": "bluetooth",
    })
    assert 0.0 <= calculate_confidence(session_full) <= 1.0


def test_merge_new_keys_override_existing():
    existing = {"category": "Fashion", "brand": "Nike", "size": "9"}
    new = {"brand": "Adidas", "color": "Blue"}
    result = merge_attributes(existing, new)
    assert result == {"category": "Fashion", "brand": "Adidas", "size": "9", "color": "Blue"}


def test_merge_preserves_existing_keys_not_in_new():
    existing = {"category": "Electronics", "brand": "Sony", "type": "headphones"}
    new = {"color": "Black"}
    result = merge_attributes(existing, new)
    assert result["category"] == "Electronics"
    assert result["brand"] == "Sony"
    assert result["type"] == "headphones"
    assert result["color"] == "Black"


def test_merge_does_not_mutate_inputs():
    existing = {"category": "Grocery", "brand": "Amul"}
    new = {"brand": "Mother Dairy", "dietary": "vegetarian"}
    existing_copy = existing.copy()
    new_copy = new.copy()

    merge_attributes(existing, new)

    assert existing == existing_copy
    assert new == new_copy


def test_merge_with_empty_existing():
    existing = {}
    new = {"category": "Tools", "brand": "Bosch"}
    result = merge_attributes(existing, new)
    assert result == {"category": "Tools", "brand": "Bosch"}


def test_merge_with_empty_new():
    existing = {"category": "Fashion", "brand": "Nike"}
    new = {}
    result = merge_attributes(existing, new)
    assert result == {"category": "Fashion", "brand": "Nike"}


def test_merge_both_empty():
    result = merge_attributes({}, {})
    assert result == {}
