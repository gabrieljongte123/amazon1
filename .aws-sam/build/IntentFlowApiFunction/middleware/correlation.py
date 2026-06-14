"""Correlation ID middleware for IntentFlow.

Generates a unique correlation ID (UUID v4) for each request and attaches it
to the request state and response headers for tracing.
"""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware to generate and attach a correlation ID to each request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        return response
