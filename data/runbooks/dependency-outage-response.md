# Dependency-Outage Response

**Applies to:** a service degraded by a failing upstream/downstream dependency.

## Symptoms
- Errors or timeouts concentrated on calls to one dependency.
- The dependency's own health/status is degraded.

## Diagnosis
1. Identify the failing dependency from the error signatures and traces.
2. Confirm it is the dependency (not this service) that is unhealthy.
3. Check whether a circuit breaker / fallback exists for that call path.

## Remediation
- Enable the circuit breaker / fallback for the failing dependency and retry with backoff.
- Shed non-critical load that depends on it.
- Open a ticket with the dependency owner and track their incident.

## Rollback
Disable the circuit breaker / fallback once the dependency recovers. Reversible.
