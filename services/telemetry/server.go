package main

import (
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// server wires together the store, logger, Prometheus collectors, and the fully
// assembled http.Handler (routing + middleware).
type server struct {
	store   *Store
	logger  *slog.Logger
	metrics *metricsCollectors
	handler http.Handler
}

// newServer builds the routed, instrumented handler. When otelEnabled is true
// the whole handler is wrapped with otelhttp so each request gets a server span.
func newServer(store *Store, logger *slog.Logger, otelEnabled bool) *server {
	s := &server{
		store:   store,
		logger:  logger,
		metrics: newMetrics(),
	}

	mux := http.NewServeMux()
	// Go 1.22 method+pattern routing. Colons in path segments (logs:search,
	// metrics:query) are valid literals and are kept intentionally.
	mux.HandleFunc("GET /healthz", s.handleHealthz)
	mux.HandleFunc("GET /readyz", s.handleReadyz)
	mux.Handle("GET /metrics", promhttp.HandlerFor(s.metrics.registry, promhttp.HandlerOpts{}))
	mux.HandleFunc("POST /v1/logs:search", s.handleLogsSearch)
	mux.HandleFunc("POST /v1/metrics:query", s.handleMetricsQuery)
	mux.HandleFunc("GET /v1/runbooks/{slug}", s.handleRunbook)
	mux.HandleFunc("POST /v1/tickets", s.handleTickets)
	// Catch-all so any unmatched method/path returns a JSON 404 (not the
	// default plain-text body).
	mux.HandleFunc("/", s.handleNotFound)

	// Middleware order (outermost first): otel span -> logging -> metrics ->
	// panic recovery -> mux.
	var h http.Handler = mux
	h = s.recoverPanic(h)
	h = s.metrics.middleware(h)
	h = s.logging(h)
	h = wrapOtel(h, otelEnabled)

	s.handler = h
	return s
}

// responseRecorder captures the status code so middleware can log/observe it.
type responseRecorder struct {
	http.ResponseWriter
	status  int
	written bool
}

func (r *responseRecorder) WriteHeader(code int) {
	if !r.written {
		r.status = code
		r.written = true
	}
	r.ResponseWriter.WriteHeader(code)
}

func (r *responseRecorder) Write(b []byte) (int, error) {
	if !r.written {
		r.status = http.StatusOK
		r.written = true
	}
	return r.ResponseWriter.Write(b)
}

// Flush forwards to the underlying writer when it supports flushing (keeps the
// promhttp handler and any streaming responses working through the wrapper).
func (r *responseRecorder) Flush() {
	if f, ok := r.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

// logging emits a structured slog record per request (method, path, status,
// duration).
func (s *server) logging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &responseRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		s.logger.LogAttrs(r.Context(), slog.LevelInfo, "http_request",
			slog.String("method", r.Method),
			slog.String("path", r.URL.Path),
			slog.Int("status", rec.status),
			slog.Duration("duration", time.Since(start)),
		)
	})
}

// recoverPanic converts a panic in a handler into a 500 response instead of
// crashing the server.
func (s *server) recoverPanic(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				s.logger.Error("panic recovered",
					slog.Any("panic", rec),
					slog.String("path", r.URL.Path))
				writeError(w, http.StatusInternalServerError, "internal server error")
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// normalizePath maps a raw request path to a low-cardinality route label for
// Prometheus. Go 1.22's ServeMux does not expose the matched pattern, so the
// mapping is explicit (and bounded: unknown paths collapse to "other").
func normalizePath(p string) string {
	switch p {
	case "/healthz", "/readyz", "/metrics",
		"/v1/logs:search", "/v1/metrics:query", "/v1/tickets":
		return p
	}
	if strings.HasPrefix(p, "/v1/runbooks/") {
		return "/v1/runbooks/{slug}"
	}
	return "other"
}
