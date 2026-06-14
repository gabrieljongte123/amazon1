"""FastAPI application entry point with Mangum handler for AWS Lambda."""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from config import settings
from middleware.auth import AuthMiddleware
from middleware.correlation import CorrelationMiddleware
from middleware.logging_middleware import LoggingMiddleware
from middleware.rate_limiter import RateLimiterMiddleware
from routers import sessions, messages, recommendations, cart

logger = logging.getLogger("intentflow.errors")

app = FastAPI(
    title="IntentFlow API",
    description="AI-driven conversational commerce backend for Amazon Now",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Global Exception Handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def pydantic_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert Pydantic validation errors (422) to HTTP 400 with a friendly message.

    Extracts the field name and error type from the first validation error
    and returns the standard error format.
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    # Build a user-friendly message from the validation errors
    errors = exc.errors()
    if errors:
        first_error = errors[0]
        # Extract field path (e.g., ["body", "text"] -> "text")
        field_path = " -> ".join(str(loc) for loc in first_error.get("loc", []) if loc != "body")
        message = f"Validation failed for field '{field_path}': {first_error.get('msg', 'invalid value')}."
    else:
        message = "Request validation failed. Please check your input and try again."

    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "correlationId": correlation_id,
            }
        },
    )


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch all unhandled exceptions and return 502 with standard error format.

    Logs the full stack trace to CloudWatch for debugging.
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    # Log full stack trace for CloudWatch diagnostics
    logger.error(
        "Unhandled exception | correlation_id=%s | path=%s | %s",
        correlation_id,
        request.url.path,
        traceback.format_exc(),
    )

    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "PROCESSING_ERROR",
                "message": "Something went wrong. Please try again.",
                "correlationId": correlation_id,
            }
        },
    )


# ---------------------------------------------------------------------------
# CORS middleware — allow frontend origins
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware stack (order matters — outermost runs first)
# Logging is outermost so it captures the full request lifecycle
app.add_middleware(LoggingMiddleware)
# Rate limiting runs after auth (needs user_id)
app.add_middleware(RateLimiterMiddleware)
# Auth validates/generates user ID
app.add_middleware(AuthMiddleware)
# Correlation generates request tracing ID
app.add_middleware(CorrelationMiddleware)

# Register API routers
app.include_router(sessions.router)
app.include_router(messages.router)
app.include_router(recommendations.router)
app.include_router(cart.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "intentflow-api"}


# Mangum handler for AWS Lambda
handler = Mangum(app, lifespan="off")
