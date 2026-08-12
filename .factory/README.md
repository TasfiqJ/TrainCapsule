# V3 factory state

The active controller is V3-only. The historical T001–T124 ledger and V2 queue are
preserved evidence; they are never scheduled or mutated by `tcfactory start`, status,
verification, explanation, or recovery commands.

All mutable V3 state resolves from the `localStateRootEnvironmentVariable` declared in
`config/factory.yaml` (`TCF_RUNTIME_ROOT` in the current configuration). When the variable is
unset, the default is `factory/state`. The controller, queue/status commands, checkpoints,
supervisor, milestone decisions, publication receipts, STOP/PAUSE controls, and recovery all
use that same resolved root.

Important runtime directories are `v3-queue/`, `pipelines/`, `scheduler-decisions/`,
`milestone-evidence/`, `milestone-decisions/`, `machine-policy-receipts/`, and `quarantine/`.
Queue claims use an OS-backed per-item lock plus a durable lease and transition journal.
Controller restart recovery moves interrupted RUNNING work through a checkpoint-bound handoff,
consumes finite plan/repair/restart budgets, and preserves repeated-finding fingerprints.

Milestone completion is evidence-driven. Per-item evidence and the owner-directive digest are
bound into a completion receipt. A write-ahead transaction makes the decision and active
milestone state replayable after a crash. Roadmap expansion remains proposal-only.

Startup and exact-SHA main publication fail closed unless the trusted private-gate installation
and a fresh candidate-bound signed receipt satisfy the contract documented in
`private-gates-reference/README.md`.
