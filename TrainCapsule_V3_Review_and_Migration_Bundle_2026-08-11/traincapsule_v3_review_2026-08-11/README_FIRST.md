# TrainCapsule V3 Review and Replacement Bundle

**Prepared:** 11 August 2026  
**Repository reviewed:** `TasfiqJ/TrainCapsule`  
**Audited baseline:** `main` at commit `c31caefaeed7e605f6ef304fae6fcfe708a163b9`  
**Repository state at that commit:** factory/bootstrap implementation; no substantive TrainCapsule product runtime yet  
**Repository changes made by this review:** none

## Bottom-line decision

Continue the company, but do not continue the current plan or autonomous loop unchanged.

The product should enter the market as:

> **Failure-derived change qualification for private distributed-training workloads.**

The first serious paid offer should be:

> **Incident-to-Change Qualification Pilot** — convert one costly historical or active distributed-training failure into a customer-local release gate for one real upcoming PyTorch, CUDA, NCCL, driver, checkpoint, GPU, topology, scheduler, or cloud change.

The long-term trust architecture remains valuable. The current execution strategy does not. It is optimized for completing a 124-task repository, not for proving a repeatable business.


## Fastest way to use this bundle

- Read `REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md` for the verified repository diagnosis and exact file-by-file changes.
- Read `TRAINCAPSULE_V3_MASTER_PLAN.md` for one consolidated product, technical, trust, commercial, factory, and roadmap document.
- Give `CODEX_MASTER_MIGRATION_PROMPT.md` and the complete extracted bundle to Codex for the controlled repository migration.
- Install `14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md` as the ongoing Claude Code operating prompt after the V3 migration.
- Use `examples/` as target schemas/configuration templates; reconcile them with the live code rather than copying blindly.

## Immediate actions

1. Pause the current autopilot before it performs more work on `T002`.
2. Preserve the existing `final-2026-08-09` bundle as immutable history.
3. Create a new source-of-truth bundle rather than editing the old locked bundle in place.
4. Mark the naming/trademark task as `DEFERRED_NON_BLOCKING`; continue using TrainCapsule as a provisional codename.
5. Replace the serial 124-task graph with four parallel lanes:
   - product/commercial slice;
   - market evidence;
   - native/competitor baseline;
   - trust validation.
6. Add hard retry, re-specification, self-repair, task-size, context, and roadmap-expansion limits.
7. Require qualified human approval before any external or commercial use of trust-critical code or a commercial incident pack.
8. Build only the first credible end-to-end qualification slice before broad federation, exchange, generic reduction, a second commercial pack, or a hosted platform.
9. Treat a result that merely duplicates native tooling as a product failure, even when the implementation is technically correct.
10. Run the migration through a branch and pull request. Do not let the current factory rewrite its own governing rules autonomously.

## Reading order

1. `REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md`
2. `00_EXECUTIVE_BUILD_DECISION_V3.md`
3. `03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md`
4. `04_TECHNICAL_ARCHITECTURE_V3.md`
5. `05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md`
6. `06_COMMERCIAL_MODEL_AND_GTM_V3.md`
7. `FACTORY_LOOP_REDESIGN_SPEC.md`
8. `12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md`
9. `SOURCE_OF_TRUTH_MIGRATION_PLAN.md`
10. `13_SOURCE_REGISTER_V3.md`
11. `14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md`
12. `CODEX_MASTER_MIGRATION_PROMPT.md`
13. `TRAINCAPSULE_V3_MASTER_PLAN.md` — generated one-file consolidation
14. `FINAL_MANIFEST_V3.json` — bundle hashes and inventory

The `examples/` directory contains concrete target configurations and schemas. They are design inputs, not drop-in patches; Codex must reconcile them with the live Pydantic models and tests.

## What should remain from the current design

Keep and harden:

- customer-local execution;
- immutable workload and environment identity;
- native evidence import;
- evidence-completeness and limitation reporting;
- explicit `UNKNOWN`;
- observed boundary versus causal-mechanism separation;
- pack-specific faithful reduction;
- Recovery Assurance;
- expiring, drift-aware incident contracts;
- baseline-versus-candidate qualification;
- replaceable technical backends;
- exact-SHA review;
- isolated worktrees;
- candidate-bound evidence;
- private gates outside the agent-visible repository;
- crash recovery and durable handoffs;
- secret and path protections;
- upstreaming ordinary defects when a normal regression test is sufficient.

## What must not remain controlling

Remove or demote:

- “complete the whole local product before market proof” as the governing build rule;
- one serial task chain;
- unlimited re-specification, retry, self-repair, or roadmap expansion;
- task-level commercial-value proof for mechanical work;
- automatic completion claims based on AI audits;
- direct automatic promotion of trust-critical work to `main`;
- Claude-specific durable state;
- broad context injection containing acquisition and career material;
- a precommitted second commercial pack;
- late competitor comparison;
- factory work that blocks product work;
- any claim that multiple sessions of one model create independent technical authority.

## Honest expectation

This bundle materially improves the probability of building a useful and sellable product. It does not guarantee product-market fit, repeat payment, or acquisition. The decisive evidence will come from real incident archives, a named upcoming change, customer-local execution authority, a paid pilot, and a second paid qualification.
