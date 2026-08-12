# TrainCapsule V3 migration report

## Scope

Migrate the V2 factory/bootstrap repository to the bounded V3 product and factory model while preserving historical authority, runtime evidence, candidate work, and rollback ability. Build the initial customer-local install-to-preflight product vertical; do not claim external or commercial validation.

## Actual base and safety

- Base: `main` at `6b480232fa92b069103da44c475bd17bcb3e6bd1`
- Rollback ref: `safety/traincapsule-v3-pre-migration-20260811T212024Z`
- V2 controller stopped and restart task disabled before tracked edits
- Baseline and runtime metadata: `V3_BASELINE_REPORT.md` and `V3_RUNTIME_SNAPSHOT_METADATA.json`

## Completed changes

- Installed the V3 source documents under `docs/source-of-truth/v3-2026-08-11/` without modifying the historical 9 August bundle.
- Replaced source precedence with separate normative and current-factual authority.
- Added a version-3 role-scoped context index that excludes career/acquisition material from routine work.
- Added deterministic V3 manifest generation and a fail-closed source-integrity gate.
- Added an external trusted-root human-approval policy; no repository fallback is permitted.
- Preserved the legacy source-manifest verification and extended the factory authority entrypoint to require both historical and V3 integrity.
- Added positive and adversarial integrity coverage for missing files, changed content, duplicate logical IDs, manifest self-hashing, parenthesized duplicates, stale authority, unresolved context, mixed fact/normative authority, and synthetic commercial completion.
- Added a separate `tcfactory.v3` domain package with the exact lane, work-kind, status, disposition, ownership, engineering-maturity, commercial-maturity, milestone, evidence, approval, and release vocabularies.
- Added strict-shape work items, bounded milestones, finite retry policy, disposition and legacy-map records, typed scheduler configuration, external evidence and human approval records, and explicit work-status transitions.
- Added an immutable candidate manifest that binds exact SHAs, packet/context/checkpoint digests, executor identity, stage and gate artifacts, findings, approvals, evidence receipts, and release decision.
- Added deterministic canonical JSON/digests, trusted evidence ceilings, signed external human-approval verification inputs, and 18 generated model-matching JSON schemas.
- Replaced unbounded V2 runtime policy with finite V3 factory, autonomy, scheduler, milestone, executor, external-evidence, and commercial-maturity configuration while retaining a safe read-only V2 compatibility projection.
- Generated the exact 109-item V3 roadmap and seven bounded milestone records from the authoritative backlog. Original dependency expressions are preserved and the resolved graph is checked for missing references and cycles.
- Implemented deterministic active-milestone scheduling with hard dependencies, lane/global WIP, native-before-duplication ordering, exact score components, stable tie-breaking, and externally signed founder overrides.
- Implemented a typed atomic V3 queue with per-status and per-lane views, duplicate prevention, interrupted-run isolation, and non-resuming V2 archive receipts.
- Implemented finite repeat-finding, value-redesign, and controller-restart recovery. Exhausted restart budgets write `HARD_STUCK` and `STOP` records with exact recovery instructions.
- Added a read-only `tcfactory v3-schedule --dry-run --explain` interface. It refuses non-dry-run use and emits a compact decision artifact scoped to the active milestone.

## Deviations

- Publishing is performed only to `main` because that is the current operator instruction. The repository's V3 factory release policy remains pull-request-first and direct-main-disabled for future autonomous work.
- The untracked ZIP/extracted review directory remains present but is not installed as an arbitrary archive.

## Phase A verification

- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Complete Pytest suite: pass
- Historical source authority: 20 files verified
- V3 source authority: 11 canonical files verified
- Git diff hygiene: pass

## Phase B verification

- Domain-model adversarial tests: 10 passed
- Complete Pytest suite: pass
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Generated V3 schemas: 10 exact matches
- Historical and V3 authority gates: pass
- Secret scan and Git diff hygiene: pass

## Phase C verification

- Focused scheduler, queue, recovery, configuration, roadmap, policy, and compatibility checks: 40 passed
- Complete Pytest suite: 430 passed
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Generated V3 schemas: 18 exact matches
- Authoritative V3 roadmap generation: 109 exact work items
- Historical and V3 authority gates: pass
- No-paid-usage gate: pass
- Secret scan and Git diff hygiene: pass

## Phase D implementation

- Added bounded, digest-bound V3 packets with fixed criteria/output/source limits, explicit decision contribution, non-goals, oracle, rollback, stop dispositions, deterministic task-kind templates, path/output consistency checks, and cache invalidation across work/source/context/compiler/base digests.
- Removed the T002 catalog special case, universal `**` write-scope broadening, forced GitHub push, automatic merge, numeric task-ID private-gate selection, renewable-session language, and work-until-done token/turn clearing.
- Added scoped V3 context manifests with per-source authority, relevance, digest, freshness, and role policy. Routine work cannot load career/acquisition context; stale current facts block only the affected work item.
- Added milestone-only completion decisions, deterministic-evidence-first evaluation, bounded proposal-only expansion, independent review requirements, trusted external receipts, human approvals, and controlled-fixture ceilings for M3-M6.
- Added the five terminal decision-value outcomes. Mechanical/maintenance work inherits milestone necessity; weak product outcomes stop or defer without appending work.
- Split finding, candidate, value, human, external, release, and recovery boundaries into small typed services. Advisory findings do not block and factory repair cannot alter normative, approval, receipt, private-gate, roadmap, or value authority.
- Added configuration validation/provenance and the read-only operator command surface for migration, configuration, lanes, milestones, work explanation, approvals, evidence, competitors, pilots, kill gates, product health, and V3 status.
- Added versioned digest-bound backend-neutral handoffs, peer artifact validation, atomic validated writes, same-root path containment, single-writer locks, redaction, safe subprocess environments, sequenced event records, corruption warnings, and separated API-equivalent estimates from actual subscription charges.
- Expanded generated model-matching schemas from 18 to 25.

## Phase D verification

- Focused planner, context, completion, value, risk, catalog, feature-adapter, durable-state, and operator checks: 71 passed
- Complete Pytest suite: 443 passed
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Generated V3 schemas: 25 exact matches
- Authoritative V3 roadmap generation: 109 exact work items
- Historical and V3 authority gates: pass
- No-paid-usage gate: pass
- Secret scan and Git diff hygiene: pass
- Manual read-only operator exercise: config validate/explain, status, lanes, milestones, work explain, kill-gates, and migrate dry-run passed

## Phase E implementation

- Added the backend-neutral `EngineeringAgentBackend` protocol and typed capability, request, session, handoff, result, usage, route-state, cancellation, and transcript-retention records.
- Added deterministic `FakeBackend` contract tests without any model/network use and a subscription-only `ClaudeBackend` adapter around the existing async stage runner.
- Moved credential decisions behind `ClaudeCredentialProvider`; factory-facing state exposes only `AUTHENTICATED`, `AUTH_EXPIRED`, `QUOTA_WAIT`, or `ROUTE_REFUSED`. Raw token values, account identifiers, token-file paths, controller-secret paths, and SDK environments are rejected or redacted from exportable records.
- Refactored structured read-only review through the backend contract for deterministic tests. Live Claude review now retains only redacted message-type counts, has a finite wall-time cancellation boundary, finite turns/cost estimate, explicit Bash prefixes, network denial, backend-neutral session references, and no raw SDK message serialization or subscription-unbounded branch.
- Upgraded checkpoints to schema-versioned digest envelopes, atomic previous generations, explicit previous-generation recovery, corrupt/incompatible quarantine, stale-candidate rejection, duplicate-active-work detection, and blocking failure semantics. V3 checkpoint state binds work item, lane, milestone, backend session reference, finite budgets, context/source digests, candidate SHA, approval state, and circuit-breaker reason.
- Expanded generated model-matching schemas from 25 to 30.

## Phase E verification

- Focused backend, redaction, structured-runner, and checkpoint recovery checks: 33 passed
- Complete Pytest suite: 456 passed
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Generated V3 schemas: 30 exact matches
- Historical/V3 authority, 109-item roadmap, no-paid-usage, secret scan, and Git diff hygiene: pass

## Phase F implementation

- Replaced the direct-main GitHub synchronization path with a strict pull-request release policy. `releaseMode` is `pull_request`, `directMainPush` is false, every auto-merge mode is false, and the retained compatibility helper now refuses all direct `main` pushes.
- Added exact candidate-branch verification, remote-main ancestry verification, release-branch fast-forward checks, full-SHA release refspecs, post-push remote-SHA verification, and unconditional force-push prohibition.
- Added idempotent draft pull-request create/update behavior. A non-draft existing PR is rejected, PR text and command failures are redacted, the observed PR head must match the candidate SHA, and release metadata binds the candidate ref/SHA, release branch/SHA, PR number/URL, draft state, disabled auto-merge state, required checks, and timestamp.
- Added exact required-workflow evaluation for the release SHA and PR head branch. Missing and in-progress workflows remain pending; a failed workflow fails closed; success requires every configured workflow to pass.
- Replaced the single self-hosted workflow with five least-privilege GitHub-hosted workflows for factory quality, product unit, product contract/journeys, security, and source-of-truth integrity. Each workflow has a finite timeout, concurrency cancellation, pinned actions, explicit test scope, no secret context, and retained evidence artifacts.
- Changed one-time GitHub setup so it verifies `origin/main` without pushing it and leaves configuration changes for the reviewed candidate flow.
- Preserved the operator's migration-only instruction to publish the completed overhaul directly to `main`; the autonomous V3 runtime remains PR-first and cannot perform that direct push.

## Phase F verification

- Focused release, exact-SHA, redaction, workflow, and setup checks: 22 passed
- Complete Pytest suite: 467 passed
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- YAML uniqueness: 84 files passed
- Generated V3 schemas: 30 exact matches
- V3 configuration validation: pass without mutation
- No GitHub branch, PR, merge, workflow run, or push was created during Phase F testing

## Phase G implementation

- Replaced the infinite launcher loop with one persistent finite supervisor. Short-lived controller exits receive exactly three restart opportunities with 15-second, 60-second, and 300-second backoff; the next exit writes the shared V3 `HARD_STUCK` record and durable `STOP`, then exits nonzero.
- Persisted the supervisor restart budget independently of a launcher process. The budget resets only after the configured 1,800-second healthy interval, so Windows recovery heartbeats and process restarts cannot renew the retry loop.
- Added a fail-closed startup preflight for the complete V3 configuration set, V3 source integrity, single-supervisor ownership, backend-neutral credential state, a source-digest/SHA-bound migration-complete marker, absence of `STOP`/`HARD_STUCK`, an empty running queue, and absence of quarantined corrupt checkpoints.
- Kept the migration-complete marker absent while later migration phases remain. The existing durable `STOP` and `PAUSE` cause the actual launcher to exit before credentials or a controller process are loaded.
- Removed Task Scheduler's 999-restart policy. The recovery heartbeat may relaunch the bounded supervisor, but persistent retry state and `HARD_STUCK` prevent a second unbounded loop.
- Rebuilt `Control-TrainCapsuleBuilder.ps1` and Windows task registration around `RepoPath`, `WslDistribution`, `FactoryRuntimePath`, and action parameters/environment configuration. No user, repository, or distribution is hardcoded; OAuth values are never requested or printed.
- Added portable status, pause, resume, recover, stop, schedule-dry-run, milestone-status, verify, logs, queue, GitHub, and start routing through the same redacting runtime script.
- Replaced the narrow status response with a truthful V3 operator snapshot: active milestone, current work item/lane, checkpoint retry budget, persistent restart budget, human/external blockers, candidate SHA, factory CI, product CI, and latest release PR.
- Added schema-versioned migration-marker and supervisor-state models, bringing generated V3 schemas from 30 to 32.

## Phase G verification

- Focused supervisor, control, status, release-compatibility, and configuration checks: 33 passed
- Complete Pytest suite: 471 passed
- Exact restart sequence and hard-stuck/stop writes: pass without sleep or model use
- Healthy-interval-only reset: pass at the configured 1,800 seconds
- Current stopped-launcher exercise: pass; `STOP` and `PAUSE` preserved, marker absent, controller not started
- PowerShell parser: both control and registration scripts pass
- Bash parser: launcher, systemd entrypoint, factory control, and status scripts pass
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Generated V3 schemas: 32 exact matches
- No model session, GitHub mutation, Windows task change, or paid usage occurred

## Phase H implementation

- Replaced open-ended global and role instructions with one-work-item V3 contracts bound to finite packet, path, turn, token, cost, retry, and elapsed-time limits.
- Enforced the authoritative packet ceilings of 12 acceptance criteria and 8 outputs, one mutating candidate owner, acyclic dependency handling, finite checkpoints, and no session renewal or automatic roadmap mutation.
- Made native/bundled/agent comparison mandatory and added explicit `NATIVE_WORKFLOW_SUFFICIENT`, `NO_INCREMENTAL_DECISION_VALUE`, `UNKNOWN`, `WAITING_EXTERNAL`, and `WAITING_HUMAN` behavior.
- Added the V3 concrete finding format with reproducible fingerprints and a limit of eight findings per review.
- Added specialist contracts for native/substitute review, bounded commercial experiment preparation, human approval packets, wedge review, and milestone audit.
- Removed acquisition/career influence from routine planning and prohibited fabricated commercial evidence, external receipts, approvals, benchmarks, integrations, and release authority.
- Replaced all active-role open ceilings with explicit limits of at most 64 turns, 96,000 task tokens, and a 12.0 API-equivalent estimate. The stopped runtime was not invoked.

## Phase H verification

- Focused prompt, planner, Claude-feature, dependency-graph, and model-routing checks: 16 passed
- Complete Pytest suite: 478 passed
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Credential scan: pass
- All active role prompts exist and all active roles have finite turn, token, and estimate ceilings
- No model session, network mutation, GitHub mutation, runtime restart, or paid usage occurred

## Phase I implementation

- Preserved the complete 79,523-byte V2 feature ledger byte-for-byte at `factory/roadmap/legacy_feature_ledger.yaml`; its snapshot-bound digest remains `sha256:ab5d10c6718d3a9fdf53dd78cf0c387e995cd1723cf10b76fb53e14af559c994`.
- Added an ordered, typed mapping for exactly T001 through T124 with original status, outcome, packet, preserved evidence references, explicit V3 disposition, bounded V3 targets, and reason.
- Preserved the observed status distribution exactly: 1 passed, 1 paused, 2 external-wait, and 120 blocked. T002 remains FACTORY history with no mapped work item and cannot be automatically resumed.
- Mapped 88 explicitly represented concepts to existing bounded V3 work, preserved 7 source/factory items as FACTORY history, and marked 29 broad or unselected designs DEFERRED_DESIGN. No title-similarity inference activates work.
- Added deterministic generation and validation. Every mapping target must exist in the authoritative 109-item V3 roadmap; multiple legacy concepts may map to one bounded V3 item, but no V3 dependency contains a legacy task ID.
- Added exact `tcfactory migrate-roadmap --from-v2 --dry-run` behavior plus a reviewed real apply path. Apply requires local-write acknowledgement, never invokes a model, and is idempotent.
- Copied the exact stopped V2 queue into `factory/state/v3-queue/archive/v2/v2-20260811T212024Z-885df1dd93b8` with `autoResume: false`, while retaining the original three files byte-for-byte. The tracked archive receipt binds the source, copied files, manifest, STOP, PAUSE, and all empty V3 state directories.
- Made startup fail closed unless the legacy ledger archive, mapping, V3 targets, and queue archive receipt all verify.
- Marked V3-MIG-010 through V3-MIG-015 passed-engineering in the deterministic roadmap generator. Human work V3-MIG-016 remains WAITING_HUMAN.

## Phase I verification

- Dedicated legacy mapping, queue, and startup checks: 15 passed
- Complete Pytest suite: 485 passed
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Exact V3 roadmap generation: 109 work items
- Exact legacy generation: 124 records
- Generated V3 schemas: 32 exact matches
- YAML uniqueness: 88 files passed
- Source authority, V3 configuration, credential scan, and no-paid-usage gates: pass
- Queue archive apply and second idempotent apply: pass; originals retained, no auto-resume, STOP/PAUSE preserved
- No model session, network mutation, GitHub mutation, runtime restart, Windows task change, or paid usage occurred

## Pending

Qualified human review, external/customer evidence, real GPU evidence, controller observation, and
future M1/M2 roadmap work remain outstanding. These are intentionally not converted into
engineering or commercial passes.

## Phase J implementation

- Added separate core, PyTorch ingest, qualification, and CLI product packages. Product records do
  not import factory enums or factory state.
- Added strict version-1 workload/environment identities, evidence artifacts, native findings,
  incident cases, completeness reports, and eligibility decisions. Technical result and
  operational recommendation remain separate dimensions.
- Added canonical UTF-8/LF JSON and SHA-256 identity plus an independent stdlib reference oracle.
  Explicit `createdAt` is retained in records but excluded from identity material; no clock is read
  while computing identity.
- Added deterministic environment-variable redaction and explicit weak/customer-attested identity
  behavior.
- Added a case-isolated customer-local CAS with raw hash verification, bounded files/counts,
  duplicate/collision checks, atomic metadata, and traversal/symlink/cross-case protections.
- Added the bounded PyTorch Flight Recorder `1.0` adapter and controlled fixtures. Unsupported
  versions fail explicitly, raw evidence is hashed before parsing, unknown fields/digests remain
  available, missing ranks remain missing, and native observations do not become inferred root
  causes.
- Added exact evidence-completeness states, machine-readable native baseline, and deterministic
  eligibility/economic preflight. Unknown costs stay unknown and native sufficiency is a valid stop.
- Added the exact offline-first CLI through preflight with canonical `--json`, explicit local paths,
  useful errors, and stable exit codes 0/2/3/4/5.
- Added a controlled case-init-to-preflight journey and adversarial cases for missing/corrupted
  evidence, native sufficiency, unsupported versions, policy blocks, unknowns, expiry, and malicious
  symlinks/paths.
- Replaced product workflow placeholders with exact product unit, schema, contract, CLI, and journey
  scopes.

## Phase J verification

- Product scope: 41 passed
- Complete repository suite: 527 passed
- Ruff: pass
- Strict Pyright: 0 errors, 0 warnings
- Ten product schemas: generated and exact
- Wheel build: pass; factory and all four product packages plus both entry points are present
- Fresh wheel install: pass; installed `doctor`, identity, and importer commands passed
- Model/GitHub/runtime/paid use: none; the public package registry was used only for the clean install

## Legacy mapping summary

The complete ordered mapping is `factory/roadmap/migrations/v2_to_v3.yaml`: 124 records preserving
1 passed, 1 paused, 2 external-wait, and 120 blocked states. Dispositions are 88 mapped to bounded
V3 work, 29 deferred designs, and 7 factory-history records. T002 remains paused factory history,
has no V3 dependency edge, and cannot auto-resume. The original V2 ledger and queue evidence remain
byte-for-byte available.

## Unresolved limitations and deferred scope

- No real GPU test, private customer trace, customer archive, independent operator run, or paid
  engagement occurred.
- No baseline/candidate runner, reduction engine, scale-emulation claim, qualification execution,
  customer report viewer, or commercial pack release is implemented.
- The controlled fixture proves software behavior only. It does not prove customer value, product
  advantage, incident root cause, or economic ROI.
- V3-MIG-016 human review remains `WAITING_HUMAN`; external and commercial maturity are unchanged.
- The operator requires publishing this migration to `main`, so no draft migration PR is opened.
  Future autonomous release policy remains draft-PR-first and direct-main-disabled.

## Final acceptance and recovery state

- Full quality and secret gates pass with 527 tests and strict type checking at 0 errors/0 warnings.
- Both source authorities, all generated schemas, the 109-item roadmap, the 124-record legacy map,
  configuration validation, no-paid-usage gate, and migration dry-run pass.
- Detached rollback rehearsal at the fixed safety SHA passes the 394-test baseline and historical
  authority; its disposable worktree was removed.
- Windows task `TrainCapsule Lights-Out Autopilot` is present but disabled. No `tcfactory` or launcher
  process is running. Durable `STOP` and `PAUSE` remain present.
- The queue remains truthful: T001 is the only done record, T002 has its preserved paused record and
  pause metadata, and no pending/running/failed/blocked record exists.

<!-- BEGIN GENERATED FILE INVENTORY -->
## Complete tracked file inventory

Compared with `6b480232fa92b069103da44c475bd17bcb3e6bd1`: **227 paths**.

| Change | Path |
|---|---|
| `A` | `.github/workflows/factory-quality.yml` |
| `D` | `.github/workflows/factory-smoke.yml` |
| `A` | `.github/workflows/product-contract.yml` |
| `A` | `.github/workflows/product-unit.yml` |
| `A` | `.github/workflows/security.yml` |
| `A` | `.github/workflows/source-of-truth-integrity.yml` |
| `M` | `Control-TrainCapsuleBuilder.ps1` |
| `M` | `README.md` |
| `M` | `SOURCE_PRECEDENCE.md` |
| `M` | `config/autonomy.yaml` |
| `A` | `config/commercial_maturity.yaml` |
| `A` | `config/executors.yaml` |
| `A` | `config/external_evidence.yaml` |
| `M` | `config/factory.yaml` |
| `M` | `config/github.yaml` |
| `A` | `config/human_approval.yaml` |
| `A` | `config/milestones.yaml` |
| `M` | `config/roles.yaml` |
| `A` | `config/scheduler.yaml` |
| `M` | `docs/CONTEXT_INDEX.yaml` |
| `A` | `docs/migrations/V3_BASELINE_REPORT.md` |
| `A` | `docs/migrations/V3_CODEX_EXECUTION_STATE.md` |
| `A` | `docs/migrations/V3_LEGACY_QUEUE_ARCHIVE_METADATA.json` |
| `A` | `docs/migrations/V3_MIGRATION_REPORT.md` |
| `A` | `docs/migrations/V3_ROLLBACK.md` |
| `A` | `docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json` |
| `A` | `docs/migrations/V3_TEST_MATRIX.md` |
| `A` | `docs/product/PREFLIGHT_QUICKSTART.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/06_COMMERCIAL_MODEL_AND_GTM_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/13_SOURCE_REGISTER_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json` |
| `A` | `docs/source-of-truth/v3-2026-08-11/README.md` |
| `A` | `docs/source-of-truth/v3-2026-08-11/REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md` |
| `A` | `examples/product/README.md` |
| `A` | `examples/product/environment-identity-input.json` |
| `A` | `examples/product/flight-recorder/supported/metadata.json` |
| `A` | `examples/product/flight-recorder/supported/rank-0.json` |
| `A` | `examples/product/flight-recorder/supported/rank-1.json` |
| `A` | `examples/product/flight-recorder/unsupported/metadata.json` |
| `A` | `examples/product/flight-recorder/unsupported/rank-0.json` |
| `A` | `examples/product/workload-identity-input.json` |
| `A` | `factory/roadmap/dispositions.yaml` |
| `A` | `factory/roadmap/legacy_feature_ledger.yaml` |
| `A` | `factory/roadmap/migrations/v2_to_v3.yaml` |
| `A` | `factory/roadmap/milestones.yaml` |
| `A` | `factory/roadmap/work_items.yaml` |
| `A` | `packages/traincapsule-cli/src/traincapsule_cli/__init__.py` |
| `A` | `packages/traincapsule-cli/src/traincapsule_cli/cli.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/__init__.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/base.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/evidence.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/identity.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/models.py` |
| `A` | `packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/__init__.py` |
| `A` | `packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/importer.py` |
| `A` | `packages/traincapsule-qualify/src/traincapsule_qualify/__init__.py` |
| `A` | `packages/traincapsule-qualify/src/traincapsule_qualify/models.py` |
| `A` | `packages/traincapsule-qualify/src/traincapsule_qualify/qualify.py` |
| `M` | `prompts/adversary.md` |
| `M` | `prompts/audit.md` |
| `M` | `prompts/autonomous_planner.md` |
| `M` | `prompts/bootstrap_integrator_windows11.md` |
| `M` | `prompts/builder.md` |
| `A` | `prompts/commercial_experiment.md` |
| `M` | `prompts/factory_repair.md` |
| `M` | `prompts/global.md` |
| `A` | `prompts/human_approval_packet.md` |
| `M` | `prompts/integration_scout.md` |
| `A` | `prompts/milestone_auditor.md` |
| `A` | `prompts/native_substitute_reviewer.md` |
| `M` | `prompts/negative_control_engineer.md` |
| `M` | `prompts/performance.md` |
| `M` | `prompts/private_gate_author.md` |
| `M` | `prompts/recovery.md` |
| `M` | `prompts/release.md` |
| `M` | `prompts/research.md` |
| `M` | `prompts/security.md` |
| `M` | `prompts/specification.md` |
| `M` | `prompts/task_packet_planner.md` |
| `M` | `prompts/value_adversary.md` |
| `M` | `prompts/value_validator.md` |
| `A` | `prompts/wedge_reviewer.md` |
| `M` | `pyproject.toml` |
| `A` | `schemas/factory/v3/agent-capabilities.schema.json` |
| `A` | `schemas/factory/v3/agent-run-result.schema.json` |
| `A` | `schemas/factory/v3/agent-task-request.schema.json` |
| `A` | `schemas/factory/v3/autonomy-config.schema.json` |
| `A` | `schemas/factory/v3/candidate-manifest.schema.json` |
| `A` | `schemas/factory/v3/checkpoint.schema.json` |
| `A` | `schemas/factory/v3/commercial-maturity-config.schema.json` |
| `A` | `schemas/factory/v3/context-manifest.schema.json` |
| `A` | `schemas/factory/v3/decision-value.schema.json` |
| `A` | `schemas/factory/v3/dispositions.schema.json` |
| `A` | `schemas/factory/v3/executors-config.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-config.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-receipt.schema.json` |
| `A` | `schemas/factory/v3/factory-config.schema.json` |
| `A` | `schemas/factory/v3/finding-counter.schema.json` |
| `A` | `schemas/factory/v3/finding.schema.json` |
| `A` | `schemas/factory/v3/handoff.schema.json` |
| `A` | `schemas/factory/v3/hard-stuck.schema.json` |
| `A` | `schemas/factory/v3/human-approval.schema.json` |
| `A` | `schemas/factory/v3/legacy-migration.schema.json` |
| `A` | `schemas/factory/v3/migration-complete-marker.schema.json` |
| `A` | `schemas/factory/v3/milestone-completion.schema.json` |
| `A` | `schemas/factory/v3/milestone-policy-config.schema.json` |
| `A` | `schemas/factory/v3/milestones.schema.json` |
| `A` | `schemas/factory/v3/release-candidate.schema.json` |
| `A` | `schemas/factory/v3/retry-policy.schema.json` |
| `A` | `schemas/factory/v3/scheduler.schema.json` |
| `A` | `schemas/factory/v3/supervisor-state.schema.json` |
| `A` | `schemas/factory/v3/task-packet.schema.json` |
| `A` | `schemas/factory/v3/usage-state.schema.json` |
| `A` | `schemas/factory/v3/work-item-v3.schema.json` |
| `A` | `schemas/factory/v3/work-items.schema.json` |
| `A` | `schemas/product/eligibility-decision.schema.json` |
| `A` | `schemas/product/environment-identity.schema.json` |
| `A` | `schemas/product/evidence-artifact.schema.json` |
| `A` | `schemas/product/evidence-completeness-report.schema.json` |
| `A` | `schemas/product/flight-recorder-import.schema.json` |
| `A` | `schemas/product/incident-case.schema.json` |
| `A` | `schemas/product/native-baseline.schema.json` |
| `A` | `schemas/product/native-finding.schema.json` |
| `A` | `schemas/product/preflight-inputs.schema.json` |
| `A` | `schemas/product/workload-identity.schema.json` |
| `M` | `scripts/configure_github.sh` |
| `M` | `scripts/factory_control.sh` |
| `M` | `scripts/factory_status.sh` |
| `M` | `scripts/gates/no_paid_usage.py` |
| `A` | `scripts/gates/source_of_truth_integrity.py` |
| `A` | `scripts/generate_product_schemas.py` |
| `A` | `scripts/generate_v3_legacy_migration.py` |
| `A` | `scripts/generate_v3_manifest.py` |
| `A` | `scripts/generate_v3_roadmap.py` |
| `A` | `scripts/generate_v3_schemas.py` |
| `M` | `scripts/register_windows_autostart.ps1` |
| `M` | `scripts/systemd_entrypoint.sh` |
| `A` | `scripts/update_v3_migration_inventory.py` |
| `M` | `scripts/verify_factory_authority.sh` |
| `M` | `scripts/windows_task_entrypoint.sh` |
| `M` | `tcfactory/autopilot.py` |
| `A` | `tcfactory/backends/__init__.py` |
| `A` | `tcfactory/backends/base.py` |
| `A` | `tcfactory/backends/claude.py` |
| `A` | `tcfactory/backends/fake.py` |
| `M` | `tcfactory/catalog.py` |
| `M` | `tcfactory/checkpoints.py` |
| `M` | `tcfactory/claude_features.py` |
| `M` | `tcfactory/cli.py` |
| `M` | `tcfactory/completion.py` |
| `M` | `tcfactory/config.py` |
| `M` | `tcfactory/context.py` |
| `M` | `tcfactory/github_sync.py` |
| `M` | `tcfactory/handoffs.py` |
| `M` | `tcfactory/ledger.py` |
| `M` | `tcfactory/models.py` |
| `M` | `tcfactory/observability.py` |
| `M` | `tcfactory/peer_messaging.py` |
| `M` | `tcfactory/pipeline.py` |
| `M` | `tcfactory/planner.py` |
| `M` | `tcfactory/prompts.py` |
| `M` | `tcfactory/provenance.py` |
| `M` | `tcfactory/quota.py` |
| `M` | `tcfactory/risk.py` |
| `A` | `tcfactory/runtime_status.py` |
| `M` | `tcfactory/structured_runner.py` |
| `A` | `tcfactory/supervisor.py` |
| `M` | `tcfactory/usage.py` |
| `M` | `tcfactory/util.py` |
| `A` | `tcfactory/v3/__init__.py` |
| `A` | `tcfactory/v3/approvals.py` |
| `A` | `tcfactory/v3/base.py` |
| `A` | `tcfactory/v3/candidate_manifest.py` |
| `A` | `tcfactory/v3/configuration.py` |
| `A` | `tcfactory/v3/dispositions.py` |
| `A` | `tcfactory/v3/enums.py` |
| `A` | `tcfactory/v3/external_evidence.py` |
| `A` | `tcfactory/v3/maturity.py` |
| `A` | `tcfactory/v3/migrations.py` |
| `A` | `tcfactory/v3/milestones.py` |
| `A` | `tcfactory/v3/pipeline_services.py` |
| `A` | `tcfactory/v3/planning.py` |
| `A` | `tcfactory/v3/queue.py` |
| `A` | `tcfactory/v3/recovery.py` |
| `A` | `tcfactory/v3/retry_policy.py` |
| `A` | `tcfactory/v3/scheduler.py` |
| `A` | `tcfactory/v3/work_items.py` |
| `M` | `tcfactory/value.py` |
| `A` | `tests/product/__init__.py` |
| `A` | `tests/product/reference_identity.py` |
| `A` | `tests/product/test_cli.py` |
| `A` | `tests/product/test_evidence_store.py` |
| `A` | `tests/product/test_flight_recorder_importer.py` |
| `A` | `tests/product/test_identity.py` |
| `A` | `tests/product/test_install_to_preflight_journey.py` |
| `A` | `tests/product/test_product_schemas.py` |
| `A` | `tests/product/test_qualification.py` |
| `M` | `tests/test_autonomy_freedom_policy.py` |
| `M` | `tests/test_autopilot_respec_evidence.py` |
| `M` | `tests/test_catalog.py` |
| `M` | `tests/test_claude_features.py` |
| `M` | `tests/test_claude_led_nodes.py` |
| `M` | `tests/test_claude_only_policy.py` |
| `M` | `tests/test_completion.py` |
| `M` | `tests/test_control_scripts.py` |
| `M` | `tests/test_github_policy.py` |
| `M` | `tests/test_github_setup_script.py` |
| `M` | `tests/test_risk_routing.py` |
| `A` | `tests/test_source_of_truth_integrity.py` |
| `A` | `tests/test_v3_backends_and_checkpoints.py` |
| `A` | `tests/test_v3_config_and_roadmap.py` |
| `A` | `tests/test_v3_domain_models.py` |
| `A` | `tests/test_v3_github_workflows.py` |
| `A` | `tests/test_v3_legacy_migration.py` |
| `A` | `tests/test_v3_planning_context_and_support.py` |
| `A` | `tests/test_v3_prompt_contracts.py` |
| `A` | `tests/test_v3_queue.py` |
| `A` | `tests/test_v3_scheduler_and_recovery.py` |
| `A` | `tests/test_v3_supervisor_and_status.py` |
| `M` | `tests/test_windows_autostart_scripts.py` |
<!-- END GENERATED FILE INVENTORY -->
