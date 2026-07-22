"""Thin Temporal client wrapper — start ConvoAgent + await result."""

from __future__ import annotations

import uuid

from temporalio.client import Client

from agent_utils.core.worker import connect_temporal
from worker.src.dtos import ChatInput, ConvoAgentOutput
from worker.src.shared import TASK_QUEUE


class ConvoAgentClient:
    """Lazy-connect Temporal client dedicated to ConvoAgent workflows."""

    def __init__(self) -> None:
        self._client: Client | None = None

    async def _ensure_connected(self) -> Client:
        if self._client is None:
            self._client = await connect_temporal()
        return self._client

    async def run_turn(self, chat_input: ChatInput) -> ConvoAgentOutput:
        client = await self._ensure_connected()
        workflow_id = f"convo-{chat_input.conversation_id}-{uuid.uuid4().hex[:8]}"
        handle = await client.start_workflow(
            "ConvoAgent",
            chat_input,
            id=workflow_id,
            task_queue=TASK_QUEUE,
            result_type=ConvoAgentOutput,
        )
        return await handle.result()
