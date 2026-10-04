package main

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// newTestServer builds a server with a discarded logger and tracing disabled.
func newTestServer() *server {
	return newServer(NewStore(), slog.New(slog.NewTextHandler(io.Discard, nil)), false)
}

// do issues a request against the assembled handler and returns the recorder.
func do(t *testing.T, s *server, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	var r io.Reader
	if body != "" {
		r = strings.NewReader(body)
	}
	req := httptest.NewRequest(method, path, r)
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	rec := httptest.NewRecorder()
	s.handler.ServeHTTP(rec, req)
	return rec
}

// decodeKeys returns the set of top-level JSON object keys in the body.
func decodeKeys(t *testing.T, body string) map[string]bool {
	t.Helper()
	var m map[string]json.RawMessage
	if err := json.Unmarshal([]byte(body), &m); err != nil {
		t.Fatalf("body is not a JSON object: %v (%s)", err, body)
	}
	keys := make(map[string]bool, len(m))
	for k := range m {
		keys[k] = true
	}
	return keys
}

func assertStatus(t *testing.T, rec *httptest.ResponseRecorder, want int) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status = %d, want %d (body: %s)", rec.Code, want, rec.Body.String())
	}
}

func assertJSONContentType(t *testing.T, rec *httptest.ResponseRecorder) {
	t.Helper()
	if ct := rec.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Fatalf("Content-Type = %q, want application/json", ct)
	}
}

func TestHealthAndReady(t *testing.T) {
	s := newTestServer()

	h := do(t, s, http.MethodGet, "/healthz", "")
	assertStatus(t, h, http.StatusOK)
	assertJSONContentType(t, h)
	if !strings.Contains(h.Body.String(), `"status":"ok"`) {
		t.Fatalf("healthz body = %s", h.Body.String())
	}

	r := do(t, s, http.MethodGet, "/readyz", "")
	assertStatus(t, r, http.StatusOK)
	if !strings.Contains(r.Body.String(), `"status":"ready"`) {
		t.Fatalf("readyz body = %s", r.Body.String())
	}
}

func TestMetricsEndpoint(t *testing.T) {
	s := newTestServer()
	// Generate at least one request so the counters are non-empty.
	do(t, s, http.MethodGet, "/healthz", "")

	rec := do(t, s, http.MethodGet, "/metrics", "")
	assertStatus(t, rec, http.StatusOK)
	body := rec.Body.String()
	for _, want := range []string{"telemetry_requests_total", "telemetry_request_duration_seconds"} {
		if !strings.Contains(body, want) {
			t.Fatalf("/metrics missing %q", want)
		}
	}
	// path label must be the normalized route, not a raw URL.
	if !strings.Contains(body, `path="/healthz"`) {
		t.Fatalf("/metrics missing normalized path label; body:\n%s", body)
	}
}

func TestLogsSearch_OK(t *testing.T) {
	s := newTestServer()
	rec := do(t, s, http.MethodPost, "/v1/logs:search",
		`{"service":"checkout","query":"ERROR","since":"60m","limit":100}`)
	assertStatus(t, rec, http.StatusOK)
	assertJSONContentType(t, rec)

	var resp logsSearchResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.TotalMatched != 5 || len(resp.Lines) != 5 {
		t.Fatalf("want 5 matched/returned, got matched=%d lines=%d", resp.TotalMatched, len(resp.Lines))
	}

	// Strict contract: top-level and per-line keys must be exactly the spec set.
	keys := decodeKeys(t, rec.Body.String())
	wantTop := map[string]bool{"lines": true, "total_matched": true, "truncated": true}
	if !sameKeys(keys, wantTop) {
		t.Fatalf("logs response keys = %v, want %v", keys, wantTop)
	}
	lineKeys := decodeKeys(t, mustFirstElem(t, rec.Body.String(), "lines"))
	allowed := map[string]bool{"timestamp": true, "level": true, "service": true, "message": true, "trace_id": true}
	for k := range lineKeys {
		if !allowed[k] {
			t.Fatalf("unexpected log line key %q (would break Python extra=forbid)", k)
		}
	}
}

func TestLogsSearch_Truncated(t *testing.T) {
	s := newTestServer()
	rec := do(t, s, http.MethodPost, "/v1/logs:search",
		`{"service":"checkout","query":"ERROR","since":"60m","limit":2}`)
	assertStatus(t, rec, http.StatusOK)
	var resp logsSearchResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	if len(resp.Lines) != 2 || resp.TotalMatched != 5 || !resp.Truncated {
		t.Fatalf("want 2 lines / total 5 / truncated, got %+v", resp)
	}
}

func TestLogsSearch_Validation(t *testing.T) {
	s := newTestServer()
	cases := []struct{ name, body string }{
		{"bad json", `{`},
		{"missing service", `{"query":"ERROR"}`},
		{"missing query", `{"service":"checkout"}`},
		{"bad since", `{"service":"checkout","query":"x","since":"yesterday"}`},
		{"limit too low", `{"service":"checkout","query":"x","limit":0}`},
		{"limit too high", `{"service":"checkout","query":"x","limit":5000}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			rec := do(t, s, http.MethodPost, "/v1/logs:search", c.body)
			assertStatus(t, rec, http.StatusBadRequest)
			if !decodeKeys(t, rec.Body.String())["error"] {
				t.Fatalf("want {\"error\":...}, got %s", rec.Body.String())
			}
		})
	}
}

func TestLogsSearch_DefaultSince(t *testing.T) {
	s := newTestServer()
	// No `since` -> default 15m window. Only the 5 ERROR lines within 15m... but
	// the 1800s-old one is outside, so 4 match.
	rec := do(t, s, http.MethodPost, "/v1/logs:search", `{"service":"checkout","query":"ERROR"}`)
	assertStatus(t, rec, http.StatusOK)
	var resp logsSearchResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	if resp.TotalMatched != 4 {
		t.Fatalf("default 15m window: want 4, got %d", resp.TotalMatched)
	}
}

func TestMetricsQuery_OK(t *testing.T) {
	s := newTestServer()
	rec := do(t, s, http.MethodPost, "/v1/metrics:query",
		`{"service":"checkout","metric":"latency_p99_ms","aggregation":"p99","since":"1h","step":"5m"}`)
	assertStatus(t, rec, http.StatusOK)

	var resp metricsQueryResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Metric != "latency_p99_ms" || resp.Unit != "ms" || resp.Aggregation != "p99" {
		t.Fatalf("envelope = %+v", resp)
	}
	if len(resp.Series) != 13 {
		t.Fatalf("want 13 points, got %d", len(resp.Series))
	}

	keys := decodeKeys(t, rec.Body.String())
	want := map[string]bool{"metric": true, "unit": true, "aggregation": true, "series": true}
	if !sameKeys(keys, want) {
		t.Fatalf("metrics response keys = %v, want %v", keys, want)
	}
	ptKeys := decodeKeys(t, mustFirstElem(t, rec.Body.String(), "series"))
	wantPt := map[string]bool{"t": true, "v": true}
	if !sameKeys(ptKeys, wantPt) {
		t.Fatalf("metric point keys = %v, want %v", ptKeys, wantPt)
	}
}

func TestMetricsQuery_Validation(t *testing.T) {
	s := newTestServer()
	cases := []struct{ name, body string }{
		{"bad json", `nope`},
		{"missing service", `{"metric":"latency_p99_ms","aggregation":"p99"}`},
		{"missing metric", `{"service":"checkout","aggregation":"p99"}`},
		{"missing aggregation", `{"service":"checkout","metric":"latency_p99_ms"}`},
		{"bad aggregation", `{"service":"checkout","metric":"latency_p99_ms","aggregation":"p42"}`},
		{"bad since", `{"service":"checkout","metric":"latency_p99_ms","aggregation":"p99","since":"soon"}`},
		{"bad step", `{"service":"checkout","metric":"latency_p99_ms","aggregation":"p99","step":"5x"}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			rec := do(t, s, http.MethodPost, "/v1/metrics:query", c.body)
			assertStatus(t, rec, http.StatusBadRequest)
		})
	}
}

func TestRunbook_OK(t *testing.T) {
	s := newTestServer()
	rec := do(t, s, http.MethodGet, "/v1/runbooks/checkout-latency", "")
	assertStatus(t, rec, http.StatusOK)

	var resp runbookResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Slug != "checkout-latency" || resp.Title == "" || resp.Version == "" {
		t.Fatalf("runbook = %+v", resp)
	}
	keys := decodeKeys(t, rec.Body.String())
	want := map[string]bool{"slug": true, "title": true, "content": true, "version": true}
	if !sameKeys(keys, want) {
		t.Fatalf("runbook keys = %v, want %v", keys, want)
	}
}

func TestRunbook_Section(t *testing.T) {
	s := newTestServer()
	rec := do(t, s, http.MethodGet, "/v1/runbooks/checkout-latency?section=Remediation", "")
	assertStatus(t, rec, http.StatusOK)
	var resp runbookResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	if !strings.HasPrefix(resp.Content, "## Remediation") || strings.Contains(resp.Content, "## Symptoms") {
		t.Fatalf("section narrowing failed: %q", resp.Content)
	}
}

func TestRunbook_NotFound(t *testing.T) {
	s := newTestServer()
	rec := do(t, s, http.MethodGet, "/v1/runbooks/nope", "")
	assertStatus(t, rec, http.StatusNotFound)
	if !strings.Contains(rec.Body.String(), "runbook not found") {
		t.Fatalf("want 'runbook not found', got %s", rec.Body.String())
	}
}

func TestTickets_OpenAndEscalated(t *testing.T) {
	s := newTestServer()

	open := do(t, s, http.MethodPost, "/v1/tickets",
		`{"title":"Checkout latency","service":"checkout","severity":"sev2","body":"p99 over SLO","escalate":false}`)
	assertStatus(t, open, http.StatusCreated)
	var o ticketResponse
	_ = json.Unmarshal(open.Body.Bytes(), &o)
	if o.TicketID != "TCK-1001" || o.Status != "open" || o.URL != "https://tickets.local/TCK-1001" {
		t.Fatalf("open ticket = %+v", o)
	}
	keys := decodeKeys(t, open.Body.String())
	want := map[string]bool{"ticket_id": true, "url": true, "status": true}
	if !sameKeys(keys, want) {
		t.Fatalf("ticket keys = %v, want %v", keys, want)
	}

	esc := do(t, s, http.MethodPost, "/v1/tickets",
		`{"title":"Cart OOM","service":"cart","severity":"sev1","body":"crash loop","escalate":true}`)
	assertStatus(t, esc, http.StatusCreated)
	var e ticketResponse
	_ = json.Unmarshal(esc.Body.Bytes(), &e)
	if e.TicketID != "TCK-1002" || e.Status != "escalated" {
		t.Fatalf("escalated ticket = %+v", e)
	}
}

func TestTickets_Validation(t *testing.T) {
	s := newTestServer()
	cases := []struct{ name, body string }{
		{"bad json", `{`},
		{"missing title", `{"service":"checkout","severity":"sev2","body":"b"}`},
		{"missing service", `{"title":"t","severity":"sev2","body":"b"}`},
		{"missing body", `{"title":"t","service":"checkout","severity":"sev2"}`},
		{"bad severity", `{"title":"t","service":"checkout","severity":"urgent","body":"b"}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			rec := do(t, s, http.MethodPost, "/v1/tickets", c.body)
			assertStatus(t, rec, http.StatusBadRequest)
		})
	}
}

func TestUnknownPathAndMethod(t *testing.T) {
	s := newTestServer()

	unknown := do(t, s, http.MethodGet, "/v1/does-not-exist", "")
	assertStatus(t, unknown, http.StatusNotFound)

	// Wrong method on a known path also collapses to a JSON 404 via the catch-all.
	wrongMethod := do(t, s, http.MethodGet, "/v1/logs:search", "")
	assertStatus(t, wrongMethod, http.StatusNotFound)
	if !decodeKeys(t, wrongMethod.Body.String())["error"] {
		t.Fatalf("want JSON error body, got %s", wrongMethod.Body.String())
	}
}

// --- small test helpers ----------------------------------------------------

func sameKeys(a, b map[string]bool) bool {
	if len(a) != len(b) {
		return false
	}
	for k := range a {
		if !b[k] {
			return false
		}
	}
	return true
}

// mustFirstElem extracts the first element of the array under key as a JSON
// string (used to inspect the keys of nested objects).
func mustFirstElem(t *testing.T, body, key string) string {
	t.Helper()
	var top map[string]json.RawMessage
	if err := json.Unmarshal([]byte(body), &top); err != nil {
		t.Fatalf("decode: %v", err)
	}
	var arr []json.RawMessage
	if err := json.Unmarshal(top[key], &arr); err != nil {
		t.Fatalf("decode array %q: %v", key, err)
	}
	if len(arr) == 0 {
		t.Fatalf("array %q is empty", key)
	}
	return string(arr[0])
}
