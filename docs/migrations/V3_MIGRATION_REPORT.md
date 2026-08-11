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

## Pending

Completion/context/value behavior, backend adapters, legacy mappings, product code, release rehearsal, and final acceptance remain to be implemented and verified in later phases.
