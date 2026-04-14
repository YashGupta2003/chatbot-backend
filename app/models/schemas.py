"""
models/schemas.py - Pydantic Data Models
==========================================
Defines the shape of every request and response
the API accepts / returns.  FastAPI uses these
models for automatic validation and documentation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ─────────────────────────────────────────────
# Supported Groq models (easy to extend)
# ─────────────────────────────────────────────
class GroqModel(str, Enum):
    llama3_70b    = "llama-3.3-70b-versatile"
    llama3_8b     = "llama3-8b-8192"
    mixtral_8x7b  = "mixtral-8x7b-32768"
    gemma2_9b     = "gemma2-9b-it"


# ─────────────────────────────────────────────
# A single message in a conversation
# ─────────────────────────────────────────────
class Message(BaseModel):
    role: str = Field(
        ...,
        description="Either 'user' or 'assistant'",
        examples=["user"],
    )
    content: str = Field(
        ...,
        description="The text content of the message",
        examples=["Hello! How are you?"],
    )


# ─────────────────────────────────────────────
# POST /chat  →  Request body
# ─────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=8192,
        description="The user's message to the chatbot",
        examples=["Explain quantum computing in simple terms."],
    )
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional session identifier for multi-turn conversations. "
            "If omitted the server creates a new session."
        ),
        examples=["user-abc-123"],
    )
    model: GroqModel = Field(
        default=GroqModel.llama3_70b,
        description="The Groq LLM model to use for this request",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description=(
            "Optional system-level instruction that shapes the assistant's "
            "behaviour. Defaults to a helpful assistant persona."
        ),
        examples=["You are a concise Python tutor."],
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature – higher = more creative, lower = more deterministic",
    )
    max_tokens: int = Field(
        default=1024,
        ge=1,
        le=8192,
        description="Maximum number of tokens in the assistant's reply",
    )
    stream: bool = Field(
        default=True,
        description="Whether to stream the response (Server-Sent Events) or return it all at once",
    )


# ─────────────────────────────────────────────
# POST /chat  →  Non-streaming response body
# ─────────────────────────────────────────────
class ChatResponse(BaseModel):
    session_id: str = Field(..., description="The session ID for follow-up messages")
    message: str = Field(..., description="The assistant's complete reply")
    model: str = Field(..., description="The model that produced the reply")
    usage: Optional[dict] = Field(
        default=None,
        description="Token usage statistics returned by Groq",
    )


# ─────────────────────────────────────────────
# GET /history/{session_id}  →  Response body
# ─────────────────────────────────────────────
class ConversationHistory(BaseModel):
    session_id: str
    messages: List[Message]
    message_count: int


# ─────────────────────────────────────────────
# Generic error response
# ─────────────────────────────────────────────
class ErrorResponse(BaseModel):
    error: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(default=None, description="Additional error detail")
    status_code: int
