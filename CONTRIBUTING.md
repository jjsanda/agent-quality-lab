# Contributing

Thanks for taking a look! This is primarily a portfolio project, but the workflow is the same one I'd use on a team.

## Prerequisites

- Python 3.11+ and [`uv`](https://github.com/astral-sh/uv)
- Go 1.22+ (only for the telemetry microservice)
- Node.js 18+ (only for rendering diagrams via `npx`)
- Docker + Docker Compose (only for the observability stack)

## Getting started

```bash make setup     # uv sync (offline stack + anthropic + otel + dev) and install pre-commit hooks make test      # run the test suite make eval      # run the deterministic evaluation gate ```

## Before you push

The CI gates are mirrored locally; run them before opening a PR:

```bash make lint      # ruff + black --check make type      # mypy --strict make test-cov  # pytest with the 90% coverage gate make eval      # the evaluation gate (must stay green) make go-test   # Go service tests ```

## Conventions

- **Hexagonal architecture.** `aql.domain` is framework-free; framework code (LangGraph, Anthropic, httpx, OpenTelemetry) lives only in `aql.adapters` / `aql.graph` / `aql.observability` and is wired by `aql.factory`. Add a new provider/transport as an adapter behind the existing port — don't reach across the boundary.
- **Determinism.** Anything on the offline path must stay reproducible: no wall-clock, no RNG, no network. Inject a `Clock`/`IdGenerator` instead.
- **Typed & tested.** New code is fully type-annotated (`mypy --strict`) and covered by a test. Public functions carry a docstring; load-bearing ones carry a doctest.
- **Conventional Commits** for commit messages (`feat:`, `fix:`, `docs:`, `test:`, `chore:` …).
