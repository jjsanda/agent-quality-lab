# syntax=docker/dockerfile:1

# ---- build stage ----------------------------------------------------------
FROM golang:1.22 AS builder

WORKDIR /src

# Download modules first so the layer is cached across source-only changes.
COPY go.mod go.sum ./
RUN go mod download

COPY . .

# Static, reproducible, stripped binary. GOTOOLCHAIN=local pins the image's
# Go 1.22 toolchain (no surprise auto-upgrades).
ENV CGO_ENABLED=0 \
    GOOS=linux \
    GOTOOLCHAIN=local
RUN go build -trimpath -ldflags="-s -w" -o /out/telemetry .

# ---- runtime stage --------------------------------------------------------
# distroless/static: no shell, no package manager, minimal attack surface.
FROM gcr.io/distroless/static:nonroot

WORKDIR /

COPY --from=builder /out/telemetry /telemetry

# Run as the image's built-in unprivileged user (uid 65532).
USER nonroot:nonroot

EXPOSE 8080

# Reuse the single binary as its own healthcheck client (no curl needed).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["/telemetry", "-healthcheck"]

ENTRYPOINT ["/telemetry"]
