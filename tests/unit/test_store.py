"""SQLite conversation store — CRUD + history load."""

from __future__ import annotations

import pytest

from api.store import ConversationStore
from worker.src.dtos import Source


@pytest.fixture
async def store():
    s = ConversationStore(url="sqlite+aiosqlite:///:memory:")
    await s.initialize()
    yield s
    await s.close()


class TestConversationStore:
    async def test_create_returns_id(self, store):
        conv = await store.create_conversation()
        assert conv.id
        assert len(conv.id) == 32

    async def test_get_nonexistent_returns_none(self, store):
        assert await store.get_conversation("does-not-exist") is None

    async def test_append_and_load_history(self, store):
        conv = await store.create_conversation()
        await store.append_message(conv.id, "user", "hello")
        await store.append_message(conv.id, "assistant", "hi there")

        history = await store.load_history(conv.id)
        assert [m.role for m in history] == ["user", "assistant"]
        assert [m.content for m in history] == ["hello", "hi there"]

    async def test_sources_persisted(self, store):
        conv = await store.create_conversation()
        sources = [Source(url="https://a.com", title="A")]
        await store.append_message(conv.id, "assistant", "cite", sources=sources)

        rows = await store.load_messages_raw(conv.id)
        assert len(rows) == 1
        assert rows[0].sources_json == [{"url": "https://a.com", "title": "A", "snippet": None, "published_at": None}]

    async def test_list_conversations_orders_by_updated(self, store):
        c1 = await store.create_conversation()
        c2 = await store.create_conversation()
        # touch c1 so it becomes most recent
        await store.append_message(c1.id, "user", "hi")

        listing = await store.list_conversations()
        assert listing[0].id == c1.id
        assert listing[1].id == c2.id

    async def test_history_empty_for_new_conversation(self, store):
        conv = await store.create_conversation()
        assert await store.load_history(conv.id) == []
