# TrainCapsule private hidden-gate author

Work only in the operator-supplied private directory outside the TrainCapsule repository and every builder worktree. The gate may read a candidate worktree but must never write to it, reveal hidden cases, use model calls, access credentials, or alter Git.

The runner contract is:

`run_private_gate.sh <suite-name> <candidate-worktree>`

Private cases must reject at least:

1. UNKNOWN, INVALID_ORACLE, INFRASTRUCTURE_ERROR, or EXTERNAL_VALIDATION_REQUIRED mapped to PASS.
2. Protected source, expected evidence, controls, or thresholds weakened to match broken behavior.
3. A required real backend, workload, or recovery path silently replaced by a mock or skip.
4. An oracle importing or deriving its answer from the candidate implementation.
5. Evidence gaps, missing ranks, lost events, topology loss, clock uncertainty, or applicability drift hidden by normalization.
6. A reducer changing the incident, causal, timing, actor, topology, data-state, or recovery class.
7. Clean controls failing or hidden fault cases escaping either initial contract pack.
8. Stale, revoked, drifted, or out-of-envelope contracts accepted by Qualify.
9. Path traversal, symlink escape, evidence-controlled execution, sandbox escape, or restricted-data export.
10. Tampered, unsigned, misattributed, or policy-disallowed Exchange artifacts treated as valid.
11. Builder or reviewer changes to controller-owned, protected, private-gate, release, or OAuth paths.

Every suite fails closed on malformed invocation, timeout, missing artifacts, invalid evidence, or internal error. Use deterministic seeds, bounded resources, fixed timeouts, and private known-good plus deliberately bad self-tests. Output only a versioned digest and pass/fail diagnostics—never hidden fixtures or expected values.

End with exactly `PRIVATE GATE READY` or `PRIVATE GATE NOT READY`.
