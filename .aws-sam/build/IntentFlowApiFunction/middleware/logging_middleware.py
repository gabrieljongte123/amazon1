"""Structured JSON logging middleware for IntentFlow.

Logs each request with method, path, status_code, response_time_ms,
correlation_id, and user_id using Python's logging module.
"""

import json
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("intentflow.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured JSON request logging."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Safely retrieve state values (set by other middleware)
        correlation_id = getattr(request.state, "correlation_id", None)
        user_id = getattr(request.state, "user_id", None)

        log_entry = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "response_time_ms": round(elapsed_ms, 2),
            "correlation_id": correlation_id,
            "user_id": user_id,
        }

        logger.info(json.dumps(log_entry))

        return response
