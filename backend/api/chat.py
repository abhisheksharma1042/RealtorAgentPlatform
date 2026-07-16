"""Chat API endpoints with SSE streaming"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import AsyncIterator, Optional

from backend.agent.graph import stream_agent_response


router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Chat request model"""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model"""
    message: str
    session_id: Optional[str] = None


@router.post("/message")
async def send_message(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the agent (non-streaming)

    This endpoint is for simple request-response interactions.
    For streaming, use /stream endpoint.
    """
    try:
        response_text = ""

        async for event in stream_agent_response(request.message):
            if event["type"] == "agent_message":
                response_text = event["content"]
            elif event["type"] == "complete":
                break

        return ChatResponse(
            message=response_text or "No response generated",
            session_id=request.session_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_chat(request: ChatRequest):
    """
    Stream chat responses using Server-Sent Events (SSE)

    This endpoint streams agent responses in real-time, including:
    - Agent thinking messages
    - Tool calls
    - Tool results
    - Final response

    Response format (SSE):
    ```
    data: {"type": "agent_message", "content": "...", "node": "agent"}
    data: {"type": "tool_call", "tool": "fetch_market_data", "args": {...}}
    data: {"type": "tool_result", "tool": "fetch_market_data", "result": {...}}
    data: {"type": "complete"}
    ```
    """

    async def event_generator() -> AsyncIterator[str]:
        """Generate SSE events"""
        try:
            async for event in stream_agent_response(request.message):
                # Format as SSE
                yield f"data: {json.dumps(event)}\n\n"

        except Exception as e:
            # Send error event
            error_event = {
                "type": "error",
                "error": str(e)
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "chat"}
