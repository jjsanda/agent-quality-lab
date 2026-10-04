# Error-Rate Troubleshooting

**Applies to:** services with an elevated 4xx/5xx error rate.

## Symptoms
- 5xx rate above baseline; error-budget burn alert firing.
- A spike that correlates with a recent deploy or a dependency change.

## Diagnosis
1. Group errors by endpoint and status code; identify the dominant signature.
2. Check whether the spike starts at a deploy boundary (likely a regression).
3. Inspect dependency health for the failing calls.

## Remediation
- If a deploy regression is implicated: roll back to the previous known-good release.
- If a dependency is failing: enable the circuit breaker / fallback and retry with backoff.
- Confirm the error rate returns to baseline before closing.

## Rollback
Re-deploy the prior release; disable any fallback toggles enabled during mitigation. Reversible.
