"""Integration tests for all API routers."""

import os
import sys

# Ensure project root and backend are on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ["USE_LOCAL_STORE"] = "true"
os.environ["USE_LOCAL_BEDROCK"] = "true"

from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_create_session():
    r = client.post(
        "/sessions",
        json={"category": "Fashion"},
        headers={"X-User-Id": "test-user-1"},
    )
    assert r.status_code == 201
    data = r.json()
    assert "sessionId" in data
    assert data["message"] == "Hi! I'm here to help you find exactly what you need. What are you looking for today?"
    assert data["userId"] == "test-user-1"


def test_create_session_no_body():
    r = client.post("/sessions", headers={"X-User-Id": "test-user-2"})
    assert r.status_code == 201
    data = r.json()
    assert "sessionId" in data
    assert data["userId"] == "test-user-2"


def test_send_message():
    # Create session first
    r = client.post(
        "/sessions",
        json={"category": "Fashion"},
        headers={"X-User-Id": "test-user-3"},
    )
    session_id = r.json()["sessionId"]

    # Send message
    r = client.post(
        f"/sessions/{session_id}/messages",
        json={"text": "I need running shoes"},
        headers={"X-User-Id": "test-user-3"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["sessionId"] == session_id
    assert "response" in data
    assert data["response"]["type"] in ("question", "recommendations")
    assert "metadata" in data


def test_send_message_session_not_found():
    r = client.post(
        "/sessions/nonexistent-id/messages",
        json={"text": "hello"},
        headers={"X-User-Id": "test-user-4"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_send_message_whitespace_only():
    r = client.post(
        "/sessions/any-id/messages",
        json={"text": "   "},
        headers={"X-User-Id": "test-user-5"},
    )
    assert r.status_code == 422  # Pydantic validation error


def test_get_recommendations():
    # Create session
    r = client.post(
        "/sessions",
        json={"category": "Fashion"},
        headers={"X-User-Id": "test-user-6"},
    )
    session_id = r.json()["sessionId"]

    # Get recommendations
    r = client.get(
        f"/sessions/{session_id}/recommendations",
        headers={"X-User-Id": "test-user-6"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "products" in data
    assert "explanation" in data


def test_get_recommendations_session_not_found():
    r = client.get(
        "/sessions/nonexistent/recommendations",
        headers={"X-User-Id": "test-user-7"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_cart_valid_product():
    r = client.post(
        "/cart/items",
        json={"productId": "PROD-001", "quantity": 1},
        headers={"X-User-Id": "test-user-8"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["productId"] == "PROD-001"
    assert data["quantity"] == 1
    assert data["cartItemCount"] == 1
    assert "title" in data
    assert "price" in data


def test_cart_invalid_product():
    r = client.post(
        "/cart/items",
        json={"productId": "INVALID-PRODUCT", "quantity": 1},
        headers={"X-User-Id": "test-user-9"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_cart_invalid_quantity():
    r = client.post(
        "/cart/items",
        json={"productId": "PROD-001", "quantity": 15},
        headers={"X-User-Id": "test-user-10"},
    )
    assert r.status_code == 422  # Pydantic validation (quantity > 10)


def test_rate_limiting():
    """Test that rate limiting kicks in after 100 requests."""
    # Use a unique user to avoid interference
    user_id = "rate-limit-test-user"
    # Send 100 requests quickly
    for i in range(100):
        r = client.get("/health", headers={"X-User-Id": user_id})
        assert r.status_code == 200

    # 101st request should be rate limited
    r = client.get("/health", headers={"X-User-Id": user_id})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
