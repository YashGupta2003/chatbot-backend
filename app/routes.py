"""
routes.py - API Route Definitions
===================================
Defines every HTTP endpoint exposed by the chatbot API.

Endpoints:
  POST   /api/v1/chat                    → Send a message (streaming or not)
  GET    /api/v1/history/{session_id}    → Fetch conversation history
  DELETE /api/v1/history/{session_id}    → Clear a session
  GET    /api/v1/sessions                → List all active sessions (debug)
  GET    /api/v1/models                  → List supported Groq models
"""

import logging
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationHistory,
    ErrorResponse,
    GroqModel,
    Message,
)
from app.services.groq_service import groq_service
from app.utils.memory import conversation_store

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# All routes live under this router.
# It is registered in main.py with prefix /api/v1
# ─────────────────────────────────────────────
router = APIRouter(tags=["Chatbot"])


# ═══════════════════════════════════════════════════════════════════════
# POST /chat
# Main chatbot endpoint – handles both streaming and non-streaming modes
# ═══════════════════════════════════════════════════════════════════════
@router.post(
    "/chat",
    summary="Send a message to the chatbot",
    responses={
        200: {"description": "Assistant reply (JSON or SSE stream)"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def chat(request: ChatRequest):
    """
    Send a user message and receive an AI response.

    **Streaming mode** (`stream: true`, default):
    Returns a `text/event-stream` response.  Each event looks like:
    ```
    data: {"chunk": "Hello"}

    data: {"chunk": " there!"}

    data: [DONE]
    ```

    **Non-streaming mode** (`stream: false`):
    Returns a standard JSON object with the full reply.
    """
    # ── 1. Resolve / create session ──────────────────────────────────
    session_id = conversation_store.create_session(request.session_id)
    logger.info(f"💬 /chat | session={session_id} | stream={request.stream}")

    # ── 2. Fetch existing conversation history ────────────────────────
    history = conversation_store.get_history(session_id)

    # ── 3. Streaming branch ───────────────────────────────────────────
    if request.stream:
        async def event_generator():
            """
            Inner async generator that:
              1. Streams tokens from Groq as SSE events.
              2. Accumulates the full reply.
              3. Saves both user message and assistant reply to memory.
            """
            full_reply_chunks = []

            # First, emit the session_id so the client knows which session to use
            session_event = json.dumps({"session_id": session_id})
            yield f"data: {session_event}\n\n"

            # Stream tokens from Groq
            async for sse_chunk in groq_service.chat_stream(
                history=history,
                user_message=request.message,
                model=request.model.value,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                # Collect non-terminal chunks to build the full reply
                if sse_chunk.strip() != "data: [DONE]":
                    try:
                        # Parse out the text content for accumulation
                        raw = sse_chunk.replace("data: ", "").strip()
                        if raw:
                            payload = json.loads(raw)
                            if "chunk" in payload:
                                full_reply_chunks.append(payload["chunk"])
                    except (json.JSONDecodeError, KeyError):
                        pass   # Skip malformed chunks silently

                yield sse_chunk   # Forward the SSE event to the client

            # ── Save to memory AFTER streaming completes ──
            full_reply = "".join(full_reply_chunks)
            if full_reply:
                conversation_store.add_message(session_id, "user",      request.message)
                conversation_store.add_message(session_id, "assistant", full_reply)
                logger.info(f"💾 Saved exchange to session {session_id}")

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                # Prevent proxies / nginx from buffering the stream
                "X-Accel-Buffering": "no",
                "Cache-Control":     "no-cache",
                "Connection":        "keep-alive",
            },
        )

    # ── 4. Non-streaming branch ───────────────────────────────────────
    try:
        reply, usage = await groq_service.chat(
            history=history,
            user_message=request.message,
            model=request.model.value,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as exc:
        logger.exception(f"❌ Groq API call failed: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Upstream AI service error: {str(exc)}",
        )

    # Save both sides of the conversation
    conversation_store.add_message(session_id, "user",      request.message)
    conversation_store.add_message(session_id, "assistant", reply)

    return ChatResponse(
        session_id=session_id,
        message=reply,
        model=request.model.value,
        usage=usage,
    )


# ═══════════════════════════════════════════════════════════════════════
# GET /history/{session_id}
# ═══════════════════════════════════════════════════════════════════════
@router.get(
    "/history/{session_id}",
    response_model=ConversationHistory,
    summary="Retrieve conversation history for a session",
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def get_history(session_id: str):
    """Return the full message history for the given session ID."""
    if not conversation_store.session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )

    raw_messages = conversation_store.get_history(session_id)
    messages = [Message(role=m["role"], content=m["content"]) for m in raw_messages]

    return ConversationHistory(
        session_id=session_id,
        messages=messages,
        message_count=len(messages),
    )


# ═══════════════════════════════════════════════════════════════════════
# DELETE /history/{session_id}
# ═══════════════════════════════════════════════════════════════════════
@router.delete(
    "/history/{session_id}",
    summary="Delete a conversation session",
    responses={
        200: {"description": "Session deleted"},
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def delete_history(session_id: str):
    """Clear and remove the specified session from memory."""
    deleted = conversation_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )
    return {"message": f"Session '{session_id}' deleted successfully."}


# ═══════════════════════════════════════════════════════════════════════
# GET /sessions   (debug / admin)
# ═══════════════════════════════════════════════════════════════════════
@router.get(
    "/sessions",
    summary="List all active session IDs",
    tags=["Debug"],
)
async def list_sessions():
    """
    Returns all currently active session IDs.
    Useful during development – restrict or remove in production.
    """
    sessions = conversation_store.list_sessions()
    return {
        "active_sessions": sessions,
        "count": len(sessions),
    }


# ═══════════════════════════════════════════════════════════════════════
# GET /models
# ═══════════════════════════════════════════════════════════════════════
@router.get(
    "/models",
    summary="List supported Groq models",
)
async def list_models():
    """Return all Groq model identifiers supported by this API."""
    return {
        "models": [
            {
                "id":          model.value,
                "description": _model_descriptions.get(model.value, ""),
            }
            for model in GroqModel
        ]
    }

# Human-readable descriptions for each model
_model_descriptions = {
    "llama3-70b-8192":    "Meta LLaMA 3 70B – best quality, 8k context",
    "llama3-8b-8192":     "Meta LLaMA 3 8B – fastest, 8k context",
    "mixtral-8x7b-32768": "Mistral Mixtral 8×7B MoE – 32k context",
    "gemma2-9b-it":       "Google Gemma 2 9B instruction-tuned",
}
