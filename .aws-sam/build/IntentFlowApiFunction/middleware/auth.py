"""Authentication middleware for IntentFlow.

Extracts and validates X-User-Id header, generating a UUID v4 if absent.
"""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to extract/validate X-User-Id header."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        user_id_header = request.headers.get("x-user-id")

        if user_id_header is None:
            # Generate a new UUID v4 for anonymous users
            generated_id = str(uuid.uuid4())
            request.state.user_id = generated_id
            response = await call_next(request)
            response.headers["X-User-Id"] = generated_id
            return response

        # Validate: must be non-empty and max 64 characters
        if len(user_id_header) == 0 or len(user_id_header) > 64:
            correlation_id = getattr(request.state, "correlation_id", "unknown")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_USER_ID",
                        "message": "Invalid user identifier format. X-User-Id must be a non-empty string of at most 64 characters.",
                        "correlationId": correlation_id,
                    }
                },
            )

        # Valid user ID — store on request state
        request.state.user_id = user_id_header
        response = await call_next(request)
        return response
