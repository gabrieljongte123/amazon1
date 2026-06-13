"""Message processing router for IntentFlow.

Handles user message submission and agent response generation.
"""

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from models.message import MessageRequest
from services.bedrock_client import AgentProcessingError
from services.intent_agent import process_user_message
from services.session_store import get_session, update_session

router = APIRouter(prefix="/sessions", tags=["messages"])


@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    body: MessageRequest,
    request: Request,
):
    """Process a user message and return the agent response.

    Loads the session, invokes the IntentFlow agent pipeline,
    persists the updated session, and returns the response.
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

    # Process message through agent pipeline
    try:
        agent_response = process_user_message(session, body.text)
    except AgentProcessingError as e:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": "PROCESSING_ERROR",
                    "message": str(e.user_message),
                    "correlationId": correlation_id,
                }
            },
        )
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

    # Persist updated session state
    try:
        update_session(session)
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

    # Build response
    response_content = {
        "sessionId": session_id,
        "response": {
            "type": agent_response["type"],
            "text": agent_response["text"],
            "options": agent_response.get("options"),
            "products": agent_response.get("products"),
        },
        "metadata": agent_response.get("metadata", {
            "confidenceScore": session.confidence_score,
            "extractedAttributes": session.extracted_attributes,
            "questionCount": session.question_count,
        }),
    }

    return JSONResponse(status_code=200, content=response_content)
