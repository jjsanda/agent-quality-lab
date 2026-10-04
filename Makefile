UV ?= uv
GO ?= go

.DEFAULT_GOAL := help
.PHONY: help setup fmt lint type test test-cov e2e eval eval-live diagnose \
        go-build go-test up down build logs security diagrams clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies (offline stack + anthropic + otel + dev) and pre-commit hooks
	$(UV) sync --dev --extra anthropic --extra otel
	$(UV) run pre-commit install || true

fmt: ## Auto-fix lint issues and format the code
	$(UV) run ruff check --fix .
	$(UV) run black .

lint: ## Lint (ruff) and check formatting (black)
	$(UV) run ruff check .
	$(UV) run black --check .

type: ## Strict type-check with mypy
	$(UV) run mypy

test: ## Run the test suite
	$(UV) run pytest -q

test-cov: ## Run tests with coverage and enforce the 90% gate
	$(UV) run pytest --cov=aql --cov-report=term-missing --cov-fail-under=90

e2e: ## Run the end-to-end CLI test over the offline stack
	$(UV) run pytest tests/integration/test_cli.py -q

eval: ## Run the evaluation harness (deterministic, offline) and write the report
	$(UV) run python -m evaluation.run_eval

eval-live: ## Run a representative eval subset against the real Claude API (needs ANTHROPIC_API_KEY)
	$(UV) run --extra anthropic python -m evaluation.run_eval --live

diagnose: ## Run the agent on a sample incident (offline, deterministic)
	$(UV) run aql diagnose data/incidents/checkout-latency.json

go-build: ## Build the Go telemetry microservice
	cd services/telemetry && $(GO) build ./...

go-test: ## Run the Go telemetry microservice tests
	cd services/telemetry && $(GO) test ./...

up: ## Build and start the full stack (telemetry + collector + jaeger + prometheus + grafana)
	docker compose up --build -d

demo: up ## Start the stack, run one traced diagnosis, then print the UIs
	@echo "waiting for the telemetry service..." ; \
	until curl -sf http://localhost:8080/healthz >/dev/null; do sleep 1; done ; \
	AQL_OTEL_ENABLED=true AQL_TRANSPORT=http AQL_TELEMETRY_BASE_URL=http://localhost:8080 \
	OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
	$(UV) run --extra otel aql diagnose data/incidents/checkout-latency.json ; \
	echo "" ; echo "Jaeger:     http://localhost:16686 (service 'agent-quality-lab')" ; \
	echo "Grafana:    http://localhost:3000 (dashboard 'agent-quality-lab')" ; \
	echo "Prometheus: http://localhost:9090"

down: ## Stop the stack and remove containers
	docker compose down -v

build: ## Build the Docker images
	docker compose build

logs: ## Tail the telemetry service logs
	docker compose logs -f telemetry

security: ## Audit Python dependencies for known vulnerabilities
	$(UV) run pip-audit || true

diagrams: ## Render the Mermaid diagrams to SVG and PNG
	./scripts/render_diagrams.sh

screenshots: ## Capture Jaeger + Grafana PNGs from the running stack (run `make up` first)
	$(UV) run --extra media python -m playwright install chromium
	$(UV) run --extra media python scripts/capture_screenshots.py

clean: ## Remove caches, coverage and rendered artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
