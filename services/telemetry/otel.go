package main

// otel.go isolates every OpenTelemetry import. The rest of the service depends
// only on the small helpers below (wrapOtel, initTracer, annotateSpan), so it
// builds and runs with zero OTel knowledge and, when tracing is disabled, makes
// no network calls at rest.

import (
	"context"
	"net/http"
	"strings"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/trace"
)

// wrapOtel wraps h with otelhttp so each request gets a server span. When
// enabled is false the handler is returned unchanged (no spans, no overhead).
func wrapOtel(h http.Handler, enabled bool) http.Handler {
	if !enabled {
		return h
	}
	return otelhttp.NewHandler(h, "telemetry.http",
		otelhttp.WithSpanNameFormatter(func(_ string, r *http.Request) string {
			return r.Method + " " + normalizePath(r.URL.Path)
		}),
	)
}

// initTracer configures an OTLP/HTTP exporter and a batching tracer provider,
// installs it globally, and returns a shutdown function that flushes spans.
func initTracer(ctx context.Context, cfg Config) (func(context.Context) error, error) {
	// WithEndpointURL derives the scheme (http -> insecure, https -> TLS) and
	// path from the URL. The standard collector path is /v1/traces.
	endpoint := strings.TrimRight(cfg.OtelEndpoint, "/") + "/v1/traces"
	exporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(endpoint))
	if err != nil {
		return nil, err
	}

	res, err := resource.Merge(
		resource.Default(),
		resource.NewWithAttributes(
			semconv.SchemaURL,
			semconv.ServiceName(cfg.OtelServiceName),
		),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))
	return tp.Shutdown, nil
}

// annotateSpan attaches the given key/value string pairs to the active span.
// When tracing is disabled the span is a no-op and this is effectively free, so
// handlers can call it unconditionally without importing any OTel package.
func annotateSpan(ctx context.Context, kv ...string) {
	span := trace.SpanFromContext(ctx)
	if !span.IsRecording() {
		return
	}
	for i := 0; i+1 < len(kv); i += 2 {
		span.SetAttributes(attribute.String(kv[i], kv[i+1]))
	}
}
