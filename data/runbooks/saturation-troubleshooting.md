# Saturation Troubleshooting

**Applies to:** services throttling under CPU/memory/disk pressure.

## Symptoms
- CPU saturation sustained above ~85%, or memory near the limit.
- Throttling, queue growth, and rising latency as secondary effects.

## Diagnosis
1. Identify which resource is saturated (CPU, memory, disk, file descriptors).
2. Check for a traffic spike vs. a resource regression in a recent release.
3. Confirm autoscaling is actually firing (and not capped).

## Remediation
- Add one replica and raise the CPU request/limit to reduce throttling.
- If memory-bound: raise the memory limit and investigate for a leak.
- Re-check saturation after scaling; escalate to capacity planning if recurring.

## Rollback
Revert replica count and resource requests/limits to their prior values. Reversible.
