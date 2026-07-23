.PHONY: install temporal worker api otel-up otel-down otel-open otel-logs test lint fmt clean

install:
	uv sync

temporal:
	temporal server start-dev --ui-port 8088

worker:
	uv run python -m worker.src.run_worker

api:
	uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

open:
	open http://localhost:8000

otel-up:
	docker compose up -d otel-lgtm
	@echo "Grafana UI: http://localhost:3030 (admin/admin — skip password reset when prompted)"
	@echo "Waiting for healthcheck..."
	@until docker compose ps otel-lgtm --format json 2>/dev/null | grep -q '"Health":"healthy"'; do sleep 2; done
	@echo "otel-lgtm ready."

otel-down:
	docker compose down

otel-open:
	open http://localhost:3030

otel-logs:
	docker compose logs -f otel-lgtm

run-once:
	@test -n "$(MSG)" || (echo "usage: make run-once MSG='hello'" && exit 1)
	uv run temporal workflow execute \
		--address $${TEMPORAL_ADDRESS:-localhost:7233} \
		--task-queue convo-agent-tq \
		--type ConvoAgent \
		--workflow-id convo-$(shell date +%s) \
		--input '{"conversation_id":"cli","message":"$(MSG)","history":[]}'

chat:
	@test -n "$(MSG)" || (echo "usage: make chat MSG='hello' [CID=<conversation_id>]" && exit 1)
	@python3 -c "import json,sys; print(json.dumps({'message':'$(MSG)', **(dict(conversation_id='$(CID)') if '$(CID)' else {})}))" \
		| curl -sS -X POST http://localhost:8000/chat \
			-H "Content-Type: application/json" \
			-d @- \
		| python3 -m json.tool

test:
	uv run pytest -x -q

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

clean:
	rm -rf .venv __pycache__ .pytest_cache
