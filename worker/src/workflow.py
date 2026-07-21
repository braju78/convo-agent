"""ConvoAgent — conversation agent with web search + citations."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

from agent_utils.core.agent import AgentMetadata
from agent_utils.core.context import initialize_context
from agent_utils.core.common.identity import TenantCallerIdentity
from agent_utils.core.pydantic_ai.agent_workflow import AgentWorkflow

from worker.src.dtos import ChatInput, ChatResponse, ConvoAgentOutput
from worker.src.prompt import SYSTEM_PROMPT
from worker.src.shared import TASK_QUEUE
from worker.src.tools.web_search import web_search


@workflow.defn
class ConvoAgent(AgentWorkflow[ChatInput, ConvoAgentOutput]):
    """Local conversation agent. Web search enabled; free-flow (no HITL)."""

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

    def get_prompt(self, input: ChatInput) -> str:
        """SDK default reads input.prompt; our DTO uses input.message."""
        return input.message

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

        # Delegate to the SDK's AgentWorkflow.run — it handles bridge construction,
        # prompt building, ReAct loop, and output wrapping. Phase 3 will wire the
        # full history into execution_options.message_history before delegating.
        return await super().run(input)
