"""Recommendations router for IntentFlow.

Handles explicit recommendation retrieval for a session.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services.recommendations import get_recommendations
from services.session_store import get_session

router = APIRouter(prefix="/sessions", tags=["recommendations"])


@router.get("/{session_id}/recommendations")
async def get_session_recommendations(
    session_id: str,
    request: Request,
):
    """Retrieve product recommendations for the given session.

    Loads the session's extracted attributes and queries the product
    catalog for matching products sorted by rating.
    """
    correlation_id: str = getattr(request.state, "correlation_id", "unknown")

    # Load session
    session = get_session(session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": "The session could not be found or has expired.",
                    "correlationId": correlation_id,
                }
            },
        )

    # Get recommendations
    try:
        result = get_recommendations(session)
    except Exception:
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

    return JSONResponse(
        status_code=200,
        content={
            "products": result["products"],
            "explanation": result["text"],
        },
    )
