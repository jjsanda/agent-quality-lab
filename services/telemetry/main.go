// Command telemetry is a small HTTP microservice that serves deterministic,
// in-memory mock telemetry (logs, metrics), runbooks, and tickets for an AI
// incident-response agent.
//
// Everything it returns is fixed and reproducible: there is no randomness and
// no external data store, so the agent (and its test/eval harness) sees the
// same answers on every run. The data deliberately includes prompt-injection
// fixtures and one poisoned runbook so a downstream agent can be exercised on
// resisting them.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

// Config holds the runtime configuration. Every field has a safe default so the
// service runs with an empty environment and zero external dependencies.
type Config struct {
	// Port is the TCP port to listen on (env PORT, default "8080").
	Port string
	// OtelEnabled turns on OpenTelemetry tracing (env OTEL_ENABLED, truthy).
	OtelEnabled bool
	// OtelEndpoint is the OTLP/HTTP collector endpoint
	// (env OTEL_EXPORTER_OTLP_ENDPOINT, default "http://localhost:4318").
	OtelEndpoint string
	// OtelServiceName is the resource service.name reported in spans
	// (env OTEL_SERVICE_NAME, default "telemetry-service").
	OtelServiceName string
}

// loadConfig reads configuration from the environment, applying defaults.
func loadConfig() Config {
	return Config{
		Port:            getenv("PORT", "8080"),
		OtelEnabled:     truthy(os.Getenv("OTEL_ENABLED")),
		OtelEndpoint:    getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
		OtelServiceName: getenv("OTEL_SERVICE_NAME", "telemetry-service"),
	}
}

// getenv returns the value of key, or def when key is unset or empty.
func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// runHealthcheck probes the local /healthz endpoint and returns a process exit
// code (0 = healthy, 1 = unhealthy). Used by the container HEALTHCHECK.
func runHealthcheck(port string) int {
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://127.0.0.1:" + port + "/healthz")
	if err != nil {
		return 1
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode == http.StatusOK {
		return 0
	}
	return 1
}

// truthy reports whether s looks like an affirmative boolean flag.
func truthy(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "1", "true", "yes", "on", "y", "t":
		return true
	default:
		return false
	}
}

func main() {
	cfg := loadConfig()

	// `telemetry -healthcheck` performs a local HTTP probe and exits 0/1. This
	// lets the container HEALTHCHECK reuse the single static binary, so the
	// runtime image needs no shell or curl (works on distroless).
	if len(os.Args) > 1 && (os.Args[1] == "-healthcheck" || os.Args[1] == "--healthcheck") {
		os.Exit(runHealthcheck(cfg.Port))
	}

	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	// ctx is cancelled on the first SIGINT/SIGTERM, which drives shutdown.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Optional OpenTelemetry tracing. When disabled there is zero network at
	// rest: no exporter is created and the global tracer stays a no-op.
	if cfg.OtelEnabled {
		shutdown, err := initTracer(ctx, cfg)
		if err != nil {
			logger.Error("otel init failed; continuing without tracing", slog.Any("error", err))
		} else {
			logger.Info("otel tracing enabled",
				slog.String("endpoint", cfg.OtelEndpoint),
				slog.String("service_name", cfg.OtelServiceName))
			defer func() {
				shCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
				defer cancel()
				if err := shutdown(shCtx); err != nil {
					logger.Error("otel shutdown failed", slog.Any("error", err))
				}
			}()
		}
	}

	store := NewStore()
	srv := newServer(store, logger, cfg.OtelEnabled)

	httpServer := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           srv.handler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	// Serve in the background so main can wait on the shutdown signal.
	go func() {
		logger.Info("telemetry service listening", slog.String("addr", httpServer.Addr))
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("server error", slog.Any("error", err))
			stop() // unblock main and shut everything down
		}
	}()

	<-ctx.Done()
	logger.Info("shutdown signal received; draining connections")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		logger.Error("graceful shutdown failed", slog.Any("error", err))
	}
	logger.Info("server stopped")
}
