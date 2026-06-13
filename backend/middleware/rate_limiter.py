"""In-memory per-user rate limiting middleware for IntentFlow.

Tracks requests by user_id with timestamps. Returns HTTP 429
when a user exceeds 100 requests per minute.
"""

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from config import settings

# In-memory store: user_id -> list of request timestamps
_request_timestamps: dict[str, list[float]] = defaultdict(list)

# Window size in seconds
_WINDOW_SECONDS = 60


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Per-user rate limiting middleware.

    Allows up to RATE_LIMIT_REQUESTS_PER_MINUTE requests per user
    within a sliding 60-second window. Returns 429 when exceeded.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Extract user_id set by AuthMiddleware
        user_id = getattr(request.state, "user_id", None)
        if user_id is None:
            # If no user_id (shouldn't happen after auth middleware), allow
            return await call_next(request)

        now = time.time()
        window_start = now - _WINDOW_SECONDS
        max_requests = settings.RATE_LIMIT_REQUESTS_PER_MINUTE

        # Get timestamps for this user and prune expired entries
        timestamps = _request_timestamps[user_id]
        # Remove timestamps older than the window
        _request_timestamps[user_id] = [
            ts for ts in timestamps if ts > window_start
        ]
        timestamps = _request_timestamps[user_id]

        # Check if limit exceeded
        if len(timestamps) >= max_requests:
            correlation_id = getattr(request.state, "correlation_id", "unknown")
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "You're going too fast. Please wait a moment.",
                        "correlationId": correlation_id,
                    }
                },
            )

        # Record this request
        timestamps.append(now)

        return await call_next(request)
