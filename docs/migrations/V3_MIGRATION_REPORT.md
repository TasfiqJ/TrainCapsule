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

## Pending

Legacy mappings, product code, release rehearsal, and final acceptance remain to be implemented and verified in later phases.
