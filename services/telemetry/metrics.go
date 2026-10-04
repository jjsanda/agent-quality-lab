package main

import (
	"net/http"
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/collectors"
)

// metricsCollectors owns the Prometheus registry and the HTTP collectors.
type metricsCollectors struct {
	registry *prometheus.Registry
	requests *prometheus.CounterVec
	duration *prometheus.HistogramVec
}

// newMetrics creates a private registry (so we control exactly what is exposed)
// with Go/process collectors plus the two request collectors required by the
// contract.
func newMetrics() *metricsCollectors {
	reg := prometheus.NewRegistry()
	reg.MustRegister(
		collectors.NewGoCollector(),
		collectors.NewProcessCollector(collectors.ProcessCollectorOpts{}),
	)

	requests := prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "telemetry_requests_total",
			Help: "Total HTTP requests handled, labelled by method, route pattern, and status.",
		},
		[]string{"method", "path", "status"},
	)
	duration := prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "telemetry_request_duration_seconds",
			Help:    "HTTP request duration in seconds, labelled by route pattern.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"path"},
	)
	reg.MustRegister(requests, duration)

	return &metricsCollectors{registry: reg, requests: requests, duration: duration}
}

// middleware records the request count and duration. path is normalized to the
// route pattern to keep label cardinality bounded.
func (m *metricsCollectors) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &responseRecorder{ResponseWriter: w, status: http.StatusOK}

		next.ServeHTTP(rec, r)

		path := normalizePath(r.URL.Path)
		m.requests.WithLabelValues(normalizeMethod(r.Method), path, strconv.Itoa(rec.status)).Inc()
		m.duration.WithLabelValues(path).Observe(time.Since(start).Seconds())
	})
}

// normalizeMethod bounds the `method` label to known verbs so an adversarial client sending
// arbitrary RFC-7230 method tokens can't create unbounded metric cardinality.
func normalizeMethod(method string) string {
	switch method {
	case http.MethodGet, http.MethodPost, http.MethodPut, http.MethodPatch,
		http.MethodDelete, http.MethodHead, http.MethodOptions:
		return method
	default:
		return "other"
	}
}
