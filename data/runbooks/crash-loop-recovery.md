# Crash-Loop Recovery

**Applies to:** pods restarting repeatedly (CrashLoopBackOff / OOMKilled).

## Symptoms
- Rising restart count; readiness probes failing.
- OOMKilled events or a panic at startup in the logs.

## Diagnosis
1. Read the last logs before each restart to find the failure (OOM vs. failed init vs. bad config).
2. Check whether the crash started at a deploy boundary.
3. Confirm resource limits against actual usage.

## Remediation
- If OOMKilled: raise the memory limit and recreate the affected pods to break the loop.
- If a bad release: roll back to the previous known-good image.
- If bad config: correct the config and roll out gradually.

## Rollback
Restore the previous image/config and resource limits. Reversible.
