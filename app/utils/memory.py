"""
utils/memory.py - In-Memory Conversation Store
================================================
Manages per-session chat history using a plain
Python dictionary.

In production you would swap this out for Redis,
a database, or another persistent store.  The
interface (get / add / clear) stays the same.
"""

import uuid
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Type alias for a single chat message
# ─────────────────────────────────────────────
ChatMessage = Dict[str, str]   # {"role": "user"|"assistant", "content": "..."}


class ConversationMemory:
    """
    Thread-safe* in-memory store for multi-turn conversations.

    Structure of _store:
        {
            "<session_id>": {
                "messages":    [{"role": "...", "content": "..."}, ...],
                "created_at":  "<ISO timestamp>",
                "updated_at":  "<ISO timestamp>",
            },
            ...
        }

    *FastAPI runs in a single-threaded async event loop so dict access
     is effectively safe without locks.  Add asyncio.Lock if you need
     background threads writing concurrently.
    """

    # Maximum messages kept per session (older ones are trimmed)
    MAX_HISTORY_LENGTH = 50

    def __init__(self):
        self._store: Dict[str, dict] = {}

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def create_session(self, session_id: Optional[str] = None) -> str:
        """
        Create a new conversation session and return its ID.
        If session_id is provided and already exists, it is reused.
        """
        if session_id and session_id in self._store:
            # Session already exists – nothing to do
            return session_id

        sid = session_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._store[sid] = {
            "messages":   [],
            "created_at": now,
            "updated_at": now,
        }
        logger.info(f"📝 New session created: {sid}")
        return sid

    def get_history(self, session_id: str) -> List[ChatMessage]:
        """
        Return the list of messages for a session.
        Returns an empty list if the session doesn't exist.
        """
        session = self._store.get(session_id)
        if session is None:
            return []
        return session["messages"]

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Append a single message to the session history.
        Automatically trims history to MAX_HISTORY_LENGTH.
        """
        if session_id not in self._store:
            # Auto-create session if it was somehow missed
            self.create_session(session_id)

        session = self._store[session_id]
        session["messages"].append({"role": role, "content": content})
        session["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Trim oldest messages (but always keep system-level context)
        if len(session["messages"]) > self.MAX_HISTORY_LENGTH:
            # Keep the last MAX_HISTORY_LENGTH messages
            session["messages"] = session["messages"][-self.MAX_HISTORY_LENGTH:]
            logger.debug(f"⚠️  Trimmed history for session {session_id}")

    def delete_session(self, session_id: str) -> bool:
        """
        Remove a session from memory.
        Returns True if it existed, False otherwise.
        """
        existed = session_id in self._store
        self._store.pop(session_id, None)
        if existed:
            logger.info(f"🗑️  Session deleted: {session_id}")
        return existed

    def clear(self) -> None:
        """Remove ALL sessions (called on app shutdown)."""
        count = len(self._store)
        self._store.clear()
        logger.info(f"🧹 Cleared {count} sessions from memory")

    def session_exists(self, session_id: str) -> bool:
        """Check whether a session ID is currently active."""
        return session_id in self._store

    def get_session_meta(self, session_id: str) -> Optional[dict]:
        """Return metadata (timestamps, message count) for a session."""
        session = self._store.get(session_id)
        if session is None:
            return None
        return {
            "session_id":    session_id,
            "message_count": len(session["messages"]),
            "created_at":    session["created_at"],
            "updated_at":    session["updated_at"],
        }

    def list_sessions(self) -> List[str]:
        """Return all active session IDs (useful for admin / debugging)."""
        return list(self._store.keys())


# ─────────────────────────────────────────────
# Module-level singleton shared across the app
# ─────────────────────────────────────────────
conversation_store = ConversationMemory()
