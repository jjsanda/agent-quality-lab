package main

import (
	"encoding/json"
	"net/http"
	"regexp"
	"time"
)

// maxBodyBytes bounds request bodies to keep the service from buffering huge
// payloads from a misbehaving client.
const maxBodyBytes = 1 << 20 // 1 MiB

// relWindowRe matches a relative time window like "15m" or "2h". The grammar
// mirrors the Python client's contract (\d{1,4}[smhd]).
var relWindowRe = regexp.MustCompile(`^\d{1,4}[smhd]$`)

// validAggregations is the closed set the metrics endpoint accepts; it matches
// the Python QueryMetricsArgs literal.
var validAggregations = map[string]bool{
	"avg": true, "p50": true, "p95": true, "p99": true, "max": true, "rate": true,
}

// validSeverities matches the Python Severity enum.
var validSeverities = map[string]bool{
	"sev1": true, "sev2": true, "sev3": true, "sev4": true,
}

// ---------------------------------------------------------------------------
// Wire types. Field names and JSON tags are the HTTP contract: the Python
// client validates these models with extra="forbid", so responses must carry
// EXACTLY these snake_case fields and nothing more.
// ---------------------------------------------------------------------------

type logsSearchRequest struct {
	Service string `json:"service"`
	Query   string `json:"query"`
	Since   string `json:"since"`
	Limit   *int   `json:"limit"` // pointer: distinguishes "omitted" from 0
}

type logLine struct {
	Timestamp string `json:"timestamp"`
	Level     string `json:"level"`
	Service   string `json:"service"`
	Message   string `json:"message"`
	TraceID   string `json:"trace_id,omitempty"`
}

type logsSearchResponse struct {
	Lines        []logLine `json:"lines"`
	TotalMatched int       `json:"total_matched"`
	Truncated    bool      `json:"truncated"`
}

type metricsQueryRequest struct {
	Service     string `json:"service"`
	Metric      string `json:"metric"`
	Aggregation string `json:"aggregation"`
	Since       string `json:"since"`
	Step        string `json:"step"`
}

type metricPoint struct {
	T string  `json:"t"`
	V float64 `json:"v"`
}

type metricsQueryResponse struct {
	Metric      string        `json:"metric"`
	Unit        string        `json:"unit"`
	Aggregation string        `json:"aggregation"`
	Series      []metricPoint `json:"series"`
}

type runbookResponse struct {
	Slug    string `json:"slug"`
	Title   string `json:"title"`
	Content string `json:"content"`
	Version string `json:"version"`
}

type ticketRequest struct {
	Title    string `json:"title"`
	Service  string `json:"service"`
	Severity string `json:"severity"`
	Body     string `json:"body"`
	Escalate bool   `json:"escalate"`
}

type ticketResponse struct {
	TicketID string `json:"ticket_id"`
	URL      string `json:"url"`
	Status   string `json:"status"`
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------

// writeJSON serializes v as JSON with the given status code. HTML escaping is
// disabled so log messages and URLs survive verbatim (the agent's safety policy
// inspects the raw substrings).
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
}

// writeError writes a {"error": msg} body with the given status code.
func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

// decodeJSON reads and decodes the (size-limited) request body into v. Unknown
// fields are tolerated (be liberal in what we accept); only structural / type
// errors are reported.
func decodeJSON(w http.ResponseWriter, r *http.Request, v any) error {
	r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)
	return json.NewDecoder(r.Body).Decode(v)
}

// validSince reports whether s is a valid `since` value: a relative window or
// an RFC3339 instant.
func validSince(s string) bool {
	if relWindowRe.MatchString(s) {
		return true
	}
	_, err := time.Parse(time.RFC3339, s)
	return err == nil
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

func (s *server) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *server) handleReadyz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *server) handleNotFound(w http.ResponseWriter, _ *http.Request) {
	writeError(w, http.StatusNotFound, "not found")
}

func (s *server) handleLogsSearch(w http.ResponseWriter, r *http.Request) {
	var req logsSearchRequest
	if err := decodeJSON(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.Service == "" {
		writeError(w, http.StatusBadRequest, "field 'service' is required")
		return
	}
	if req.Query == "" {
		writeError(w, http.StatusBadRequest, "field 'query' is required")
		return
	}
	since := req.Since
	if since == "" {
		since = "15m"
	}
	if !validSince(since) {
		writeError(w, http.StatusBadRequest, "field 'since' must be a relative window (e.g. 15m) or RFC3339 timestamp")
		return
	}
	limit := 100
	if req.Limit != nil {
		limit = *req.Limit
		if limit < 1 || limit > 1000 {
			writeError(w, http.StatusBadRequest, "field 'limit' must be between 1 and 1000")
			return
		}
	}

	annotateSpan(r.Context(), "telemetry.service", req.Service, "telemetry.query", req.Query)
	writeJSON(w, http.StatusOK, s.store.SearchLogs(req.Service, req.Query, since, limit))
}

func (s *server) handleMetricsQuery(w http.ResponseWriter, r *http.Request) {
	var req metricsQueryRequest
	if err := decodeJSON(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.Service == "" {
		writeError(w, http.StatusBadRequest, "field 'service' is required")
		return
	}
	if req.Metric == "" {
		writeError(w, http.StatusBadRequest, "field 'metric' is required")
		return
	}
	if req.Aggregation == "" {
		writeError(w, http.StatusBadRequest, "field 'aggregation' is required")
		return
	}
	if !validAggregations[req.Aggregation] {
		writeError(w, http.StatusBadRequest, "field 'aggregation' must be one of avg, p50, p95, p99, max, rate")
		return
	}
	since := req.Since
	if since == "" {
		since = "1h"
	}
	if !validSince(since) {
		writeError(w, http.StatusBadRequest, "field 'since' must be a relative window (e.g. 1h) or RFC3339 timestamp")
		return
	}
	step := req.Step
	if step == "" {
		step = "1m"
	}
	if !relWindowRe.MatchString(step) {
		writeError(w, http.StatusBadRequest, "field 'step' must be a relative window (e.g. 5m)")
		return
	}

	annotateSpan(r.Context(), "telemetry.service", req.Service, "telemetry.metric", req.Metric)
	writeJSON(w, http.StatusOK, s.store.QueryMetrics(req.Service, req.Metric, req.Aggregation, since, step))
}

func (s *server) handleRunbook(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	section := r.URL.Query().Get("section")

	rb, ok := s.store.GetRunbook(slug, section)
	if !ok {
		writeError(w, http.StatusNotFound, "runbook not found")
		return
	}
	annotateSpan(r.Context(), "telemetry.slug", slug)
	writeJSON(w, http.StatusOK, rb)
}

func (s *server) handleTickets(w http.ResponseWriter, r *http.Request) {
	var req ticketRequest
	if err := decodeJSON(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.Title == "" {
		writeError(w, http.StatusBadRequest, "field 'title' is required")
		return
	}
	if req.Service == "" {
		writeError(w, http.StatusBadRequest, "field 'service' is required")
		return
	}
	if req.Body == "" {
		writeError(w, http.StatusBadRequest, "field 'body' is required")
		return
	}
	if !validSeverities[req.Severity] {
		writeError(w, http.StatusBadRequest, "field 'severity' must be one of sev1, sev2, sev3, sev4")
		return
	}

	annotateSpan(r.Context(), "telemetry.service", req.Service, "telemetry.severity", req.Severity)
	writeJSON(w, http.StatusCreated, s.store.CreateTicket(req.Escalate))
}
