"""Conversation-history activities.

Owns the persistence side of a chat turn: workflow calls these to load prior
history and append new messages. Backed by the same SQLite DB the API reads
from.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from temporalio import activity

from api.store import ConversationStore
from worker.src.dtos import (
    AppendMessageInput,
    ChatMessage,
    FetchHistoryInput,
    FetchHistoryOutput,
)

logger = logging.getLogger(__name__)

_store: Optional[ConversationStore] = None


async def _get_store() -> ConversationStore:
    """Lazy singleton — one store per activity worker process."""
    global _store
    if _store is None:
        url = os.getenv("CONVO_DB_URL", "sqlite+aiosqlite:///./convo.db")
        _store = ConversationStore(url=url)
        await _store.initialize()
    return _store


@activity.defn(name="fetch_conversation_history")
async def fetch_conversation_history(input: FetchHistoryInput) -> FetchHistoryOutput:
    """Load prior messages for a conversation, oldest first."""
    store = await _get_store()
    messages = await store.load_history(input.conversation_id)
    return FetchHistoryOutput(messages=messages)


@activity.defn(name="append_message")
async def append_message(input: AppendMessageInput) -> None:
    """Persist a message on a conversation. No return value."""
    store = await _get_store()
    await store.append_message(
        conversation_id=input.conversation_id,
        role=input.role,
        content=input.content,
        sources=input.sources or None,
    )
