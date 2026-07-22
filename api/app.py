"""FastAPI wrapper for ConvoAgent — POST /chat + conversation history."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel

from agent_utils.core.logging.setup import configure_logging
from api.store import ConversationStore, sources_from_json
from api.temporal_client import ConvoAgentClient
from worker.src.dtos import ChatInput, ChatResponse, Source
from worker.src.shared import SERVICE_NAME

_HERE = Path(__file__).parent
_templates = Jinja2Templates(directory=str(_HERE / "templates"))

load_dotenv()
logger = logging.getLogger(__name__)

store = ConversationStore(url=os.getenv("CONVO_DB_URL", "sqlite+aiosqlite:///./convo.db"))
temporal_client = ConvoAgentClient()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(service_name=f"{SERVICE_NAME}-api")
    await store.initialize()
    logger.info("API ready; SQLite store initialized")
    yield
    await store.close()


app = FastAPI(title="convo-agent API", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")


# ---------- request / response models ----------


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatReply(BaseModel):
    conversation_id: str
    response: ChatResponse


class ConversationSummary(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime


class HistoryMessage(BaseModel):
    role: str
    content: str
    sources: list[Source] = []
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    messages: list[HistoryMessage]


# ---------- routes ----------


@app.get("/livez")
async def livez() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(request, "index.html", {})


@app.post("/chat/htmx", response_class=HTMLResponse)
async def chat_htmx(
    request: Request,
    message: str = Form(...),
    conversation_id: str = Form(""),
) -> HTMLResponse:
    """HTMX-friendly variant of /chat — returns HTML fragment, not JSON."""
    conv_id = conversation_id or None
    if conv_id is None:
        conv = await store.create_conversation()
        conv_id = conv.id
    elif await store.get_conversation(conv_id) is None:
        # Recover gracefully: user's localStorage points at a stale/missing
        # convo. Start fresh instead of 404-ing the widget.
        conv = await store.create_conversation()
        conv_id = conv.id

    result = await temporal_client.run_turn(
        ChatInput(conversation_id=conv_id, message=message)
    )
    reply: ChatResponse = result.result

    return _templates.TemplateResponse(
        request,
        "_message.html",
        {
            "conversation_id": conv_id,
            "user_message": message,
            "text": reply.text,
            "sources": reply.sources,
            "suggested_tools": reply.suggested_tools,
        },
    )


@app.post("/chat", response_model=ChatReply)
async def chat(req: ChatRequest) -> ChatReply:
    """Run one turn. Persistence (history load + message append) happens inside
    the workflow via SDK-registered activities — API only creates the
    conversation record and dispatches the turn."""
    conv_id = req.conversation_id
    if conv_id is None:
        conv = await store.create_conversation()
        conv_id = conv.id
    elif await store.get_conversation(conv_id) is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conv_id} not found")

    result = await temporal_client.run_turn(
        ChatInput(conversation_id=conv_id, message=req.message)
    )
    return ChatReply(conversation_id=conv_id, response=result.result)


@app.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(limit: int = 50) -> list[ConversationSummary]:
    rows = await store.list_conversations(limit=limit)
    return [
        ConversationSummary(id=r.id, created_at=r.created_at, updated_at=r.updated_at)
        for r in rows
    ]


@app.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str) -> ConversationDetail:
    conv = await store.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    rows = await store.load_messages_raw(conversation_id)
    return ConversationDetail(
        id=conv.id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            HistoryMessage(
                role=row.role,
                content=row.content,
                sources=sources_from_json(row.sources_json),
                created_at=row.created_at,
            )
            for row in rows
        ],
    )
