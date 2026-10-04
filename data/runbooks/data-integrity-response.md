# Data-Integrity Response

**Applies to:** suspected data corruption, inconsistency, or pipeline drift.

## Symptoms
- Records that fail validation or disagree across stores.
- A pipeline producing inconsistent or stale outputs.

## Diagnosis
1. Quantify the blast radius: which records/partitions are affected since when.
2. Identify the first bad batch and correlate with a deploy or schema change.
3. Confirm a consistent checkpoint exists to reconcile from.

## Remediation
- Pause the affected pipeline to stop propagation.
- Reconcile from the last consistent checkpoint; **require human approval** before any write that mutates production data, and verify on a sample first.
- Re-enable the pipeline once validation passes.

## Rollback
Resume from the paused state; restore from the checkpoint/backup if a write was applied. Any data mutation here is gated behind explicit human approval and a verified backup.
