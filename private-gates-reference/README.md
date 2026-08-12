# Private gate interface reference

This directory may document stable public inputs, outputs, and result schemas for private gates. It must not contain hidden cases, expected evidence, gate implementations, release credentials, or bypass instructions.

Private gate implementations live outside the repository and outside builder-visible worktrees.

The V3 controller expects a root-owned, non-group/world-writable installation at
`/var/lib/traincapsule-factory/private-gates/` containing executable
`run_private_gate.sh` and `trusted-public-key.pem` (Ed25519). Startup fails closed when either
file, its ownership/mode, or the key type is invalid.

For suite `full-release`, the controller supplies the exact candidate worktree as the second
argument and sets `TCF_TASK_ID`, `TCF_RUN_ID`, `TCF_CANDIDATE_SHA`,
`TCF_CANDIDATE_WORKTREE`, `TCF_PRIVATE_GATE_RECEIPT`, and
`TCF_PRIVATE_GATE_SIGNATURE`. The runner writes the receipt and detached Ed25519 signature to
the two requested output paths.

The receipt must validate against `schemas/factory/v3/private-gate-receipt.schema.json` and bind
the exact candidate SHA, work-item ID, complete ordered release scope, runner digest and semantic
version, captured result digest, issue/expiry time (no more than 24 hours), decision, algorithm,
and key ID. The controller verifies the exact signed bytes and rejects missing, stale, substituted,
incomplete, or mismatched evidence before main publication.
