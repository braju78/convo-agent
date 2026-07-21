.PHONY: install temporal worker test lint fmt clean

install:
	uv sync

temporal:
	temporal server start-dev --ui-port 8088

worker:
	uv run python -m worker.src.run_worker

run-once:
	@test -n "$(MSG)" || (echo "usage: make run-once MSG='hello'" && exit 1)
	uv run temporal workflow execute \
		--address $${TEMPORAL_ADDRESS:-localhost:7233} \
		--task-queue convo-agent-tq \
		--type ConvoAgent \
		--workflow-id convo-$(shell date +%s) \
		--input '{"conversation_id":"cli","message":"$(MSG)","history":[]}'

test:
	uv run pytest -x -q

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

clean:
	rm -rf .venv __pycache__ .pytest_cache
