"""Tests for the recommendation retrieval and formatting service."""

from datetime import datetime, timezone

from backend.models.session import Session
from backend.services.recommendations import (
    _build_attributes_summary,
    get_recommendations,
)


def _make_session(attributes: dict | None = None) -> Session:
    """Helper to create a test session with given attributes."""
    now = datetime.now(timezone.utc).isoformat()
    return Session(
        sessionId="test-session-001",
        userId="user-001",
        conversationHistory=[],
        extractedAttributes=attributes or {},
        confidenceScore=0.8,
        questionCount=3,
        createdAt=now,
        updatedAt=now,
        ttl=int(datetime.now(timezone.utc).timestamp()) + 1800,
    )


class TestBuildAttributesSummary:
    """Tests for _build_attributes_summary helper."""

    def test_empty_attributes(self):
        result = _build_attributes_summary({})
        assert result == "your preferences"

    def test_brand_only(self):
        result = _build_attributes_summary({"brand": "Nike"})
        assert "Nike" in result

    def test_brand_and_subcategory(self):
        result = _build_attributes_summary({"brand": "Nike", "subcategory": "shoes"})
        assert "Nike" in result
        assert "shoes" in result

    def test_full_attributes(self):
        result = _build_attributes_summary({
            "brand": "Nike",
            "subcategory": "shoes",
            "type": "running",
            "priceRange": "0-3000",
        })
        assert "Nike" in result
        assert "running" in result
        assert "shoes" in result
        assert "₹3000" in result

    def test_price_range_with_min(self):
        result = _build_attributes_summary({"priceRange": "2000-5000"})
        assert "₹2000" in result
        assert "₹5000" in result

    def test_category_alone(self):
        result = _build_attributes_summary({"category": "Electronics"})
        assert "Electronics" in result

    def test_size_and_color(self):
        result = _build_attributes_summary({"size": "9", "color": "Black"})
        assert "size 9" in result
        assert "Black" in result


class TestGetRecommendations:
    """Tests for get_recommendations function."""

    def test_returns_recommendations_type(self):
        session = _make_session({"category": "Fashion"})
        result = get_recommendations(session)
        assert result["type"] == "recommendations"

    def test_returns_max_5_products(self):
        # Fashion category has many products; we should get at most 5
        session = _make_session({"category": "Fashion"})
        result = get_recommendations(session)
        assert len(result["products"]) <= 5

    def test_products_sorted_by_rating_descending(self):
        session = _make_session({"category": "Fashion"})
        result = get_recommendations(session)
        products = result["products"]
        if len(products) > 1:
            for i in range(len(products) - 1):
                assert products[i]["rating"] >= products[i + 1]["rating"]

    def test_product_format_has_required_fields(self):
        session = _make_session({"category": "Fashion"})
        result = get_recommendations(session)
        if result["products"]:
            product = result["products"][0]
            assert "productId" in product
            assert "title" in product
            assert "price" in product
            assert "rating" in product
            assert "imageUrl" in product

    def test_zero_results_returns_broadening_message(self):
        # Use attributes that won't match anything
        session = _make_session({
            "category": "Fashion",
            "brand": "NonExistentBrand12345",
        })
        result = get_recommendations(session)
        assert result["type"] == "recommendations"
        assert result["products"] == []
        assert "couldn't find" in result["text"].lower()
        assert "broader" in result["text"].lower()

    def test_explanation_references_attributes(self):
        session = _make_session({
            "category": "Fashion",
            "brand": "Nike",
            "subcategory": "shoes",
            "type": "running",
        })
        result = get_recommendations(session)
        if result["products"]:
            assert "preference" in result["text"].lower()
            assert "Nike" in result["text"]

    def test_empty_attributes_returns_all_products_limited(self):
        # Empty attributes should match all products, still return max 5
        session = _make_session({})
        result = get_recommendations(session)
        assert len(result["products"]) <= 5
