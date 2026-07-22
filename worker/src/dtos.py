from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from agent_utils.core.agent import AgentOutput


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime | None = None


class Source(BaseModel):
    url: str
    title: str
    snippet: str | None = None
    published_at: datetime | None = None


class ChatInput(BaseModel):
    conversation_id: str
    message: str
    user_id: str = "local-user"


class FetchHistoryInput(BaseModel):
    conversation_id: str


class FetchHistoryOutput(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class AppendMessageInput(BaseModel):
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = Field(default_factory=list)


class SearchResult(BaseModel):
    query: str
    results: list[Source]


class ToolSuggestion(BaseModel):
    id: str
    title: str
    enables: list[str]
    why_relevant: str
    config_steps: list[str]
    docs_url: str | None = None


class ChatResponse(BaseModel):
    """LLM-produced structured answer (bound as pydantic-ai result_type)."""

    text: str
    sources: list[Source] = Field(default_factory=list)
    suggested_tools: list[ToolSuggestion] = Field(default_factory=list)


class ConvoAgentOutput(AgentOutput[ChatResponse]):
    """Workflow output envelope — wraps ChatResponse with agent_run_id."""

    agent_run_id: Optional[str] = None
