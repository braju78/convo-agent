"""ConvoAgent — conversation agent with web search + citations."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Iterable

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from temporalio import workflow
from temporalio.common import RetryPolicy

from agent_utils.core.agent import AgentMetadata
from agent_utils.core.context import initialize_context
from agent_utils.core.common.identity import TenantCallerIdentity
from agent_utils.core.pydantic_ai.agent_workflow import AgentWorkflow

from worker.src.dtos import (
    AppendMessageInput,
    ChatInput,
    ChatMessage,
    ChatResponse,
    ConvoAgentOutput,
    FetchHistoryInput,
    FetchHistoryOutput,
    Source,
)
from worker.src.prompt import SYSTEM_PROMPT
from worker.src.shared import TASK_QUEUE
from worker.src.tools.web_search import web_search

logger = logging.getLogger(__name__)

# Cap history to avoid token blowout — keep last N turns.
_MAX_HISTORY_TURNS = 20

# Retry policy for storage activities — fail-fast on programmer errors, retry
# on transient DB hiccups a couple of times.
_STORAGE_RETRY = RetryPolicy(
    initial_interval=timedelta(milliseconds=100),
    maximum_interval=timedelta(seconds=2),
    maximum_attempts=3,
)


@workflow.defn
class ConvoAgent(AgentWorkflow[ChatInput, ConvoAgentOutput]):
    """Local conversation agent. Web search enabled; free-flow (no HITL).

    Owns its own conversation lifecycle — loads prior history and appends
    user + assistant messages via SDK-registered activities. The API layer
    only creates conversations and invokes the workflow.
    """

    Input = ChatInput
    Output = ConvoAgentOutput
    result_type = ChatResponse

    metadata = AgentMetadata(
        name="ConvoAgent",
        description="Local conversation agent with web search and citations",
        task_queue=TASK_QUEUE,
        model_alias="gpt-4o",
        model_settings={
            "temperature": 0.2,
            "parallel_tool_calls": True,
        },
        max_iterations=10,
        execution_timeout_seconds=120,
        run_timeout_seconds=120,
        system_prompt=SYSTEM_PROMPT,
    )

    io_tools = [web_search]

    _loaded_history: list[ChatMessage] = []

    def get_prompt(self, input: ChatInput) -> str:
        """SDK default reads input.prompt; our DTO uses input.message."""
        return input.message

    def get_message_history(self, input: ChatInput) -> list[ModelMessage] | None:
        """Return prior turns loaded in run() for pydantic-ai's message_history."""
        if not self._loaded_history:
            return None
        recent = self._loaded_history[-_MAX_HISTORY_TURNS * 2 :]
        return _to_model_messages(recent) or None

    @workflow.run
    async def run(self, input: ChatInput) -> ConvoAgentOutput:
        initialize_context(
            caller=TenantCallerIdentity(
                principal_type="user",
                principal_id=input.user_id,
                tenant_id="local-dev",
            ),
            trace_id=workflow.info().workflow_id,
            root_orchestrator_id=workflow.info().workflow_id,
            current_time=workflow.now().isoformat(),
        )

        # Load prior turns before the ReAct loop starts. Empty on first turn.
        history_out = await workflow.execute_activity(
            "fetch_conversation_history",
            FetchHistoryInput(conversation_id=input.conversation_id),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=_STORAGE_RETRY,
            result_type=FetchHistoryOutput,
        )
        self._loaded_history = history_out.messages

        # Persist the user turn BEFORE the LLM call so it's durable even if
        # the ReAct loop fails partway through.
        await workflow.execute_activity(
            "append_message",
            AppendMessageInput(
                conversation_id=input.conversation_id,
                role="user",
                content=input.message,
            ),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=_STORAGE_RETRY,
        )

        output = await super().run(input)

        # Persist assistant reply + sources after the turn completes.
        await workflow.execute_activity(
            "append_message",
            AppendMessageInput(
                conversation_id=input.conversation_id,
                role="assistant",
                content=output.result.text,
                sources=output.result.sources,
            ),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=_STORAGE_RETRY,
        )

        return output

    def _build_output(self, result: ChatResponse) -> ConvoAgentOutput:
        """Wrap LLM result; drop hallucinated citations before returning.

        Any URL the LLM lists in ``sources`` MUST have been produced by an
        actual ``web_search`` call in this run. URLs not present in any
        tool result are dropped and logged.
        """
        cited_urls = _collect_search_urls(self.run_metadata.tool_calls if self.run_metadata else [])
        clean, dropped = _validate_sources(result.sources, cited_urls)
        if dropped:
            logger.warning(
                "Dropped %d hallucinated source URL(s) from ChatResponse: %s",
                len(dropped),
                [s.url for s in dropped],
            )

        validated = result.model_copy(update={"sources": clean})
        metadata = self.run_metadata
        return ConvoAgentOutput(
            result=validated,
            tool_calls=(metadata.tool_calls or None) if metadata else None,
            reasoning_trace=(metadata.reasoning_trace or None) if metadata else None,
            iterations=metadata.iterations if metadata else None,
        )


def _collect_search_urls(tool_calls: Iterable[Any]) -> set[str]:
    """Collect every URL returned by any web_search invocation in this run."""
    urls: set[str] = set()
    for call in tool_calls or []:
        if getattr(call, "tool_name", None) != "web_search":
            continue
        result = getattr(call, "result", None)
        if result is None:
            continue
        # result may be a dict (serialized) or SearchResult model
        items = result.get("results") if isinstance(result, dict) else getattr(result, "results", None)
        for item in items or []:
            url = item.get("url") if isinstance(item, dict) else getattr(item, "url", None)
            if url:
                urls.add(url)
    return urls


def _validate_sources(
    proposed: list[Source], allowed: set[str]
) -> tuple[list[Source], list[Source]]:
    """Split proposed sources into (kept, dropped) based on the allowed-URL set."""
    kept, dropped = [], []
    for source in proposed:
        (kept if source.url in allowed else dropped).append(source)
    return kept, dropped


def _to_model_messages(history: list[ChatMessage]) -> list[ModelMessage]:
    """Convert stored ChatMessage list to pydantic-ai ModelMessage list."""
    messages: list[ModelMessage] = []
    for msg in history:
        if msg.role == "user":
            messages.append(
                ModelRequest(parts=[UserPromptPart(content=msg.content)])
            )
        elif msg.role == "assistant":
            messages.append(
                ModelResponse(parts=[TextPart(content=msg.content)])
            )
    return messages
