# TrainCapsule V3 execution state

- Migration base: `6b480232fa92b069103da44c475bd17bcb3e6bd1`
- Working/publication branch: `main` only
- Safety ref: `safety/traincapsule-v3-pre-migration-20260811T212024Z`
- Owner deviations: zero-human execution and exact-SHA main-only publication; non-main pushes and
  pull-request dependencies are forbidden
- External truth: GPU, customer, operator, payment, repeat-use, and commercial-support facts remain
  UNKNOWN or `WAITING_EXTERNAL`

## Historical accepted implementation

`f1fd8077fee001fa6751aa86b26f341f04d0d150` remains the historical implementation-acceptance SHA.
The eight run identifiers recorded in `V3_TEST_MATRIX.md` apply only to that SHA. They are not proof
for a later repair or handoff commit.

## Current finalization state

The implementation tree is frozen and all five M0 records are `FINAL`/`PASS`. They bind 663 active
implementation files with the mode-aware, nonrecursive SHA-256
`8a2f80ae17cfe2dbcf45ea296bc7c984901ca2a744809ee4151569203e66db6b`. The combined evidence-set
digest reported by the finalizer is
`7fda41fc90b708bb21cf09d3e3d9fe36f3b3d954b69d7d9547dfe9936c9d06f1`.

The exact commands completed successfully:

```text
.venv/bin/python scripts/finalize_v3_m0_evidence.py
scripts/gates/full_quality.sh
.venv/bin/python -m pytest
```

The finalizer records exact allowlisted argv, transcript-derived exit/result/count, failure
attribution, transcript paths and SHA-256 digests, active authority digests, and a mode-aware,
nonrecursive implementation-tree digest. Before writing `V3-MIG-020`, it runs
`scripts/gates/full_quality.sh --pre-evidence`: the complete acceptance suite without the necessarily
pending final evidence gate. It then binds `V3-MIG-020` only to `V3-MIG-016` through
`V3-MIG-019`; completion never cites itself. Normal `full_quality.sh` subsequently validates the
final evidence and reruns complete acceptance. The independent full-suite run completed with 599
tests passing; Ruff and strict Pyright were clean; all generators, migration checks, no-paid-usage
checks, and the offline wheel build passed. The installed root-owned private-gate health probe also
passed without minting a receipt.

The publication commit and hosted run identifiers are intentionally not predeclared here. The
resulting commit must independently pass every required hosted workflow at its exact SHA and the
actual clean-candidate private gate. Until those publication checks are recorded, the controller
remains stopped and no current hosted-release acceptance claim exists.

## Rollback

Keep the controller stopped and preserve runtime files. Compare tracked changes with
`safety/traincapsule-v3-pre-migration-20260811T212024Z`. After publication, use ordinary `git revert`
commits on `main`; never force-push or rewrite published history. T002 remains preserved and paused.

The historical acceptance SHA and its hosted run identifiers remain immutable historical evidence.
They must never be copied forward as proof for the implementation currently being finalized.
