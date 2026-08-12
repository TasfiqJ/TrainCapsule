# TrainCapsule V3 migration report

## Decision and authority

The authoritative 2026-08-11 V3 bundle was verified before implementation: all 30 declared files,
542,907 declared bytes, and every declared SHA-256 matched. Installed normative source files remain
byte-identical to the supplied bundle.

Two later owner instructions are active, scoped overrides:

1. Runtime operation is 100% zero-human. Deterministic, digest-bound machine-policy receipts replace
   human operational approvals. There is no human wait/review/owner state in the active V3 domain.
2. Publication is exact-SHA `main` only. Non-main pushes, pull requests, force pushes, and automatic
   dependence on an interactive login are forbidden.

The override authority is explicit in `config/owner_directives.yaml`,
`docs/migrations/V3_OWNER_DIRECTIVES.md`, and
`factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json`. It does not relax evidence truth, external-fact
ceilings, source integrity, exact-SHA binding, finite recovery, or commercial non-claims.

## Completed migration

- The real Windows/WSL launcher invokes the V3 controller. V2 autopilot and ledger-mutation entry
  points fail closed and the 124-entry legacy ledger no longer schedules V3 work.
- The V3 controller uses typed work items, dependency-aware lane scheduling, atomic queue transitions,
  claim leases, bounded concurrency, finite retry/restart budgets, backend-neutral requests,
  digest-bound role context, immutable checkpoint snapshots, handoffs, candidate manifests, salvage,
  and restart recovery.
- Autonomous changes cannot rewrite owner directives, source precedence, V3 source, policy, roadmap,
  or other protected authority. Candidate changed paths and artifacts are verified before publication.
- Publication accepts only an exact verified candidate SHA, pushes only `<sha>:refs/heads/main`, never
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

## M0 acceptance

`M0_FACTORY_MIGRATED` is completed. Its final five acceptance records are tracked and digest-bound:

- `docs/migrations/evidence/V3-MIG-016.json`: owner-directed machine-policy authority.
- `docs/migrations/evidence/V3-MIG-017.json`: disposable rollback rehearsal to exact safety SHA.
- `docs/migrations/evidence/V3-MIG-018.json`: non-mutating controller observation contracts.
- `docs/migrations/evidence/V3-MIG-019.json`: disposable mechanical and standard V3 execution.
- `docs/migrations/evidence/V3-MIG-020.json`: bounded M0 completion record.

The fixed rollback point is `safety/traincapsule-v3-pre-migration-20260811T212024Z` at
`6b480232fa92b069103da44c475bd17bcb3e6bd1`. The rehearsal restored that exact SHA, found a clean
tree, verified the preserved ledger digest
`ab5d10c6718d3a9fdf53dd78cf0c387e995cd1723cf10b76fb53e14af559c994`, and removed only the
disposable worktree.

The controller simulation completed one mechanical and one standard item, left the outside-fact item
at `WAITING_EXTERNAL`, reported `interventionMode: NONE`, preserved the V2 ledger byte-for-byte, and
used neither a model nor network access.

## Truthful unresolved scope

No real GPU run, customer archive, customer conversation, customer decision, independent outside
operator run, payment, second paid use, or commercially supported pack is evidenced. Those facts
remain UNKNOWN or `WAITING_EXTERNAL`; synthetic fixtures cannot advance their maturity.

M1 is the active engineering milestone. Product/trust items already implemented are marked `PASSED_ENGINEERING` so the scheduler will not
repeat them. Competitor/current-fact research and all outside/commercial work retain their bounded
roadmap states.

## Runtime and publication handoff

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

The ignored migration marker is valid and bound to the published commit, source manifest, owner
directives, and five M0 evidence files. A direct preflight probe initially misclassified the
credential as `AUTH_EXPIRED` because it did not load the launcher PATH. The installed Claude CLI
actually reports first-party `claude.ai` Max authentication. Loading the real launcher environment
then exposed two forbidden V2-only overrides; those were removed, and private-gate discovery now
uses its fixed controller-owned path outside the repository. The corrected preflight returned
`ready: true`, `credentials: AUTHENTICATED`, `runtimeState: CLEAN`, and validated all 16 V3 config
sets plus source, marker, live archive, and publication recovery. No model was invoked during these
probes.

After the runtime-path repair is exact-SHA hosted-green, the durable stops may be removed and the
verified launcher enabled for a bounded observation. If any later publication or hosted verification
fails, retain the stopped state and follow `docs/migrations/V3_ROLLBACK.md`; never reset or rewrite
published history.

<!-- BEGIN GENERATED FILE INVENTORY -->
## Complete tracked file inventory

Compared with `6b480232fa92b069103da44c475bd17bcb3e6bd1`: **270 paths**.

| Change | Path |
|---|---|
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
| `M` | `Control-TrainCapsuleBuilder.ps1` |
| `M` | `README.md` |
| `M` | `SOURCE_PRECEDENCE.md` |
| `M` | `config/autonomy.yaml` |
| `M` | `config/claude_features.yaml` |
| `A` | `config/commercial_maturity.yaml` |
| `M` | `config/context.yaml` |
| `A` | `config/executors.yaml` |
| `A` | `config/external_evidence.yaml` |
| `M` | `config/factory.yaml` |
| `M` | `config/github.yaml` |
| `A` | `config/human_approval.yaml` |
| `A` | `config/milestones.yaml` |
| `A` | `config/owner_directives.yaml` |
| `M` | `config/risk_profiles.yaml` |
| `M` | `config/roles.yaml` |
| `A` | `config/scheduler.yaml` |
| `M` | `docs/CONTEXT_INDEX.yaml` |
| `A` | `docs/migrations/V3_BASELINE_REPORT.md` |
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
| `A` | `factory/roadmap/migrations/v2_to_v3.yaml` |
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
| `A` | `packages/traincapsule-ingest-pytorch/pyproject.toml` |
| `A` | `packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/__init__.py` |
| `A` | `packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/importer.py` |
| `A` | `packages/traincapsule-qualify/pyproject.toml` |
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
| `A` | `schemas/factory/v3/agent-capabilities.schema.json` |
| `A` | `schemas/factory/v3/agent-run-result.schema.json` |
| `A` | `schemas/factory/v3/agent-task-request.schema.json` |
| `A` | `schemas/factory/v3/autonomy-config.schema.json` |
| `A` | `schemas/factory/v3/candidate-manifest.schema.json` |
| `A` | `schemas/factory/v3/checkpoint.schema.json` |
| `A` | `schemas/factory/v3/commercial-maturity-config.schema.json` |
| `A` | `schemas/factory/v3/context-manifest.schema.json` |
| `A` | `schemas/factory/v3/context-policy-config.schema.json` |
| `A` | `schemas/factory/v3/decision-value.schema.json` |
| `A` | `schemas/factory/v3/dispositions.schema.json` |
| `A` | `schemas/factory/v3/executors-config.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-config.schema.json` |
| `A` | `schemas/factory/v3/external-evidence-receipt.schema.json` |
| `A` | `schemas/factory/v3/factory-config.schema.json` |
| `A` | `schemas/factory/v3/finding-counter.schema.json` |
| `A` | `schemas/factory/v3/finding.schema.json` |
| `A` | `schemas/factory/v3/github-config.schema.json` |
| `A` | `schemas/factory/v3/handoff.schema.json` |
| `A` | `schemas/factory/v3/hard-stuck.schema.json` |
| `A` | `schemas/factory/v3/human-approval-disabled-config.schema.json` |
| `A` | `schemas/factory/v3/legacy-migration.schema.json` |
| `A` | `schemas/factory/v3/main-policy-receipt.schema.json` |
| `A` | `schemas/factory/v3/main-publication-transaction.schema.json` |
| `A` | `schemas/factory/v3/main-publication.schema.json` |
| `A` | `schemas/factory/v3/migration-complete-marker.schema.json` |
| `A` | `schemas/factory/v3/milestone-completion.schema.json` |
| `A` | `schemas/factory/v3/milestone-policy-config.schema.json` |
| `A` | `schemas/factory/v3/milestones.schema.json` |
| `A` | `schemas/factory/v3/owner-directives.schema.json` |
| `A` | `schemas/factory/v3/owner-override-policy.schema.json` |
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
| `A` | `scripts/gates/generate_sbom.py` |
| `M` | `scripts/gates/no_paid_usage.py` |
| `A` | `scripts/gates/source_of_truth_integrity.py` |
| `A` | `scripts/generate_product_schemas.py` |
| `A` | `scripts/generate_v3_legacy_migration.py` |
| `A` | `scripts/generate_v3_manifest.py` |
| `A` | `scripts/generate_v3_roadmap.py` |
| `A` | `scripts/generate_v3_schemas.py` |
| `M` | `scripts/recover_factory.sh` |
| `M` | `scripts/register_windows_autostart.ps1` |
| `M` | `scripts/resume_factory.sh` |
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
| `M` | `tcfactory/claude_runner.py` |
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
| `A` | `tcfactory/v3/base.py` |
| `A` | `tcfactory/v3/candidate_manifest.py` |
| `A` | `tcfactory/v3/configuration.py` |
| `A` | `tcfactory/v3/controller.py` |
| `A` | `tcfactory/v3/dispositions.py` |
| `A` | `tcfactory/v3/doctor.py` |
| `A` | `tcfactory/v3/enums.py` |
| `A` | `tcfactory/v3/external_evidence.py` |
| `A` | `tcfactory/v3/maturity.py` |
| `A` | `tcfactory/v3/migrations.py` |
| `A` | `tcfactory/v3/milestones.py` |
| `A` | `tcfactory/v3/pilot.py` |
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
| `M` | `tests/test_context_manifest.py` |
| `M` | `tests/test_control_scripts.py` |
| `M` | `tests/test_github_policy.py` |
| `M` | `tests/test_github_setup_script.py` |
| `M` | `tests/test_risk_routing.py` |
| `A` | `tests/test_sbom_generation.py` |
| `A` | `tests/test_source_of_truth_integrity.py` |
| `A` | `tests/test_v3_backends_and_checkpoints.py` |
| `A` | `tests/test_v3_candidate_salvage.py` |
| `A` | `tests/test_v3_config_and_roadmap.py` |
| `A` | `tests/test_v3_context_authority.py` |
| `A` | `tests/test_v3_controller_simulation.py` |
| `A` | `tests/test_v3_doctor_and_pilot.py` |
| `A` | `tests/test_v3_domain_models.py` |
| `A` | `tests/test_v3_github_workflows.py` |
| `A` | `tests/test_v3_legacy_migration.py` |
| `A` | `tests/test_v3_planning_context_and_support.py` |
| `A` | `tests/test_v3_prompt_contracts.py` |
| `A` | `tests/test_v3_publication_recovery.py` |
| `A` | `tests/test_v3_queue.py` |
| `A` | `tests/test_v3_scheduler_and_recovery.py` |
| `A` | `tests/test_v3_supervisor_and_status.py` |
| `M` | `tests/test_windows_autostart_scripts.py` |
| `M` | `uv.lock` |
<!-- END GENERATED FILE INVENTORY -->
