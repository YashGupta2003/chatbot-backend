"""
services/groq_service.py - Groq API Integration
=================================================
All communication with the Groq inference API lives
here.  Supports:
  • Standard (non-streaming) chat completions
  • Server-Sent Events (SSE) streaming completions

The Groq SDK wraps the OpenAI-compatible REST API,
so the interface is very familiar.
"""

import os
import logging
import json
from typing import AsyncGenerator, List, Dict, Optional

from groq import AsyncGroq, APIError, APIConnectionError, RateLimitError
from dotenv import load_dotenv

# Load .env file so GROQ_API_KEY is available as an env var
load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Default system prompt used when the caller
# doesn't supply one.
# ─────────────────────────────────────────────
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, friendly, and knowledgeable AI assistant. "
    "Answer questions clearly and concisely. "
    "If you're unsure about something, say so honestly."
)


class GroqService:
    """
    Async wrapper around the Groq Python SDK.

    Usage:
        service = GroqService()
        # Non-streaming
        reply, usage = await service.chat(messages, model)
        # Streaming
        async for chunk in service.chat_stream(messages, model):
            print(chunk, end="", flush=True)
    """

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
        # AsyncGroq client – reuse a single instance for connection pooling
        self._client = AsyncGroq(api_key=api_key)
        logger.info("✅ Groq async client initialised")

    # ──────────────────────────────────────────
    # Helper: build the full message list
    # ──────────────────────────────────────────
    @staticmethod
    def _build_messages(
        history: List[Dict[str, str]],
        user_message: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Combine the system prompt + past conversation history +
        the new user message into the format Groq expects.
        """
        messages = []

        # 1. System message (always first)
        messages.append({
            "role":    "system",
            "content": system_prompt or DEFAULT_SYSTEM_PROMPT,
        })

        # 2. Historical turns (already validated role/content pairs)
        messages.extend(history)

        # 3. New user turn
        messages.append({"role": "user", "content": user_message})

        return messages

    # ──────────────────────────────────────────
    # Non-streaming completion
    # ──────────────────────────────────────────
    async def chat(
        self,
        history: List[Dict[str, str]],
        user_message: str,
        model: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> tuple[str, dict]:
        """
        Send a chat request and wait for the full response.

        Returns:
            (assistant_reply: str, usage: dict)
        """
        messages = self._build_messages(history, user_message, system_prompt)

        try:
            logger.info(f"📤 Sending non-streaming request | model={model} | tokens≤{max_tokens}")

            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )

            assistant_reply = response.choices[0].message.content
            usage = {
                "prompt_tokens":     response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens":      response.usage.total_tokens,
            }

            logger.info(f"📥 Response received | total_tokens={usage['total_tokens']}")
            return assistant_reply, usage

        except RateLimitError as e:
            logger.warning(f"⚠️  Rate limit hit: {e}")
            raise
        except APIConnectionError as e:
            logger.error(f"🔌 Connection error: {e}")
            raise
        except APIError as e:
            logger.error(f"❌ Groq API error [{e.status_code}]: {e.message}")
            raise

    # ──────────────────────────────────────────
    # Streaming completion (SSE / chunked)
    # ──────────────────────────────────────────
    async def chat_stream(
        self,
        history: List[Dict[str, str]],
        user_message: str,
        model: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion chunks as they arrive from Groq.

        Yields:
            Server-Sent Event strings, e.g.:
                "data: {\"chunk\": \"Hello\"}\n\n"
            Followed by a terminal:
                "data: [DONE]\n\n"

        The caller wraps this in a FastAPI StreamingResponse.
        """
        messages = self._build_messages(history, user_message, system_prompt)

        try:
            logger.info(f"📤 Sending streaming request | model={model} | tokens≤{max_tokens}")

            stream = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,           # ← enable streaming!
            )

            full_response = []         # accumulate for logging

            async for chunk in stream:
                # Each chunk has a list of choices; we only care about [0]
                delta = chunk.choices[0].delta

                if delta and delta.content:
                    text = delta.content
                    full_response.append(text)

                    # Format as SSE: "data: <json>\n\n"
                    payload = json.dumps({"chunk": text})
                    yield f"data: {payload}\n\n"

            # Signal end-of-stream (mirrors OpenAI convention)
            yield "data: [DONE]\n\n"

            logger.info(
                f"📥 Stream complete | chars={sum(len(t) for t in full_response)}"
            )

        except RateLimitError as e:
            logger.warning(f"⚠️  Rate limit during stream: {e}")
            error_payload = json.dumps({"error": "Rate limit exceeded. Try again later."})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

        except APIConnectionError as e:
            logger.error(f"🔌 Connection error during stream: {e}")
            error_payload = json.dumps({"error": "Could not connect to Groq API."})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

        except APIError as e:
            logger.error(f"❌ Groq API error during stream [{e.status_code}]: {e.message}")
            error_payload = json.dumps({"error": f"Groq API error: {e.message}"})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"


# ─────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────
groq_service = GroqService()
