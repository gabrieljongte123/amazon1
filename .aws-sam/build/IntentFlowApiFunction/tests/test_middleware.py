"""Tests for the middleware stack (auth, correlation, logging)."""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_correlation_id_generated(client):
    """Each request gets a unique correlation ID in the response."""
    r = await client.get("/health")
    assert r.status_code == 200
    correlation_id = r.headers.get("x-correlation-id")
    assert correlation_id is not None
    # Verify it's a valid UUID v4
    parsed = uuid.UUID(correlation_id, version=4)
    assert str(parsed) == correlation_id


@pytest.mark.anyio
async def test_correlation_id_unique_per_request(client):
    """Each request gets a different correlation ID."""
    r1 = await client.get("/health")
    r2 = await client.get("/health")
    assert r1.headers["x-correlation-id"] != r2.headers["x-correlation-id"]


@pytest.mark.anyio
async def test_user_id_generated_when_missing(client):
    """When X-User-Id header is absent, a UUID v4 is generated."""
    r = await client.get("/health")
    assert r.status_code == 200
    user_id = r.headers.get("x-user-id")
    assert user_id is not None
    # Verify it's a valid UUID v4
    parsed = uuid.UUID(user_id, version=4)
    assert str(parsed) == user_id


@pytest.mark.anyio
async def test_user_id_accepted_when_valid(client):
    """A valid X-User-Id (non-empty, <= 64 chars) is accepted."""
    r = await client.get("/health", headers={"X-User-Id": "test-user-123"})
    assert r.status_code == 200


@pytest.mark.anyio
async def test_user_id_accepted_at_max_length(client):
    """A 64-character X-User-Id is accepted (boundary)."""
    r = await client.get("/health", headers={"X-User-Id": "a" * 64})
    assert r.status_code == 200


@pytest.mark.anyio
async def test_user_id_rejected_when_empty(client):
    """An empty X-User-Id header returns HTTP 400."""
    r = await client.get("/health", headers={"X-User-Id": ""})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_USER_ID"


@pytest.mark.anyio
async def test_user_id_rejected_when_too_long(client):
    """A X-User-Id header > 64 characters returns HTTP 400."""
    r = await client.get("/health", headers={"X-User-Id": "x" * 65})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_USER_ID"
