# Deploy Rollback

**Applies to:** an incident correlated with a recent deployment.

## Symptoms
- Metrics degrade sharply at a deploy boundary.
- New error signatures appear that match the changed code paths.

## Diagnosis
1. Confirm the timeline: did the regression begin exactly at the rollout?
2. Identify the previous known-good release.
3. Check for stateful migrations that would complicate a rollback.

## Remediation
- Roll the service back to the previous known-good release.
- Re-check the affected metrics return to baseline.
- File a follow-up to root-cause the regression before re-deploying.

## Rollback
This *is* the rollback procedure; if it does not help, restore traffic to the prior version and escalate to the release owner. No data migration is reversed here.
