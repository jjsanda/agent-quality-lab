# General Incident Response

**Applies to:** any incident without a more specific runbook.

## Steps
1. Acknowledge the alert and confirm the symptom in the relevant dashboard.
2. Establish a timeline: when did it start, what changed around then (deploys, config, traffic).
3. Gather evidence: recent error logs, the key metric for the symptom, and any owning runbook.
4. Form a single root-cause hypothesis and the smallest reversible mitigation that tests it.
5. Apply one change at a time and re-check the signal.
6. If unresolved within the SLA, escalate to the service owner and open an incident bridge.

## Safety
- Prefer reversible mitigations; record a rollback for every change.
- Never run a destructive or irreversible command as automated remediation.
