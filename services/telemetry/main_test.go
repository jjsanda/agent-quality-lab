package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestTruthy(t *testing.T) {
	for _, s := range []string{"1", "true", "TRUE", "yes", "on", "y", "t", " True "} {
		if !truthy(s) {
			t.Errorf("truthy(%q) = false, want true", s)
		}
	}
	for _, s := range []string{"", "0", "false", "no", "off", "nope"} {
		if truthy(s) {
			t.Errorf("truthy(%q) = true, want false", s)
		}
	}
}

func TestGetenv(t *testing.T) {
	if getenv("DEFINITELY_UNSET_TELEMETRY_VAR", "fallback") != "fallback" {
		t.Error("getenv should return the default for an unset var")
	}
	t.Setenv("SET_TELEMETRY_VAR", "value")
	if getenv("SET_TELEMETRY_VAR", "fallback") != "value" {
		t.Error("getenv should return the env value when set")
	}
}

func TestLoadConfig(t *testing.T) {
	// Defaults (no relevant env set).
	t.Setenv("PORT", "")
	t.Setenv("OTEL_ENABLED", "")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	t.Setenv("OTEL_SERVICE_NAME", "")
	def := loadConfig()
	if def.Port != "8080" || def.OtelEnabled ||
		def.OtelEndpoint != "http://localhost:4318" || def.OtelServiceName != "telemetry-service" {
		t.Fatalf("unexpected default config: %+v", def)
	}

	// Overrides.
	t.Setenv("PORT", "9090")
	t.Setenv("OTEL_ENABLED", "true")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
	t.Setenv("OTEL_SERVICE_NAME", "custom")
	cfg := loadConfig()
	if cfg.Port != "9090" || !cfg.OtelEnabled ||
		cfg.OtelEndpoint != "http://collector:4318" || cfg.OtelServiceName != "custom" {
		t.Fatalf("unexpected overridden config: %+v", cfg)
	}
}

func TestWrapOtelDisabledIsIdentity(t *testing.T) {
	called := false
	base := http.HandlerFunc(func(http.ResponseWriter, *http.Request) { called = true })
	wrapped := wrapOtel(base, false)
	wrapped.ServeHTTP(nil, httptestReq())
	if !called {
		t.Fatal("disabled wrapOtel should call through to the base handler")
	}
}

// TestTracingEnabledEndToEnd exercises the OTel-enabled path: a real tracer
// provider is installed, the handler is wrapped with otelhttp, and a request
// produces a recording span that annotateSpan decorates. No collector is
// required (spans are queued and dropped on shutdown).
func TestTracingEnabledEndToEnd(t *testing.T) {
	ctx := context.Background()
	shutdown, err := initTracer(ctx, Config{
		OtelEndpoint:    "http://localhost:4318",
		OtelServiceName: "telemetry-test",
	})
	if err != nil {
		t.Fatalf("initTracer: %v", err)
	}
	defer func() {
		shCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = shutdown(shCtx)
	}()

	s := newServer(NewStore(), slog.New(slog.NewTextHandler(io.Discard, nil)), true)
	rec := do(t, s, http.MethodPost, "/v1/logs:search",
		`{"service":"checkout","query":"ERROR","since":"60m","limit":5}`)
	assertStatus(t, rec, http.StatusOK)
}

func httptestReq() *http.Request {
	r, _ := http.NewRequest(http.MethodGet, "/healthz", nil)
	return r
}

func TestRecoverPanic(t *testing.T) {
	s := newTestServer()
	boom := http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		panic("boom")
	})
	rec := httptest.NewRecorder()
	s.recoverPanic(boom).ServeHTTP(rec, httptestReq())
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500", rec.Code)
	}
	if !decodeKeys(t, rec.Body.String())["error"] {
		t.Fatalf("want JSON error body, got %s", rec.Body.String())
	}
}
