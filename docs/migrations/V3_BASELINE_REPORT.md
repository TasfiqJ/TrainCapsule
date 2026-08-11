# TrainCapsule V3 baseline report

## Repository baseline

- Repository: `/home/jasim/projects/traincapsule`
- Remote: `https://github.com/TasfiqJ/TrainCapsule.git`
- Branch: `main`
- Actual migration base: `6b480232fa92b069103da44c475bd17bcb3e6bd1`
- Upstream: `origin/main` at the same SHA after a fresh fetch
- Divergence: zero commits ahead and zero behind
- Tracked worktree changes before migration: none
- Untracked inputs: the supplied V3 ZIP, its Windows metadata stream file, and its extracted review directory
- Safety ref: `safety/traincapsule-v3-pre-migration-20260811T212024Z`

The V3 audit reviewed `c31caefaeed7e605f6ef304fae6fcfe708a163b9`. That commit is an ancestor of the actual migration base. The only intervening commit is `6b48023 update roadmap`, which changes `factory/feature_ledger.yaml` from T002 `queued` to `paused` and updates its timestamp. No audited product or controller source changed between those SHAs.

## Controller and runtime baseline

- Windows task `TrainCapsule Lights-Out Autopilot`: disabled.
- V2 controller: stopped.
- V2 single-instance lock: released.
- `PAUSE` and `STOP` controls: present.
- Self-hosted GitHub Actions runner: left running; it is independent of the factory controller.
- Queue: T001 done, T002 paused, nothing pending/running/failed/blocked in the queue directories.
- V2 roadmap: 1 passed, 1 paused, 120 blocked, 2 external-wait; no next task.
- V2 autonomy still has unlimited semantics (`max_respecifications_per_task: 0`, `max_completion_expansions: 0`, and `value_redesign_limit: 0`) and direct automatic merge enabled. These are migration targets, not accepted V3 behavior.
- Runtime state, worktrees, candidate branches, recovery records, logs, and evidence were not deleted or rewritten.

Exact non-secret hashes and inventory counts are recorded in `docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json`.

## Existing CI/test baseline

All commands ran inside Ubuntu 22.04 against the exact migration base:

| Check | Result |
|---|---|
| `uv sync --extra dev --frozen` | pass |
| YAML duplicate/syntax validation | 71 files, pass |
| generated task schema versus checked-in schema | identical |
| DEMO-001, T001, and T002 packet validation | pass |
| catalog consistency | 122 entries, pass |
| Ruff | pass |
| strict Pyright | 0 errors, 0 warnings |
| Pytest | 394 passed in 17.59 seconds |
| secret scan | pass |
| factory source authority | 20 historical files verified |
| no-paid-usage gate | pass |
| self-repair scope gate | pass |

An earlier capture attempt invoked the commands from Windows instead of WSL and produced environment-only failures (`uv` absent and Git safe-directory mismatch). Those results are invalid and are not classified as repository failures. The WSL rerun above is the authoritative baseline.

## Baseline deviations affecting migration

- Current user instruction requires all eventual publishing to `main`; the bundle's migration-branch and draft-PR instructions are obsolete for this execution. Product/factory V3 release defaults will still be implemented as pull-request mode with direct-main release disabled.
- The supplied ZIP and extracted review directory are inside the repository root but remain untracked and will not be committed.
- Human approval for V3 source migration and any external release is not fabricated by this migration. M0 remains `WAITING_HUMAN` for that evidence even when engineering gates pass.
- No GPU or customer evidence was available or claimed at baseline.
