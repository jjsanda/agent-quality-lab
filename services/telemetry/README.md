# telemetry-service

A small, **deterministic** Go 1.22 HTTP microservice that serves mock telemetry (logs + metrics), runbooks, and tickets for an AI incident-response agent. It is the `http` transport behind the Python `agent-quality-lab` agent; the wire contract is documented in [`../../docs/contracts/telemetry.openapi.yaml`](../../docs/contracts/telemetry.openapi.yaml).

Everything it returns is fixed and reproducible. All time-windowed answers are computed relative to a pinned reference clock — **`2026-06-30T11:05:00Z`** — and metric series are a fixed function of `service + metric + index` (no randomness), so the agent and its evaluation gate see identical data on every run.

> The seed data intentionally contains **prompt-injection fixtures** (two log lines and one poisoned runbook) so a downstream agent can be demonstrated *refusing* to act on untrusted tool output. They are data, never instructions.

## Endpoints

| Method | Path                  | Description                                   |
| ------ | --------------------- | --------------------------------------------- |
| GET    | `/healthz`            | Liveness — `{"status":"ok"}`                  |
| GET    | `/readyz`             | Readiness — `{"status":"ready"}`              |
| GET    | `/metrics`            | Prometheus text exposition                    |
| POST   | `/v1/logs:search`     | Search seeded logs (`since` / `query` / `limit`) |
| POST   | `/v1/metrics:query`   | Deterministic metric time series              |
| GET    | `/v1/runbooks/{slug}` | Fetch a runbook (optional `?section=`)        |
| POST   | `/v1/tickets`         | Open a ticket (atomic id counter from 1001)   |

Routing uses Go 1.22 `net/http.ServeMux` method+pattern matching; the `:` in `logs:search` / `metrics:query` is a literal path character. Malformed JSON or missing required fields return `400 {"error":"..."}`; any unmatched method/path returns `404 {"error":"not found"}`.

## Seed data

- **Services:** `checkout`, `payments`, `search-api`, `cart` (failure modes: checkout = DB connection-pool exhaustion / latency, payments = upstream 5xx error-rate, search-api = CPU saturation, cart = crash loop / OOM).
- **Metrics:** `latency_p99_ms` (ms), `error_rate` (ratio 0..1), `cpu_saturation_pct` (percent), `restart_count` (count). Aggregations: `avg`, `p50`, `p95`, `p99`, `max`, `rate`.
- **Runbooks (slugs):** `checkout-latency`, `payments-error-rate`, `search-saturation`, `cart-crash-loop`, `db-connection-pool`, `deploy-rollback`, and the poisoned `untrusted-vendor-runbook`.

## Run it

```bash
# From this directory:
go run .                       # listens on :8080 go test ./...                  # unit + handler tests (httptest) go vet ./... && gofmt -l .     # lint / format

# Try it:
curl localhost:8080/healthz curl -s localhost:8080/v1/logs:search \ -d '{"service":"checkout","query":"ERROR","since":"15m","limit":100}' curl -s localhost:8080/v1/metrics:query \ -d '{"service":"checkout","metric":"latency_p99_ms","aggregation":"p99","since":"1h","step":"5m"}' curl -s localhost:8080/v1/runbooks/checkout-latency curl -s localhost:8080/v1/tickets \ -d '{"title":"Checkout latency","service":"checkout","severity":"sev2","body":"p99 over SLO","escalate":false}' ```

### Docker

```bash docker build -t telemetry-service . docker run --rm -p 8080:8080 telemetry-service ```

Multi-stage build (`golang:1.22` → `gcr.io/distroless/static:nonroot`), runs as a non-root user, and ships a `HEALTHCHECK` that reuses the binary itself (`/telemetry -healthcheck`) so the runtime image needs no shell or curl.

## Configuration (env, all with safe defaults)

| Variable                      | Default                  | Purpose                              |
| ----------------------------- | ------------------------ | ------------------------------------ |
| `PORT`                        | `8080`                   | Listen port                          |
| `OTEL_ENABLED`                | `false`                  | Enable OpenTelemetry tracing (truthy)|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318`  | OTLP/HTTP collector endpoint         |
| `OTEL_SERVICE_NAME`           | `telemetry-service`      | `service.name` resource attribute    |

The server shuts down gracefully on `SIGINT`/`SIGTERM` via `http.Server.Shutdown`.

## Observability

- **Logging:** stdlib `log/slog` JSON handler — one record per request (`method`, `path`, `status`, `duration`).
- **Metrics (Prometheus):**
  - `telemetry_requests_total{method,path,status}` — request counter.
  - `telemetry_request_duration_seconds{path}` — duration histogram.

  `path` is normalized to the route pattern (e.g. `/v1/runbooks/{slug}`, `other`) to keep label cardinality bounded.
- **Tracing (opt-in):** when `OTEL_ENABLED` is truthy, the mux is wrapped with `otelhttp` and an OTLP/HTTP exporter is configured. Spans carry the queried `service` / `metric` / `slug`. When disabled there is zero network at rest. All OpenTelemetry imports are isolated to `otel.go`.
