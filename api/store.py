"""SQLite conversation persistence via sqlmodel."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import event
from sqlmodel import Column, Field, JSON, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from worker.src.dtos import ChatMessage, Source


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    return uuid.uuid4().hex


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: str = Field(default_factory=_uuid_str, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = Field(default_factory=_uuid_str, primary_key=True)
    conversation_id: str = Field(index=True, foreign_key="conversations.id")
    role: str
    content: str
    sources_json: list[dict] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)


class ConversationStore:
    """Thin async wrapper over sqlmodel for conversation + message CRUD."""

    def __init__(self, url: str = "sqlite+aiosqlite:///./convo.db") -> None:
        self._engine: AsyncEngine = create_async_engine(url, echo=False)
        # Enable WAL for safe concurrent readers alongside a single writer.
        if url.startswith("sqlite"):
            _install_wal_pragma(self._engine)

    async def initialize(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    async def create_conversation(self) -> Conversation:
        conv = Conversation()
        async with AsyncSession(self._engine) as session:
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
        return conv

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        async with AsyncSession(self._engine) as session:
            return await session.get(Conversation, conversation_id)

    async def list_conversations(self, limit: int = 50) -> list[Conversation]:
        async with AsyncSession(self._engine) as session:
            stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
            result = await session.exec(stmt)
            return list(result.all())

    async def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[Source] | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources_json=[s.model_dump(mode="json") for s in (sources or [])] or None,
        )
        async with AsyncSession(self._engine) as session:
            session.add(msg)
            # Bump conversation updated_at
            conv = await session.get(Conversation, conversation_id)
            if conv is not None:
                conv.updated_at = _utcnow()
                session.add(conv)
            await session.commit()
            await session.refresh(msg)
        return msg

    async def load_messages_raw(self, conversation_id: str) -> list[Message]:
        """Load full Message rows (with sources_json) for detail views."""
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
            result = await session.exec(stmt)
            return list(result.all())

    async def load_history(self, conversation_id: str) -> list[ChatMessage]:
        async with AsyncSession(self._engine) as session:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
            result = await session.exec(stmt)
            rows = list(result.all())
        return [
            ChatMessage(role=row.role, content=row.content, timestamp=row.created_at)
            for row in rows
        ]

    async def close(self) -> None:
        await self._engine.dispose()


def _install_wal_pragma(engine: AsyncEngine) -> None:
    """Enable WAL journaling for safe concurrent reads."""

    @event.listens_for(engine.sync_engine, "connect")
    def _pragma(dbapi_conn, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def sources_from_json(raw: list[dict] | None) -> list[Source]:
    if not raw:
        return []
    return [Source.model_validate(item) for item in raw]


__all__ = [
    "Conversation",
    "ConversationStore",
    "Message",
    "sources_from_json",
]
