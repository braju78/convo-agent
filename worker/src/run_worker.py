"""Temporal worker entry point for ConvoAgent."""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from agent_utils.core.activity import ActivityRegistry
from agent_utils.core.logging.setup import configure_logging
from agent_utils.core.worker import (
    SANDBOX_PASSTHROUGH_MODULES,
    connect_temporal,
    get_all_worker_activities,
    get_default_interceptors,
    get_default_nexus_handlers,
)

from worker.src.activities.history import append_message, fetch_conversation_history
from worker.src.shared import SERVICE_NAME, TASK_QUEUE
from worker.src.workflow import ConvoAgent

load_dotenv()

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging(service_name=SERVICE_NAME)
    logger.info("Starting worker on task queue %s", TASK_QUEUE)

    client = await connect_temporal()

    sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules(
            *SANDBOX_PASSTHROUGH_MODULES
        )
    )

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ConvoAgent],
        activities=[
            *get_all_worker_activities(),
            *ActivityRegistry.get_all_activities(),
            *ConvoAgent.get_temporal_activities(),
            fetch_conversation_history,
            append_message,
        ],
        nexus_service_handlers=get_default_nexus_handlers(),
        interceptors=get_default_interceptors(),
        workflow_runner=sandbox_runner,
    )

    logger.info("Worker ready — polling %s @ %s", TASK_QUEUE, os.getenv("TEMPORAL_ADDRESS", "localhost:7233"))
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
