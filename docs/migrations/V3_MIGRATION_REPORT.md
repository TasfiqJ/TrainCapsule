# TrainCapsule V3 migration report

> **HISTORICAL V3 RECORD — SUPERSEDED FOR ACTIVE OPERATION.** This report preserves the
> completed V3 migration and its then-current main-publication evidence. It is not V3.1-ZH
> acceptance. Current authority, M0 status, and blockers are recorded in
> `docs/migrations/V3_1_ZH_CODEX_EXECUTION_STATE.md`; V3.1 M0 is active and pending independent
> signed authorization plus real automated-PR/required-CI/verified-merged-main receipts.

## Decision and authority

The authoritative 2026-08-11 V3 bundle was verified before implementation: all 30 declared files,
542,907 declared bytes, and every declared SHA-256 matched. Installed normative source files remain
byte-identical to the supplied bundle.

The historical V3 implementation used two scoped owner instructions:

1. Runtime operation is 100% zero-human. Deterministic, digest-bound machine-policy receipts replace
   human operational approvals. There is no human wait/review/owner state in the active V3 domain.
2. Publication is exact-SHA `main` only. Non-main pushes, pull requests, force pushes, and automatic
   dependence on an interactive login are forbidden.

That historical override authority is preserved in `config/owner_directives.yaml`,
`docs/migrations/V3_OWNER_DIRECTIVES.md`, and
`factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json`. It is not active V3.1 authority. V3.1 replaces
direct-main and owner authority with automated PR-only publication plus independent machine-policy
authorization. Historical files remain immutable inputs and may not be imported into active policy.

## Historical V3 completed migration

- The real Windows/WSL launcher invokes the V3 controller. V2 autopilot and ledger-mutation entry
  points fail closed and the 124-entry legacy ledger no longer schedules V3 work.
- The V3 controller uses typed work items, dependency-aware lane scheduling, atomic queue transitions,
  claim leases, bounded concurrency, finite retry/restart budgets, backend-neutral requests,
  digest-bound role context, immutable checkpoint snapshots, handoffs, candidate manifests, salvage,
  and restart recovery.
- Autonomous changes cannot rewrite owner directives, source precedence, V3 source, policy, roadmap,
  or other protected authority. Candidate changed paths and artifacts are verified before publication.
- Historical V3 publication accepted only an exact verified candidate SHA, pushed only `<sha>:refs/heads/main`, never
  force-pushes, verifies remote SHA, monitors the complete configured hosted-workflow set at that SHA,
  and quarantines plus publishes an ordinary multi-commit-tree revert if a hosted gate fails.
- Publication transactions are durable and idempotent across every pre-push, post-push, hosted-poll,
  and revert crash window. Ambiguous recovery writes `HARD_STUCK` and `STOP`.
- Missing policy is `BLOCKED_POLICY`; missing outside facts are scoped `WAITING_EXTERNAL`. Independent
  work continues without any human intervention or fabricated substitute evidence.
- The product is split into four independently installable packages. Typed identity, CAS evidence,
  real-format and controlled import, native baseline generation, redaction, bounded preflight,
  schemas, CLI, adversarial cases, and install-to-preflight journeys are implemented.
- T002 and all V2 evidence remain preserved. T002 is explicitly `DEFERRED_NON_BLOCKING`, has no V3
  mapped item, and cannot auto-resume.

## Historical V3 M0 acceptance

The historical V3 roadmap recorded `M0_FACTORY_MIGRATED` as completed, but those files cannot satisfy
V3.1 M0. The earlier five JSON files
were self-declared summaries rather than independently auditable execution receipts. They have been
replaced with five schema-valid `FINAL`/`PASS` records after the repaired implementation tree was
frozen.

Historical V3 finalization used `scripts/finalize_v3_m0_evidence.py` to generate schema-valid records
containing exact command argv, exit/result/count, failure attribution, transcript path/digest, active
authority digests, and one clean exact subject SHA or mode-aware nonrecursive implementation-tree
digest. Per-ID evidence types and argv are allowlisted, and result counts are derived from the bound
transcript. The final
completion record binds only `V3-MIG-016` through `V3-MIG-019` by their exact file digests; it cannot
cite itself. `scripts/gates/v3_migration_evidence.py` fails closed on pending, missing, altered,
authority-mismatched, transcript-mismatched, tree-mismatched, or recursive evidence.

Historical `V3-MIG-020` ran `scripts/gates/full_quality.sh --pre-evidence` before it was written. That phase ran
complete local acceptance while deliberately skipping only the final evidence gate that cannot pass
until the receipts exist. Normal `full_quality.sh` then validates the final evidence and reruns the
same complete acceptance, avoiding both circularity and premature M0 completion.

The final records bind 663 active implementation files at mode-aware implementation-tree SHA-256
`8a2f80ae17cfe2dbcf45ea296bc7c984901ca2a744809ee4151569203e66db6b`; the finalizer reported evidence
set digest `7fda41fc90b708bb21cf09d3e3d9fe36f3b3d954b69d7d9547dfe9936c9d06f1`.
Normal full quality then passed, followed by an independent 599-test run. Ruff, strict Pyright, all
schema/roadmap/migration generators, configuration validation, migration dry-run, no-paid-usage
policy, bundle/source integrity, and offline wheel build all passed.

The fixed rollback point remains `safety/traincapsule-v3-pre-migration-20260811T212024Z` at
`6b480232fa92b069103da44c475bd17bcb3e6bd1`. Finalization replays it through a read-only `git archive`
and verifies every snapshot-bound tracked input without changing Git or runtime.

## Truthful unresolved scope

No real GPU run, customer archive, customer conversation, customer decision, independent outside
operator run, payment, second paid use, or commercially supported pack is evidenced. Those facts
remain UNKNOWN or `WAITING_EXTERNAL`; synthetic fixtures cannot advance their maturity.

Active V3.1 remains at M0 pending independent source authorization, real automated-PR/required-CI/
verified-merged-main receipts, installed authority, live canaries, and activation evidence. Historical
V3 completion or `PASSED_ENGINEERING` rows cannot advance V3.1 maturity. Outside commercial facts
remain UNKNOWN or `WAITING_EXTERNAL` until signed attributable evidence exists.

## Historical runtime and publication record

The implementation acceptance commit is
`f1fd8077fee001fa6751aa86b26f341f04d0d150`. It was pushed only to `refs/heads/main` without
force, the remote ref resolved to that exact SHA, and all eight configured workflows passed there:
Factory quality `31563636477`, Product unit `31563636487`, Product contract `31563636485`, Security
`31563636472`, Source-of-truth integrity `31563636497`, Packaging install `31563636469`, Docs and
schemas `31563636505`, and Source freshness `31563636499`.

The private GitHub account's hosted-runner billing/spending restriction initially prevented runner
assignment. Final verification used the already-provisioned `traincapsule-wsl-local` runner through
the bounded `TRAINCAPSULE_CI_RUNNER` repository variable, with `ubuntu-latest` retained as the
workflow fallback. No new paid runner usage was created.

Those publication and preflight facts are historical observations for the SHA named above. The
ignored migration marker is mutable runtime state and cannot substitute for tracked, replayable
evidence for a later implementation tree.

## Current V3.1 handoff

Implementation candidate `81e46ce5ad95c588c8fae3bd64f5704e40ac984b` has scoped local evidence,
not complete acceptance. It still requires canonical full local/pre-evidence acceptance, every
exact-head hosted PR check, independent verifier/runtime installation, trusted GitHub App and exact
ruleset, V3.1 M0 receipts, all 20 live canaries, signed activation, and the ordered seven-event
observer. Publication must use the automated PR-only path; direct-main publication is forbidden.
No future SHA, run ID, receipt, or PASS is invented here. Retain `factory/state/STOP` and follow
`docs/migrations/V3_ROLLBACK.md` on ambiguity; never reset or rewrite published history.

<!-- BEGIN GENERATED FILE INVENTORY -->
## Complete tracked file inventory

Compared with `6b480232fa92b069103da44c475bd17bcb3e6bd1`: **645 paths**.

This is a deterministic tracked-tree inventory, not acceptance evidence. The enclosing
report must bind acceptance to an immutable candidate SHA and independent test/receipt
artifacts.

| Change | Path |
|---|---|
| `M` | `.claude/hooks/path_guard.py` |
| `M` | `.factory/README.md` |
| `A` | `.github/workflows/docs-schemas.yml` |
| `A` | `.github/workflows/factory-quality.yml` |
| `D` | `.github/workflows/factory-smoke.yml` |
| `A` | `.github/workflows/gpu-validation.yml` |
| `A` | `.github/workflows/packaging-install.yml` |
| `A` | `.github/workflows/product-contract.yml` |
| `A` | `.github/workflows/product-unit.yml` |
| `A` | `.github/workflows/security.yml` |
| `A` | `.github/workflows/source-freshness.yml` |
| `A` | `.github/workflows/source-of-truth-integrity.yml` |
| `M` | `CLAUDE.md` |
| `M` | `Control-TrainCapsuleBuilder.ps1` |
| `M` | `README.md` |
| `M` | `SOURCE_PRECEDENCE.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/00_START_HERE.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/01_CODEX_MASTER_EXECUTION_PROMPT.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/02_FILES_AND_AUTHORITY_ORDER.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/03_V3_1_ZH_ACCEPTANCE_CONTRACT.yaml` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/04_ZERO_HUMAN_CONFORMANCE_AUDIT.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/05_ZERO_HUMAN_CONFORMANCE_MATRIX.csv` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/06_REQUIRED_FINAL_REPORT_TEMPLATE.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/07_CODEX_PHASE_CHECKLIST.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/08_LAUNCHER_PROMPT.txt` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/09_REMEDIATION_PLAN.yaml` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/10_UNRESOLVED_REQUIREMENTS.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/11_PACKAGE_INVENTORY.md` |
| `A` | `TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/TrainCapsule_Codex_V3_1_ZH_Full_Remediation_Package_2026-08-12/12_SHA256SUMS.txt` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/06_COMMERCIAL_MODEL_AND_GTM_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/13_SOURCE_REGISTER_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FINAL_MANIFEST_V3.json` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/README_FIRST.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/TRAINCAPSULE_V3_MASTER_PLAN.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/config/autonomy.v3.example.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/config/executors.v3.example.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/config/factory.v3.example.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/config/roles.v3.example.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/config/scheduler.v3.example.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/factory/milestones.v3.example.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/factory/work_items.v3.example.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/market/account-map.template.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/market/discovery-interview.template.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/market/pricing-experiment.template.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/product/customer-local-security-checklist.md` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/product/qualification-pilot-intake.template.yaml` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/schemas/external-evidence-receipt.schema.json` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/schemas/human-approval.schema.json` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/schemas/native-substitute-benchmark.schema.json` |
| `A` | `TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/schemas/work-item-v3.schema.json` |
| `A` | `canary_runner/policy/runner-policy.template.json` |
| `A` | `canary_runner/pyproject.toml` |
| `A` | `canary_runner/schemas/mandatory-canary-result.schema.json` |
| `A` | `canary_runner/schemas/mechanism-outcome.schema.json` |
| `A` | `canary_runner/schemas/mechanism-policy.schema.json` |
| `A` | `canary_runner/schemas/runner-policy.schema.json` |
| `A` | `canary_runner/scripts/generate_policy.py` |
| `A` | `canary_runner/scripts/generate_schemas.py` |
| `A` | `canary_runner/src/traincapsule_canary_runner/__init__.py` |
| `A` | `canary_runner/src/traincapsule_canary_runner/cli.py` |
| `A` | `canary_runner/src/traincapsule_canary_runner/external_probes.py` |
| `A` | `canary_runner/src/traincapsule_canary_runner/mechanisms.py` |
| `A` | `canary_runner/src/traincapsule_canary_runner/models.py` |
| `A` | `canary_runner/src/traincapsule_canary_runner/runner.py` |
| `A` | `canary_runner/tests/test_runner.py` |
| `A` | `config/active_generation.yaml` |
| `M` | `config/autonomy.yaml` |
| `M` | `config/claude_features.yaml` |
| `A` | `config/commercial_maturity.yaml` |
| `A` | `config/completion_evidence_policy.yaml` |
| `M` | `config/context.yaml` |
| `A` | `config/executors.yaml` |
| `A` | `config/external_evidence.yaml` |
| `A` | `config/external_evidence_authority_installation.yaml` |
| `M` | `config/factory.yaml` |
| `M` | `config/github.yaml` |
| `A` | `config/human_approval.yaml` |
| `A` | `config/milestones.yaml` |
| `A` | `config/owner_directives.yaml` |
| `M` | `config/risk_profiles.yaml` |
| `M` | `config/roles.yaml` |
| `A` | `config/scheduler.yaml` |
| `A` | `config/traincapsule-controller-runtime.env` |
| `A` | `config/traincapsule-deployment-refresh-claim.path` |
| `A` | `config/traincapsule-deployment-refresh-claim.service` |
| `A` | `config/traincapsule-deployment-refresh-completion.path` |
| `A` | `config/traincapsule-deployment-refresh-completion.service` |
| `A` | `config/traincapsule-deployment-refresh.path` |
| `A` | `config/traincapsule-deployment-refresh.service` |
| `A` | `config/traincapsule-external-evidence-authority.path` |
| `A` | `config/traincapsule-external-evidence-authority.service` |
| `A` | `config/traincapsule-github-token-promoter.path` |
| `A` | `config/traincapsule-github-token-promoter.service` |
| `A` | `config/traincapsule-github-token-refresher.service` |
| `A` | `config/traincapsule-github-token-refresher.timer` |
| `A` | `deployment/__init__.py` |
| `A` | `deployment/bundle_assembler.py` |
| `A` | `deployment/github_token_refresher.py` |
| `A` | `deployment/privileged_installer.py` |
| `A` | `deployment/repository_snapshot.py` |
| `A` | `deployment/runtime_distribution.py` |
| `A` | `deployment/runtime_refresh.py` |
| `A` | `deployment/tests/test_github_token_refresher.py` |
| `A` | `deployment/tests/test_privileged_installer.py` |
| `A` | `deployment/tests/test_repository_snapshot.py` |
| `A` | `deployment/tests/test_runtime_distribution.py` |
| `A` | `deployment/tests/test_runtime_refresh.py` |
| `M` | `docs/CONTEXT_INDEX.yaml` |
| `A` | `docs/migrations/V3_1_ZH_158_ROW_FINDINGS_LEDGER.json` |
| `A` | `docs/migrations/V3_1_ZH_CODEX_EXECUTION_STATE.md` |
| `A` | `docs/migrations/V3_1_ZH_FINDINGS_CROSS_REFERENCE.md` |
| `A` | `docs/migrations/V3_1_ZH_PACKAGE_INTEGRITY.json` |
| `A` | `docs/migrations/V3_1_ZH_PHASE_0_BASELINE.json` |
| `A` | `docs/migrations/V3_1_ZH_REMAINING_ACCEPTANCE.md` |
| `A` | `docs/migrations/V3_1_ZH_ZERO_HUMAN_COMPLETION_PLAN.md` |
| `A` | `docs/migrations/V3_BASELINE_REPORT.md` |
| `A` | `docs/migrations/V3_BUNDLE_INTEGRITY_REPORT.json` |
| `A` | `docs/migrations/V3_CODEX_EXECUTION_STATE.md` |
| `A` | `docs/migrations/V3_LEGACY_QUEUE_ARCHIVE_METADATA.json` |
| `A` | `docs/migrations/V3_MIGRATION_REPORT.md` |
| `A` | `docs/migrations/V3_OWNER_DIRECTIVES.md` |
| `A` | `docs/migrations/V3_ROLLBACK.md` |
| `A` | `docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json` |
| `A` | `docs/migrations/V3_TEST_MATRIX.md` |
| `A` | `docs/migrations/evidence/V3-MIG-016.json` |
| `A` | `docs/migrations/evidence/V3-MIG-017.json` |
| `A` | `docs/migrations/evidence/V3-MIG-018.json` |
| `A` | `docs/migrations/evidence/V3-MIG-019.json` |
| `A` | `docs/migrations/evidence/V3-MIG-020.json` |
| `A` | `docs/migrations/evidence/transcripts/V3-MIG-016-01-source-authority-integrity.json` |
| `A` | `docs/migrations/evidence/transcripts/V3-MIG-016-02-active-policy-integrity.json` |
| `A` | `docs/migrations/evidence/transcripts/V3-MIG-016-03-authoritative-bundle-integrity.json` |
| `A` | `docs/migrations/evidence/transcripts/V3-MIG-017-01-rollback-archive-rehearsal.json` |
| `A` | `docs/migrations/evidence/transcripts/V3-MIG-018-01-controller-observation-contracts.json` |
| `A` | `docs/migrations/evidence/transcripts/V3-MIG-019-01-controller-simulation.json` |
| `A` | `docs/migrations/evidence/transcripts/V3-MIG-020-01-complete-pre-evidence-acceptance.json` |
| `A` | `docs/migrations/evidence/v3.1-zh/V3-MIG-016.json` |
| `A` | `docs/migrations/evidence/v3.1-zh/V3-MIG-017.json` |
| `A` | `docs/migrations/evidence/v3.1-zh/V3-MIG-018.json` |
| `A` | `docs/migrations/evidence/v3.1-zh/V3-MIG-019.json` |
| `A` | `docs/migrations/evidence/v3.1-zh/V3-MIG-020.json` |
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
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/13_SOURCE_REGISTER_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/README.md` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/SECTION_COVERAGE_V3_TO_V3_1_ZH.json` |
| `A` | `docs/source-of-truth/v3.1-zh-2026-08-12/SOURCE_OF_TRUTH_MIGRATION_PLAN_V3_1_ZH.md` |
| `A` | `examples/product/README.md` |
| `A` | `examples/product/environment-identity-input.json` |
| `A` | `examples/product/flight-recorder/real-format/rank-0.json` |
| `A` | `examples/product/flight-recorder/real-format/rank-1.json` |
| `A` | `examples/product/flight-recorder/supported/metadata.json` |
| `A` | `examples/product/flight-recorder/supported/rank-0.json` |
| `A` | `examples/product/flight-recorder/supported/rank-1.json` |
| `A` | `examples/product/flight-recorder/unsupported/metadata.json` |
| `A` | `examples/product/flight-recorder/unsupported/rank-0.json` |
| `A` | `examples/product/workload-identity-input.json` |
| `A` | `factory/policy/T002_LEGAL_CLEARANCE_CHECKLIST.yaml` |
| `A` | `factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json` |
| `A` | `factory/roadmap/dispositions.yaml` |
| `A` | `factory/roadmap/legacy_feature_ledger.yaml` |
| `A` | `factory/roadmap/migrations/v2_runtime_evidence_manifest.json` |
| `A` | `factory/roadmap/migrations/v2_to_v3.yaml` |
| `A` | `factory/roadmap/migrations/v2_to_v3.yaml.previous` |
| `A` | `factory/roadmap/migrations/v3_to_v3_1_zh.yaml` |
| `A` | `factory/roadmap/milestones.yaml` |
| `A` | `factory/roadmap/work_items.yaml` |
| `A` | `packages/traincapsule-cli/pyproject.toml` |
| `A` | `packages/traincapsule-cli/src/traincapsule_cli/__init__.py` |
| `A` | `packages/traincapsule-cli/src/traincapsule_cli/cli.py` |
| `A` | `packages/traincapsule-core/pyproject.toml` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/__init__.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/base.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/evidence.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/identity.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/models.py` |
| `A` | `packages/traincapsule-core/src/traincapsule_core/secure_fs.py` |
| `A` | `packages/traincapsule-ingest-pytorch/pyproject.toml` |
| `A` | `packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/__init__.py` |
| `A` | `packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/importer.py` |
| `A` | `packages/traincapsule-qualify/pyproject.toml` |
| `A` | `packages/traincapsule-qualify/src/traincapsule_qualify/__init__.py` |
| `A` | `packages/traincapsule-qualify/src/traincapsule_qualify/experiment.py` |
| `A` | `packages/traincapsule-qualify/src/traincapsule_qualify/models.py` |
| `A` | `packages/traincapsule-qualify/src/traincapsule_qualify/qualify.py` |
| `M` | `private-gates-reference/README.md` |
| `M` | `prompts/adversary.md` |
| `M` | `prompts/audit.md` |
| `M` | `prompts/autonomous_planner.md` |
| `M` | `prompts/bootstrap_integrator_windows11.md` |
| `M` | `prompts/builder.md` |
| `A` | `prompts/commercial_experiment.md` |
| `M` | `prompts/factory_repair.md` |
| `M` | `prompts/global.md` |
| `M` | `prompts/integration_scout.md` |
| `A` | `prompts/machine_policy_receipt.md` |
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
| `A` | `schemas/factory/v3.1/account-evidence-field.schema.json` |
| `A` | `schemas/factory/v3.1/account-qualification-score.schema.json` |
| `A` | `schemas/factory/v3.1/activation-receipt.schema.json` |
| `A` | `schemas/factory/v3.1/activation-request.schema.json` |
| `A` | `schemas/factory/v3.1/activation-transaction.schema.json` |
| `A` | `schemas/factory/v3.1/agent-execution-report.schema.json` |
| `A` | `schemas/factory/v3.1/authorized-value-transition.schema.json` |
| `A` | `schemas/factory/v3.1/compiled-task-contract.schema.json` |
| `A` | `schemas/factory/v3.1/decision-value.schema.json` |
| `A` | `schemas/factory/v3.1/discovery-interview-guide.schema.json` |
| `A` | `schemas/factory/v3.1/execution-report.schema.json` |
| `A` | `schemas/factory/v3.1/external-action-installation.schema.json` |
| `A` | `schemas/factory/v3.1/external-action-outcome.schema.json` |
| `A` | `schemas/factory/v3.1/external-action-payload.schema.json` |
| `A` | `schemas/factory/v3.1/external-action-request.schema.json` |
| `A` | `schemas/factory/v3.1/external-action-template.schema.json` |
| `A` | `schemas/factory/v3.1/external-delivery-receipt.schema.json` |
| `A` | `schemas/factory/v3.1/fingerprint-counter.schema.json` |
| `A` | `schemas/factory/v3.1/interview-question.schema.json` |
| `A` | `schemas/factory/v3.1/machine-policy-receipt.schema.json` |
| `A` | `schemas/factory/v3.1/machine-policy-revocation-list.schema.json` |
| `A` | `schemas/factory/v3.1/mandatory-canary-result.schema.json` |
| `A` | `schemas/factory/v3.1/mandatory-canary-suite.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-agent-capability.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-agent-request.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-candidate-manifest.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-checkpoint.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-finding.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-handoff.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-task-packet.schema.json` |
| `A` | `schemas/factory/v3.1/migrated-work-item.schema.json` |
| `A` | `schemas/factory/v3.1/milestone-completion-proposal.schema.json` |
| `A` | `schemas/factory/v3.1/native-substitute-benchmark.schema.json` |
| `A` | `schemas/factory/v3.1/native-value-gate-policy.schema.json` |
| `A` | `schemas/factory/v3.1/output-declaration.schema.json` |
| `A` | `schemas/factory/v3.1/parsed-claim-result.schema.json` |
| `A` | `schemas/factory/v3.1/parsed-source-result.schema.json` |
| `A` | `schemas/factory/v3.1/pilot-qualification-rubric.schema.json` |
| `A` | `schemas/factory/v3.1/post-activation-observation.schema.json` |
| `A` | `schemas/factory/v3.1/pr-publication-transaction.schema.json` |
| `A` | `schemas/factory/v3.1/reachable-account-map.schema.json` |
| `A` | `schemas/factory/v3.1/reachable-account.schema.json` |
| `A` | `schemas/factory/v3.1/research-claim.schema.json` |
| `A` | `schemas/factory/v3.1/research-control.schema.json` |
| `A` | `schemas/factory/v3.1/research-finding.schema.json` |
| `A` | `schemas/factory/v3.1/research-query-plan.schema.json` |
| `A` | `schemas/factory/v3.1/research-report.schema.json` |
| `A` | `schemas/factory/v3.1/research-resolution.schema.json` |
| `A` | `schemas/factory/v3.1/research-source-request.schema.json` |
| `A` | `schemas/factory/v3.1/research-source.schema.json` |
| `A` | `schemas/factory/v3.1/runtime-event.schema.json` |
| `A` | `schemas/factory/v3.1/runtime-status.schema.json` |
| `A` | `schemas/factory/v3.1/session-reference.schema.json` |
| `A` | `schemas/factory/v3.1/source-acquisition-policy.schema.json` |
| `A` | `schemas/factory/v3.1/source-artifact.schema.json` |
| `A` | `schemas/factory/v3.1/source-freshness-receipt.schema.json` |
| `A` | `schemas/factory/v3.1/source-generation.schema.json` |
| `A` | `schemas/factory/v3.1/source-hop-receipt.schema.json` |
| `A` | `schemas/factory/v3.1/source-parser-limits.schema.json` |
| `A` | `schemas/factory/v3.1/source-retrieval-receipt.schema.json` |
| `A` | `schemas/factory/v3.1/task-output-declaration.schema.json` |
| `A` | `schemas/factory/v3.1/task-result-artifact.schema.json` |
| `A` | `schemas/factory/v3.1/task-tool-policy.schema.json` |
| `A` | `schemas/factory/v3/active-generation.schema.json` |
| `A` | `schemas/factory/v3/active-source-generation.schema.json` |
| `A` | `schemas/factory/v3/agent-capabilities.schema.json` |
| `A` | `schemas/factory/v3/agent-run-result.schema.json` |
| `A` | `schemas/factory/v3/agent-task-request.schema.json` |
| `A` | `schemas/factory/v3/autonomy-config.schema.json` |
| `A` | `schemas/factory/v3/candidate-manifest.schema.json` |
| `A` | `schemas/factory/v3/checkpoint.schema.json` |
| `A` | `schemas/factory/v3/commercial-maturity-config.schema.json` |
| `A` | `schemas/factory/v3/completion-evidence-observation.schema.json` |
| `A` | `schemas/factory/v3/completion-evidence-policy.schema.json` |
| `A` | `schemas/factory/v3/context-manifest.schema.json` |
| `A` | `schemas/factory/v3/context-policy-config.schema.json` |
| `A` | `schemas/factory/v3/decision-value.schema.json` |
| `A` | `schemas/factory/v3/delivery-economics-evidence.schema.json` |
| `A` | `schemas/factory/v3/delivery-measurement.schema.json` |
| `A` | `schemas/factory/v3/dispositions.schema.json` |
| `A` | `schemas/factory/v3/executors-config.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-authority-anchor.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-authority-ledger.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-authority-state.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-config.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-receipt.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-revocation-list.schema.json` |
| `A` | `schemas/factory/v3/factory-config.schema.json` |
| `A` | `schemas/factory/v3/finding-counter.schema.json` |
| `A` | `schemas/factory/v3/finding.schema.json` |
| `A` | `schemas/factory/v3/frozen-release-evidence-authorization.schema.json` |
| `A` | `schemas/factory/v3/github-config.schema.json` |
| `A` | `schemas/factory/v3/handoff.schema.json` |
| `A` | `schemas/factory/v3/hard-stuck.schema.json` |
| `A` | `schemas/factory/v3/incident-contract.schema.json` |
| `A` | `schemas/factory/v3/incident-invariant-observation.schema.json` |
| `A` | `schemas/factory/v3/legacy-migration.schema.json` |
| `A` | `schemas/factory/v3/migration-complete-marker.schema.json` |
| `A` | `schemas/factory/v3/migration-evidence.schema.json` |
| `A` | `schemas/factory/v3/milestone-advance-transaction.schema.json` |
| `A` | `schemas/factory/v3/milestone-completion-receipt.schema.json` |
| `A` | `schemas/factory/v3/milestone-completion.schema.json` |
| `A` | `schemas/factory/v3/milestone-evidence-contract.schema.json` |
| `A` | `schemas/factory/v3/milestone-policy-config.schema.json` |
| `A` | `schemas/factory/v3/milestone-runtime-state.schema.json` |
| `A` | `schemas/factory/v3/milestones.schema.json` |
| `A` | `schemas/factory/v3/private-gate-receipt.schema.json` |
| `A` | `schemas/factory/v3/reduction-boundary-evidence.schema.json` |
| `A` | `schemas/factory/v3/reduction-candidate-input.schema.json` |
| `A` | `schemas/factory/v3/reduction-oracle-decision.schema.json` |
| `A` | `schemas/factory/v3/release-candidate.schema.json` |
| `A` | `schemas/factory/v3/retry-policy.schema.json` |
| `A` | `schemas/factory/v3/scheduler.schema.json` |
| `A` | `schemas/factory/v3/source-generation-manifest.schema.json` |
| `A` | `schemas/factory/v3/source-wedge-proposal.schema.json` |
| `A` | `schemas/factory/v3/supervisor-state.schema.json` |
| `A` | `schemas/factory/v3/support-policy-evidence.schema.json` |
| `A` | `schemas/factory/v3/task-packet.schema.json` |
| `A` | `schemas/factory/v3/third-same-family-case-evidence.schema.json` |
| `A` | `schemas/factory/v3/traincheck-differential-request.schema.json` |
| `A` | `schemas/factory/v3/traincheck-differential-result.schema.json` |
| `A` | `schemas/factory/v3/usage-state.schema.json` |
| `A` | `schemas/factory/v3/work-item-completion-evidence.schema.json` |
| `A` | `schemas/factory/v3/work-item-evidence-contract.schema.json` |
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
| `A` | `scripts/build_production_runtime.py` |
| `M` | `scripts/configure_github.sh` |
| `M` | `scripts/configure_max5_token.sh` |
| `M` | `scripts/enable_lights_out.sh` |
| `M` | `scripts/factory_control.sh` |
| `M` | `scripts/factory_status.sh` |
| `A` | `scripts/finalize_v3_1_zh_m0_evidence.py` |
| `A` | `scripts/finalize_v3_m0_evidence.py` |
| `A` | `scripts/gates/active_policy_integrity.py` |
| `M` | `scripts/gates/full_quality.sh` |
| `A` | `scripts/gates/generate_sbom.py` |
| `M` | `scripts/gates/no_paid_usage.py` |
| `M` | `scripts/gates/output_and_integration_gate.py` |
| `A` | `scripts/gates/source_of_truth_integrity.py` |
| `A` | `scripts/gates/v3_1_zh_package_integrity.py` |
| `A` | `scripts/gates/v3_bundle_integrity.py` |
| `A` | `scripts/gates/v3_migration_evidence.py` |
| `A` | `scripts/gates/v3_rollback_rehearsal.py` |
| `A` | `scripts/generate_completion_evidence_policy.py` |
| `A` | `scripts/generate_product_schemas.py` |
| `A` | `scripts/generate_v31_contract_schemas.py` |
| `A` | `scripts/generate_v3_1_zh_source.py` |
| `A` | `scripts/generate_v3_legacy_migration.py` |
| `A` | `scripts/generate_v3_manifest.py` |
| `A` | `scripts/generate_v3_roadmap.py` |
| `A` | `scripts/generate_v3_schemas.py` |
| `M` | `scripts/install_private_gate.sh` |
| `M` | `scripts/load_factory_env.sh` |
| `M` | `scripts/one_time_setup.sh` |
| `M` | `scripts/pause_factory.sh` |
| `M` | `scripts/recover_factory.sh` |
| `M` | `scripts/register_windows_autostart.ps1` |
| `M` | `scripts/resume_factory.sh` |
| `M` | `scripts/run_one_time_calibration.sh` |
| `M` | `scripts/stop_factory.sh` |
| `M` | `scripts/systemd_entrypoint.sh` |
| `A` | `scripts/update_v31_findings_candidate.py` |
| `A` | `scripts/update_v3_migration_inventory.py` |
| `M` | `scripts/verify_autonomous_loop.sh` |
| `M` | `scripts/verify_claude_features.sh` |
| `M` | `scripts/verify_factory_authority.sh` |
| `A` | `scripts/windows_activation_entrypoint.sh` |
| `M` | `scripts/windows_task_entrypoint.sh` |
| `M` | `scripts/windows_wsl_prepare.sh` |
| `M` | `tcfactory/autopilot.py` |
| `A` | `tcfactory/backends/__init__.py` |
| `A` | `tcfactory/backends/base.py` |
| `A` | `tcfactory/backends/claude.py` |
| `A` | `tcfactory/backends/fake.py` |
| `M` | `tcfactory/catalog.py` |
| `M` | `tcfactory/checkpoints.py` |
| `M` | `tcfactory/claude_features.py` |
| `M` | `tcfactory/claude_runner.py` |
| `M` | `tcfactory/cli.py` |
| `M` | `tcfactory/completion.py` |
| `M` | `tcfactory/config.py` |
| `M` | `tcfactory/context.py` |
| `M` | `tcfactory/gates.py` |
| `M` | `tcfactory/github_sync.py` |
| `M` | `tcfactory/gitops.py` |
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
| `M` | `tcfactory/self_repair.py` |
| `M` | `tcfactory/stage_policy.py` |
| `M` | `tcfactory/structured_runner.py` |
| `A` | `tcfactory/supervisor.py` |
| `M` | `tcfactory/usage.py` |
| `M` | `tcfactory/util.py` |
| `A` | `tcfactory/v3/__init__.py` |
| `A` | `tcfactory/v3/activation.py` |
| `A` | `tcfactory/v3/activation_supervisor.py` |
| `A` | `tcfactory/v3/base.py` |
| `A` | `tcfactory/v3/canaries.py` |
| `A` | `tcfactory/v3/candidate_freeze.py` |
| `A` | `tcfactory/v3/candidate_manifest.py` |
| `A` | `tcfactory/v3/completion_artifacts.py` |
| `A` | `tcfactory/v3/completion_policy.py` |
| `A` | `tcfactory/v3/completion_verification.py` |
| `A` | `tcfactory/v3/configuration.py` |
| `A` | `tcfactory/v3/contracts_v31.py` |
| `A` | `tcfactory/v3/controller.py` |
| `A` | `tcfactory/v3/controller_lock.py` |
| `A` | `tcfactory/v3/dispositions.py` |
| `A` | `tcfactory/v3/doctor.py` |
| `A` | `tcfactory/v3/enums.py` |
| `A` | `tcfactory/v3/external_actions.py` |
| `A` | `tcfactory/v3/external_evidence.py` |
| `A` | `tcfactory/v3/external_evidence_authority.py` |
| `A` | `tcfactory/v3/external_evidence_broker_cli.py` |
| `A` | `tcfactory/v3/installed_runtime.py` |
| `A` | `tcfactory/v3/machine_policy_runtime.py` |
| `A` | `tcfactory/v3/market_artifacts.py` |
| `A` | `tcfactory/v3/maturity.py` |
| `A` | `tcfactory/v3/migration_evidence.py` |
| `A` | `tcfactory/v3/migrations.py` |
| `A` | `tcfactory/v3/milestone_runtime.py` |
| `A` | `tcfactory/v3/milestones.py` |
| `A` | `tcfactory/v3/native_value_gate.py` |
| `A` | `tcfactory/v3/native_value_runtime.py` |
| `A` | `tcfactory/v3/phase6_installation.py` |
| `A` | `tcfactory/v3/phase6_runtime.py` |
| `A` | `tcfactory/v3/pilot.py` |
| `A` | `tcfactory/v3/pipeline_services.py` |
| `A` | `tcfactory/v3/planning.py` |
| `A` | `tcfactory/v3/post_activation_events.py` |
| `A` | `tcfactory/v3/private_gate.py` |
| `A` | `tcfactory/v3/publication.py` |
| `A` | `tcfactory/v3/queue.py` |
| `A` | `tcfactory/v3/recovery.py` |
| `A` | `tcfactory/v3/retry_policy.py` |
| `A` | `tcfactory/v3/runtime_paths.py` |
| `A` | `tcfactory/v3/scheduler.py` |
| `A` | `tcfactory/v3/service_storage.py` |
| `A` | `tcfactory/v3/source_acquisition.py` |
| `A` | `tcfactory/v3/source_authority.py` |
| `A` | `tcfactory/v3/task_compiler_v31.py` |
| `A` | `tcfactory/v3/traincheck_differential.py` |
| `A` | `tcfactory/v3/verifier_submission.py` |
| `A` | `tcfactory/v3/work_items.py` |
| `M` | `tcfactory/value.py` |
| `M` | `tcfactory/value_policy.py` |
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
| `M` | `tests/test_calibration_evidence.py` |
| `M` | `tests/test_catalog.py` |
| `M` | `tests/test_claude_features.py` |
| `M` | `tests/test_claude_led_nodes.py` |
| `M` | `tests/test_claude_only_policy.py` |
| `M` | `tests/test_completion.py` |
| `M` | `tests/test_context_manifest.py` |
| `M` | `tests/test_control_scripts.py` |
| `M` | `tests/test_github_policy.py` |
| `M` | `tests/test_github_setup_script.py` |
| `A` | `tests/test_independent_verifier.py` |
| `M` | `tests/test_risk_routing.py` |
| `A` | `tests/test_sbom_generation.py` |
| `A` | `tests/test_source_of_truth_integrity.py` |
| `A` | `tests/test_v31_activation_and_canaries.py` |
| `A` | `tests/test_v31_completion_policy.py` |
| `A` | `tests/test_v31_contracts.py` |
| `A` | `tests/test_v31_controlled_source_acquisition.py` |
| `A` | `tests/test_v31_external_actions.py` |
| `A` | `tests/test_v31_findings_candidate_ledger.py` |
| `A` | `tests/test_v31_market_artifacts.py` |
| `A` | `tests/test_v31_native_value_gate.py` |
| `A` | `tests/test_v31_output_integration_gate.py` |
| `A` | `tests/test_v31_phase6_installation.py` |
| `A` | `tests/test_v31_post_activation_events.py` |
| `A` | `tests/test_v31_task_compiler.py` |
| `A` | `tests/test_v3_backend_runtime_policy.py` |
| `A` | `tests/test_v3_backends_and_checkpoints.py` |
| `A` | `tests/test_v3_candidate_salvage.py` |
| `A` | `tests/test_v3_config_and_roadmap.py` |
| `A` | `tests/test_v3_context_authority.py` |
| `A` | `tests/test_v3_controller_simulation.py` |
| `A` | `tests/test_v3_doctor_and_pilot.py` |
| `A` | `tests/test_v3_domain_models.py` |
| `A` | `tests/test_v3_github_workflows.py` |
| `A` | `tests/test_v3_legacy_migration.py` |
| `A` | `tests/test_v3_machine_policy.py` |
| `A` | `tests/test_v3_migration_evidence_and_policy.py` |
| `A` | `tests/test_v3_milestone_runtime.py` |
| `A` | `tests/test_v3_operator_runtime_paths.py` |
| `A` | `tests/test_v3_package_and_historical_integrity.py` |
| `A` | `tests/test_v3_phase1_fail_closed.py` |
| `A` | `tests/test_v3_planning_context_and_support.py` |
| `A` | `tests/test_v3_private_gate.py` |
| `A` | `tests/test_v3_prompt_contracts.py` |
| `A` | `tests/test_v3_publication_recovery.py` |
| `A` | `tests/test_v3_queue.py` |
| `A` | `tests/test_v3_scheduler_and_recovery.py` |
| `A` | `tests/test_v3_source_authority.py` |
| `A` | `tests/test_v3_supervisor_and_status.py` |
| `A` | `tests/test_v3_verifier_submission_bridge.py` |
| `M` | `tests/test_windows_autostart_scripts.py` |
| `M` | `uv.lock` |
| `A` | `verifier/.gitignore` |
| `A` | `verifier/README.md` |
| `A` | `verifier/__init__.py` |
| `A` | `verifier/pyproject.toml` |
| `A` | `verifier/pyrightconfig.json` |
| `A` | `verifier/schemas/activation-authorization.schema.json` |
| `A` | `verifier/schemas/activation-receipt.schema.json` |
| `A` | `verifier/schemas/activation-request.schema.json` |
| `A` | `verifier/schemas/authority-anchor.schema.json` |
| `A` | `verifier/schemas/check-authorization.schema.json` |
| `A` | `verifier/schemas/check-delivery-receipt.schema.json` |
| `A` | `verifier/schemas/check-event.schema.json` |
| `A` | `verifier/schemas/check-process-result.schema.json` |
| `A` | `verifier/schemas/check-publish-request.schema.json` |
| `A` | `verifier/schemas/check-publisher-policy.schema.json` |
| `A` | `verifier/schemas/installation-attestation.schema.json` |
| `A` | `verifier/schemas/machine-policy-receipt.schema.json` |
| `A` | `verifier/schemas/observed-main-receipt.schema.json` |
| `A` | `verifier/schemas/oracle-execution-result.schema.json` |
| `A` | `verifier/schemas/revocation-list.schema.json` |
| `A` | `verifier/schemas/ruleset-observation-receipt.schema.json` |
| `A` | `verifier/schemas/trusted-evidence-manifest.schema.json` |
| `A` | `verifier/schemas/verification-request.schema.json` |
| `A` | `verifier/schemas/verifier-policy.schema.json` |
| `A` | `verifier/scripts/__init__.py` |
| `A` | `verifier/scripts/generate_schemas.py` |
| `A` | `verifier/scripts/plan_production_install.py` |
| `A` | `verifier/scripts/rehearse_install.py` |
| `A` | `verifier/src/traincapsule_verifier/__init__.py` |
| `A` | `verifier/src/traincapsule_verifier/activation_issuer_service.py` |
| `A` | `verifier/src/traincapsule_verifier/activation_request_broker.py` |
| `A` | `verifier/src/traincapsule_verifier/activation_selector_broker.py` |
| `A` | `verifier/src/traincapsule_verifier/attestation.py` |
| `A` | `verifier/src/traincapsule_verifier/bootstrap.py` |
| `A` | `verifier/src/traincapsule_verifier/broker_cli.py` |
| `A` | `verifier/src/traincapsule_verifier/canary_receipt_probe.py` |
| `A` | `verifier/src/traincapsule_verifier/canonical.py` |
| `A` | `verifier/src/traincapsule_verifier/check_publisher.py` |
| `A` | `verifier/src/traincapsule_verifier/check_worker_cli.py` |
| `A` | `verifier/src/traincapsule_verifier/cli.py` |
| `A` | `verifier/src/traincapsule_verifier/controller_start_broker.py` |
| `A` | `verifier/src/traincapsule_verifier/crypto.py` |
| `A` | `verifier/src/traincapsule_verifier/evaluator.py` |
| `A` | `verifier/src/traincapsule_verifier/filesystem.py` |
| `A` | `verifier/src/traincapsule_verifier/git_anchor_producer.py` |
| `A` | `verifier/src/traincapsule_verifier/git_anchor_updater.py` |
| `A` | `verifier/src/traincapsule_verifier/github_app_backend.py` |
| `A` | `verifier/src/traincapsule_verifier/github_app_readonly.py` |
| `A` | `verifier/src/traincapsule_verifier/install_cli.py` |
| `A` | `verifier/src/traincapsule_verifier/issuer_service.py` |
| `A` | `verifier/src/traincapsule_verifier/models.py` |
| `A` | `verifier/src/traincapsule_verifier/observed_main_selector.py` |
| `A` | `verifier/src/traincapsule_verifier/post_activation_observer.py` |
| `A` | `verifier/src/traincapsule_verifier/public_cli.py` |
| `A` | `verifier/src/traincapsule_verifier/public_crypto.py` |
| `A` | `verifier/src/traincapsule_verifier/public_verifier.py` |
| `A` | `verifier/src/traincapsule_verifier/receipt_broker.py` |
| `A` | `verifier/src/traincapsule_verifier/request_broker.py` |
| `A` | `verifier/src/traincapsule_verifier/request_broker_cli.py` |
| `A` | `verifier/src/traincapsule_verifier/ruleset_broker.py` |
| `A` | `verifier/src/traincapsule_verifier/ruleset_observer.py` |
| `A` | `verifier/src/traincapsule_verifier/ruleset_policy.py` |
| `A` | `verifier/tests/canonical-vector.json` |
| `A` | `verifier/tests/test_canary_receipt_probe.py` |
| `A` | `verifier/tests/test_controller_start_broker.py` |
| `A` | `verifier/tests/test_git_anchor_producer.py` |
| `A` | `verifier/tests/test_git_anchor_updater.py` |
| `A` | `verifier/tests/test_github_app_readonly.py` |
| `A` | `verifier/tests/test_post_activation_observer.py` |
| `A` | `verifier/tests/test_public_boundary.py` |
| `A` | `verifier/tests/test_ruleset_policy.py` |
| `A` | `verifier/tests/test_selector_and_ruleset.py` |
| `A` | `verifier/tests/test_service_bootstrap.py` |
<!-- END GENERATED FILE INVENTORY -->
