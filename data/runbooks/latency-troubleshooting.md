# Latency Troubleshooting

**Applies to:** any service breaching a latency SLO (p95/p99).

## Symptoms
- p99 latency above the SLO threshold for a sustained window.
- Upstream timeouts or queueing reported by callers.

## Diagnosis
1. Confirm the breach in the latency dashboard and identify the affected endpoints.
2. Check connection-pool utilisation and database/cache latency for the service.
3. Correlate with the most recent deploy and with CPU/memory saturation.

## Remediation
- If pool saturation is the cause: scale out by one replica and raise the connection-pool size.
- If a slow dependency is the cause: enable the cached/fallback path and open a ticket with the owner.
- Re-check p99 after each change; do not stack multiple changes at once.

## Rollback
Revert the replica count and pool size to their previous values; redeploy the last known-good release if a deploy is implicated. No data changes are involved.
