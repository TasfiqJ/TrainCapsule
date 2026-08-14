# Overall goal

Build and operate TrainCapsule as a **zero-human autonomous loop after one-time bootstrap**: the
factory must select bounded work, execute it, verify it through independent machine authority,
publish only through protected pull requests, install the exact verified result, recover from
ordinary faults, and continue useful unrelated work without a founder, operator, reviewer, browser
click, or manual receipt placement. Missing customer, payment, adoption, or other outside facts must
remain truthful `WAITING_EXTERNAL` states and must never be fabricated.

This goal preserves the bounded product, evidence, native-first, finite-recovery, and protected-release
requirements of the original V3 review bundle while deliberately superseding its qualified-human
runtime approval clauses with independent, signed, scoped, expiring, revocable machine authority.
That distinction is required because the original bundle explicitly requires qualified-human release
authority and forbids the factory from creating that approval itself; see
[00_EXECUTIVE_BUILD_DECISION_V3.md, sections 00.10–00.15](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3.md)
(lines 262–458),
[04_TECHNICAL_ARCHITECTURE_V3.md, section 04.16](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md)
(lines 717–745), and
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, sections 05.19–05.21](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 697–783). The correct conformance claim is therefore **“preserved or explicitly superseded
by V3.1-ZH,”** not “unchanged literal V3 conformance.”

## Document purpose and evidence rule

This is the remaining-work and final-acceptance plan. A feature is not complete merely because a
model, schema, unit test, or sidecar module exists. It is complete only when all applicable layers
are proven:

1. the requirement is mapped from the bundle;
2. the production call graph reaches the implementation;
3. positive and hostile tests pass;
4. installed bytes match the accepted source and manifest;
5. the live service performs the behavior under its real principal and permissions;
6. an immutable receipt or observation proves the exact SHA, tree, configuration, authority, and
   time window; and
7. recovery and rollback are demonstrated without human intervention.

This proof rule follows the bundle's provenance, completeness, identity, expiry, and minimum-verifier
requirements in
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, sections 05.3–05.5 and 05.17](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 85–213 and 639–662), its six-layer testing architecture in
[04_TECHNICAL_ARCHITECTURE_V3.md, section 04.21](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md)
(lines 856–926), and the static/dynamic/adversarial migration verification plan in
[SOURCE_OF_TRUTH_MIGRATION_PLAN.md, section 19](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
(lines 344–380).

## What is completed, briefly

The architecture and much of the implementation are complete and well tested:

- The entire review bundle is preserved: 31 files were audited, all 30 manifest payload hashes and
  byte counts match, all 1,211 headings were inspected, and all 109 roadmap IDs are unique. This
  satisfies the byte-preservation part of
  [FINAL_MANIFEST_V3.json](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FINAL_MANIFEST_V3.json)
  and the canonical hashing/integrity requirements in
  [SOURCE_OF_TRUTH_MIGRATION_PLAN.md, sections 9–10](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
  (lines 157–209).
- V3.1-ZH deterministically maps all 504 controlling V3 headings: 314 are preserved and 190 are
  explicitly superseded. Source, context, package, active-policy, roadmap, and schema gates pass.
  This implements the authority and context migration required by
  [SOURCE_OF_TRUTH_MIGRATION_PLAN.md, sections 4–7](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
  (lines 42–144).
- Active policy has no human runtime state or direct-main release dependency. Missing machine
  authority becomes `BLOCKED_POLICY`; missing outside truth becomes `WAITING_EXTERNAL`. This keeps
  external facts isolated as required by
  [FACTORY_LOOP_REDESIGN_SPEC.md, sections 7 and 16](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
  (lines 195–231 and 594–628).
- Finite planning, repair, redesign, restart, and completion-expansion budgets exist, and controller,
  queue, scheduler, checkpoint, backend, publication, verifier, canary, and deployment models have
  extensive hostile coverage. This matches
  [FACTORY_LOOP_REDESIGN_SPEC.md, sections 10–14 and 24–25](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
  (lines 309–594 and 894–964).
- Protected `main` currently requires pull requests, forbids bypass/force-push/deletion, requires
  exact checks including a separately identified Machine policy App, and has passed all required
  checks on current main. That is the release architecture required by
  [FACTORY_LOOP_REDESIGN_SPEC.md, sections 26–27](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
  (lines 965–1033) and
  [CODEX_MASTER_MIGRATION_PROMPT.md, Phase F](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md)
  (lines 876–945).
- The independent verifier, receipt brokers, GitHub token refresher, immutable runtime distribution,
  deployment refresh path, activation path, canary runner, and post-activation observer are installed
  and have real production call graphs. Their separation is aligned with the minimum external
  verifier and security boundaries in
  [05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, sections 05.28–05.30](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
  (lines 907–974).
- The broad local factory, product, verifier, canary, and deployment suite passed to 100%, alongside
  exact roadmap, source, policy, and schema generators. This is strong local implementation proof,
  although the bundle correctly requires live and external proof in addition to local tests; see
  [04_TECHNICAL_ARCHITECTURE_V3.md, sections 04.21 and 04.27](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md)
  (lines 856–926 and 1044–1072).
- The current product vertical implements evidence import, canonical identity, native-baseline
  capture, evidence completeness, and eligibility preflight. These are valid early parts of the
  workflow and native-first requirements in
  [03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md, sections 03.6–03.8](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md)
  (lines 179–427), but they are not the complete product.

## Verification of the additional-chat claims

| Claim from the additional chat | Current verified judgment | Why |
|---|---|---|
| The architecture is correct for zero-founder operation. | **Mostly correct.** | The active design uses independent machine authority, protected PRs, finite recovery, and external-fact isolation. The live safety failure described below prevents acceptance. This preserves the bounded factory doctrine in [FACTORY_LOOP_REDESIGN_SPEC.md, sections 7–10](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md) (lines 195–383). |
| Human approval is removed from active runtime. | **Correct by deliberate V3.1 supersession.** | It is not literal original-V3 compliance. Original V3 requires signed human approval in [04_TECHNICAL_ARCHITECTURE_V3.md, section 04.16](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md) (lines 717–745). V3.1 replaces it with independent machine authorization. |
| `autonomy.enabled: false` means autonomy was never activated. | **Misleading and now stale.** | Repository policy intentionally remains false; a signed activation transaction sets protected runtime autonomy true. The controller was live. The actual problem is that its authority later expired while it kept running. The original migration requires startup controls to fail closed in [CODEX_MASTER_MIGRATION_PROMPT.md, Phase G](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md) (lines 946–1001). |
| Phase 4 publication is only a design. | **Stale.** | The automated PR publisher, recovery state machine, exact-SHA checks, App token refresh, and protected-main policy are installed. Full machine-originated publication continuity is still not proven. The required behavior remains the PR-only sequence in [FACTORY_LOOP_REDESIGN_SPEC.md, section 26](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md) (lines 965–1006). |
| PR #25 was manually marked ready and merged. | **Correct.** | The GitHub timeline records `ready_for_review` and `merged` by `TasfiqJ`, with no `auto_merge_enabled` event. It proves checks and merge protection, not the complete zero-human publication path required by [SOURCE_OF_TRUTH_MIGRATION_PLAN.md, sections 16–17](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md) (lines 295–320). |
| The actual PR publisher must prove it uses the intended App identity. | **Correct.** | Code and installation are not enough; an exact live PR must bind branch creation, PR creation, checks, App identity, merge request, merged SHA, refresh, and continuation. This follows the exact evidence rule in [05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, sections 05.3 and 05.28](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md) (lines 85–127 and 907–934). |
| Claude autonomy is bounded by its credential. | **Correct, and currently a live problem.** | The controller logged `AUTH_EXPIRED`; retry exists, but automatic browserless renewal is not proven. Backend quota/auth states must pause and resume finitely under [FACTORY_LOOP_REDESIGN_SPEC.md, section 18](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md) (lines 681–715). |
| The product is not finished. | **Correct.** | The baseline/candidate runner, reduction engine, real GPU claim, commercial pack, and customer/paid-use evidence are not complete. The required workflow, comparison, pilot success, and product success contracts are in [03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md, sections 03.6, 03.12, 03.15, and 03.20](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md) (lines 179–196, 519–552, 631–659, and 766–779). |

## What remains: P0 safety and authority closure

### P0.1 Stop safely on expired or revoked activation authority

**Current defect.** The live activation and its machine-policy receipt expired. The activation
supervisor and independent observer now fail on every timer tick, but the controller continues
running. The observer does not catch `PublicVerificationError` because it inherits `RuntimeError`, so
the intended fail-closed stop path is skipped.

**Required work.**

1. Catch public-verifier authority failures at every continuous-observation and startup boundary.
2. On expiry, revocation, rollback, signature failure, path substitution, or authority race:
   - stop the controller before any further claim or publication action;
   - create or restore the authoritative `STOP` state;
   - write immutable failure and transition evidence;
   - quarantine any active candidate;
   - prevent an old activation transaction from being replayed;
   - retain enough evidence for automatic diagnosis and renewed authorization.
3. Add a pre-expiry renewal window. The machine-policy and activation pipelines must begin renewal
   before the old receipts expire. If renewal does not finish, the controller must stop before
   expiry rather than continue unauthorized.
4. Make the post-activation observer idempotently retire a completed observation instead of
   revalidating an old receipt forever.

This is mandatory under the expiry, revocation, and requalification law in
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, section 05.17](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 639–662) and its trust-stop conditions in section 05.30 (lines 957–974).

**Acceptance proof.** Use deliberately short-lived receipts. Prove that renewal succeeds without
human action; prove that failed renewal stops the controller before expiry; revoke the active receipt
and prove the controller stops; roll the revocation epoch backward and prove rejection; restart all
services and prove an expired transaction cannot reactivate the controller.

### P0.2 Close V3.1 migration milestone M0 truthfully

**Current defect.** The authoritative roadmap still marks `M0_FACTORY_MIGRATED` active. V3-MIG-012
through V3-MIG-015 are proposed, V3-MIG-016 is blocked by policy, V3-MIG-017 through V3-MIG-020 are
proposed, and the five migration evidence records remain `PENDING_FINALIZATION`. The migration gate
fails and the finalizer reports missing independent M0 receipts.

**Required work.**

1. Produce the exact signed source-migration machine authorization for V3-MIG-016.
2. Run and bind the exact restart/recovery rehearsal for V3-MIG-017.
3. Produce observation-mode controller proof for V3-MIG-018.
4. Complete one mechanical and one standard work item through the real automated PR pipeline for
   V3-MIG-019, binding candidate manifests, exact required checks, machine-policy receipts, PRs,
   merged-main SHAs, and installed runtime refresh evidence.
5. Run full pre-evidence acceptance, finalize V3-MIG-020, then rerun complete acceptance without a
   circular self-reference.
6. Transition M0 to completed only after the independent evaluator accepts every exit criterion and
   move the active milestone according to the generated roadmap—never by editing status alone.

The exact M0 exit intent and stop conditions are specified in
[12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md, section 12.3](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md)
(lines 49–98), while final migration acceptance and rollback are specified in
[SOURCE_OF_TRUTH_MIGRATION_PLAN.md, sections 20–21](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
(lines 381–415).

**Acceptance proof.** `scripts/gates/v3_migration_evidence.py` must pass; all V3-MIG-012 through
V3-MIG-020 work items must have terminal evidence accepted by the typed completion policy; no
`PENDING_FINALIZATION` M0 record may remain; the milestone evaluator must independently derive M0
completion from immutable evidence.

### P0.3 Prove noninteractive backend credential continuity

**Current defect.** Claude backend state reached `AUTH_EXPIRED`. Periodic retry is not credential
renewal and does not prove zero-human continuation.

**Required work.** Provide one of these machine-operable, policy-approved paths:

- an independently managed service credential with automatic renewal;
- a root-owned credential broker that renews and atomically promotes short-lived controller-readable
  credentials without exposing them to candidate agents; or
- a pre-authorized backend failover that preserves task/checkpoint semantics and uses no founder
  account, browser login, API-key substitution, or weaker provider path.

If the upstream service fundamentally requires periodic human renewal, that dependency must be
classified as an external bootstrap limitation. The controller must pause affected work truthfully,
continue unrelated lanes, and never claim indefinite zero-human operation. This matches the bounded
quota/model policy in
[FACTORY_LOOP_REDESIGN_SPEC.md, sections 17–18](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 629–715) and the backend-neutral executor requirement in
[CODEX_MASTER_MIGRATION_PROMPT.md, Phase E](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md)
(lines 832–875).

**Acceptance proof.** Expire the credential during a real task, prove no prompt or browser appears,
prove the task becomes a typed finite wait without spending repair budget, renew or fail over
automatically, and prove the exact checkpoint resumes without duplicate external or publication
side effects.

### P0.4 Establish cold-boot and process-restart autonomy

**Current defect.** The controller unit is disabled and configured without direct systemd restart;
its recovery depends on the activation supervisor, which is currently failing. Windows Automatic
Activation and Lights-Out tasks are disabled, while the enabled GitHub Runner task uses an
interactive-login principal. Cold boot before a person logs in is unproven.

**Required work.**

1. Select one canonical boot owner and eliminate ambiguous competing Windows/WSL launch paths.
2. Start the root verifier/broker/timer graph and the controller-start broker without interactive
   login.
3. Keep the controller disabled until exact LIVE activation, but ensure the activation supervisor
   itself starts automatically and can renew authority.
4. Use bounded restart/backoff, a durable restart ledger, healthy-window reset, and `HARD_STUCK` for
   exhausted recovery.
5. Prove shutdown, WSL restart, Windows reboot, controller kill, broker kill, and observer kill.

The expected startup replacement and bounded restart doctrine are in
[FACTORY_LOOP_REDESIGN_SPEC.md, section 25](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 935–964), and the original migration explicitly requires portable controls and bounded
startup in
[CODEX_MASTER_MIGRATION_PROMPT.md, Phase G](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md)
(lines 946–1001).

**Acceptance proof.** From a powered-off machine, boot without logging into the founder account.
Observe the verifier graph, renewal path, activation supervisor, exact authorization, controller
start, task selection, and a complete idle/work cycle. Repeat after forced process kills and verify
the restart budget and journal prevent duplicate work.

### P0.5 Run all mandatory canaries successfully on the exact installed SHA

**Current defect.** The available 20-canary suite is entirely `BLOCKED_PREREQUISITE` because the
disposable repository clone failed. It does not prove process recovery, auth recovery, receipt
expiry/revocation, milestone advancement, publication recovery, or automated revert.

**Required work.** Repair the disposable clone/runtime setup without weakening its isolation. Every
canary must execute its real mechanism using exact installed binaries, policies, roots, and
credentials. A blocked or synthetic result is not a pass.

This follows the controlled/adversarial/external testing layers in
[04_TECHNICAL_ARCHITECTURE_V3.md, section 04.21](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md)
(lines 856–926) and the required regression categories in
[FACTORY_LOOP_REDESIGN_SPEC.md, section 31](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 1139–1191).

**Acceptance proof.** All 20 IDs must report PASS with reopened artifact hashes, exact main/tree,
installed runtime manifest, controller digest, source-generation digest, and independent receipt
bindings. No canary may inherit a test fixture, fake backend result, or mutable repository-local
authority.

## What remains: P1 complete the autonomous release and refresh loop

### P1.1 Produce a genuinely machine-originated protected PR

PR #25 proved required checks and protected merge behavior, but the user account marked it ready and
merged it. The zero-human loop still needs a real transaction where the machine:

1. selects and completes a bounded work item;
2. freezes the exact candidate SHA and tree;
3. pushes a candidate branch with the scoped GitHub App credential;
4. opens and marks the PR ready;
5. waits for exact-head required checks;
6. obtains the independent machine-policy check;
7. requests auto-merge;
8. lets GitHub perform the merge without the user account;
9. verifies exact merged `main`;
10. promotes the signed anchor bundle;
11. refreshes the immutable source/runtime generation;
12. obtains fresh activation authority; and
13. starts the next eligible task without a click.

This is the concrete implementation of
[FACTORY_LOOP_REDESIGN_SPEC.md, section 26](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 965–1006) and the GitHub migration requirements in
[SOURCE_OF_TRUTH_MIGRATION_PLAN.md, section 16](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
(lines 295–305).

**Acceptance proof.** GitHub timeline actors, App IDs, check suites, auto-merge event, merge actor,
exact SHAs, root-promoted bundle, refresh completion, fresh activation, seven-event observation, and
next scheduler decision must all bind the same transaction. No event may be performed by `TasfiqJ`
or another person.

### P1.2 Exercise crash recovery at every publication and deployment boundary

For each durable phase—prepared, branch pushed, PR open, checks pending, policy pending, auto-merge
requested, merged, exact-main verified, anchor promoted, refresh switching, refresh committed,
activation requested, activated, start requested—kill the responsible process before and after its
journal write. Recovery must either continue idempotently or stop with immutable `HARD_STUCK`
evidence; it must never duplicate a PR, merge, external action, receipt, or runtime switch.

This implements candidate preservation and deterministic recovery from
[FACTORY_LOOP_REDESIGN_SPEC.md, sections 13–14](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 460–594) and rollback requirements in
[SOURCE_OF_TRUTH_MIGRATION_PLAN.md, section 20](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
(lines 381–401).

### P1.3 Prove automated post-merge invariant failure and revert PR

Deliberately introduce a candidate that passes pre-merge controls but fails a declared post-merge
invariant. The machine must create a normal protected revert PR, run the same exact-SHA checks and
machine authority, merge it without direct-main mutation, restore the verified anchor/runtime, and
continue or enter a bounded stop.

This is required by the protected release and recovery architecture in
[FACTORY_LOOP_REDESIGN_SPEC.md, sections 26–27](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 965–1033) and the trust correction process in
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, section 05.24](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 820–837).

## What remains: P1 durable truth and no-forgetting

The following documents currently describe an old stopped candidate and contradict the installed
live system:

- `docs/migrations/V3_1_ZH_CODEX_EXECUTION_STATE.md`;
- `docs/migrations/V3_1_ZH_REMAINING_ACCEPTANCE.md`;
- `docs/migrations/V3_MIGRATION_REPORT.md`; and
- `docs/migrations/V3_1_ZH_158_ROW_FINDINGS_LEDGER.json`.

The 158-row ledger remains bound to old candidate `0fa90da…`, reports zero proven-final rows, says
activation is unauthorized, and says the controller must remain stopped. Conversely, the current
controller was active, even though M0 evidence remains unfinished. Both sides of that contradiction
must be reconciled without rewriting historical facts.

**Required work.**

1. Freeze the existing Phase-0 and candidate records as explicitly named historical snapshots.
2. Generate a new current-state evaluation bound to current main, tree, installed runtime, source
   generation, GitHub ruleset observation, receipts, canaries, and service status.
3. Give every one of the 158 rows an explicit current classification, proof digest roster, rollback
   behavior, and acceptance state. No blanket carry-forward is allowed.
4. Update the execution state, remaining acceptance, migration report, README, and test matrix from
   the same generated evidence source.
5. Add a gate that fails when a document labeled “current” is bound to a different main/runtime or
   contradicts live activation/M0 state.

This is required by the durable state and no-forgetting migration in
[CODEX_MASTER_MIGRATION_PROMPT.md, section 8.12](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md)
(lines 799–831), the source authority conflict rules in
[SOURCE_OF_TRUTH_MIGRATION_PLAN.md, sections 5–8](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
(lines 70–156), and the truth model in
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, section 05.2](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 25–84).

**Acceptance proof.** A clean-checkout generator check must reproduce all current-status documents.
Mutating main SHA, activation status, receipt expiry, M0 state, or service health in a temporary copy
must fail the gate. Historical snapshots must remain byte-identical.

## What remains: P2 complete the TrainCapsule product

The autonomous factory is not the product. Product completion still requires the bounded
Incident-to-Change Qualification workflow and its evidence outputs.

### P2.1 Implement the baseline/candidate execution and comparison vertical

Build the real local runner, pack-specific experiment planner, baseline/candidate comparison,
execution records, and qualification decision path. Every run must bind workload/environment
identity, native baseline, evidence completeness, candidate SHA, artifact CAS, limitations, and
expiry. This is specified in
[04_TECHNICAL_ARCHITECTURE_V3.md, sections 04.10–04.13](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md)
(lines 549–667) and the output contract in
[03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md, section 03.7](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md)
(lines 197–355).

### P2.2 Complete reduction, independent oracle, and negative controls

Implement the registered legal-reduction operators, monotonic truth rule, raw artifact roster,
content-pinned independent oracle, faithfulness dimensions, and economic limit. A reduction result
must not be accepted from caller-authored aggregates or booleans. This is specified in
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, sections 05.10–05.13](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 335–519).

### P2.3 Complete Recovery Assurance and the initial incident pack

Implement named restart/resume/failover recovery properties, reference acquisition, aggregation,
and the `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1` pack with exact applicability and checkpoint policy.
The required product and trust contracts are in
[03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md, sections 03.8–03.9](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md)
(lines 356–448) and
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, sections 05.14 and 05.26–05.27](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 520–572 and 857–906).

### P2.4 Reconcile the remaining bundle templates into typed production artifacts

The following bundle concepts remain partial or lack proven production consumers:

- a typed pricing-experiment artifact equivalent to
  [examples/market/pricing-experiment.template.yaml](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/market/pricing-experiment.template.yaml);
- the full authority/access fields from
  [examples/product/qualification-pilot-intake.template.yaml](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/product/qualification-pilot-intake.template.yaml);
- a proven controller consumer and completion binding for the pilot qualification rubric; and
- a generated, evidence-bound customer-local checklist equivalent to
  [examples/product/customer-local-security-checklist.md](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/examples/product/customer-local-security-checklist.md).

The completed artifacts must remain attributable and must not turn research templates into customer
facts. That constraint follows the discovery and claims policy in
[03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md, sections 03.17–03.19](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md)
(lines 700–765) and the commercial proof hierarchy in
[06_COMMERCIAL_MODEL_AND_GTM_V3.md, sections 06.11–06.16](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/06_COMMERCIAL_MODEL_AND_GTM_V3.md)
(lines 379–605).

### P2.5 Obtain real GPU, customer, payment, repeat, and support evidence

These are outside facts, not code tasks. They may be acquired through separately authorized
zero-human external-action channels, but they may never be invented by the controller. Until they
exist, the corresponding work remains `WAITING_EXTERNAL`, while unrelated engineering continues.

Required evidence includes real complete-substitute benchmarking, a paid pilot, changed customer
decision, a second paid action, same-family repeatability, support acceptance, and decreasing
founder/operator delivery dependence. These requirements are in
[03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md, sections 03.12, 03.15, and 03.20](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md)
(lines 519–552, 631–659, and 766–779) and
[06_COMMERCIAL_MODEL_AND_GTM_V3.md, sections 06.15–06.17 and 06.29](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/06_COMMERCIAL_MODEL_AND_GTM_V3.md)
(lines 507–623 and 898–910).

## Required implementation order

The remaining work must be executed in this order so later evidence is not built on unsafe or stale
authority:

1. **Fail closed on expired/revoked authority.** Stop the currently unauthorized continuity path.
2. **Implement automatic authority renewal.** Prove renewal and failed-renewal stop behavior.
3. **Repair noninteractive credential and cold-boot continuity.** No browser or founder login.
4. **Repair and pass all 20 canaries on the exact installed SHA.**
5. **Complete V3-MIG-012 through V3-MIG-020 and close M0.**
6. **Run a machine-originated protected PR, refresh, reactivation, and next-task cycle.**
7. **Run publication/deployment crash matrices and the automated revert PR.**
8. **Regenerate the durable current-state documents and 158-row ledger.**
9. **Complete the product runner, reduction, recovery, pack, and typed market/pilot artifacts.**
10. **Collect real external/commercial evidence without blocking unrelated lanes.**

This sequencing respects the original migration order in
[FACTORY_LOOP_REDESIGN_SPEC.md, section 32](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 1193–1263) while applying the V3.1 zero-human machine-authority substitution.

## How to determine that the zero-human loop is perfect now

“Perfect now” means **every** item below passes on one exact immutable main SHA and installed runtime.
There is no partial-credit activation.

### A. Repository and migration acceptance

- All bundle, V3.1 package, source-authority, active-policy, roadmap, schema, inventory, and legacy
  migration generators pass from a clean checkout.
- The complete test suite, Ruff, and strict Pyright pass.
- The migration-evidence gate passes; M0 is completed by the evaluator; V3-MIG-012 through 020 are
  terminal and independently evidenced.
- Every current-status document and every 158-row record is bound to the exact accepted main/tree and
  truthfully classified.
- Historical source and Phase-0 evidence remain byte-identical.

These checks implement the final migration acceptance list in
[SOURCE_OF_TRUTH_MIGRATION_PLAN.md, section 21](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/SOURCE_OF_TRUTH_MIGRATION_PLAN.md)
(lines 402–415) and the required test matrix in
[CODEX_MASTER_MIGRATION_PROMPT.md, section 16](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md)
(lines 1263–1320).

### B. Installed authority and service acceptance

- `systemctl --failed` reports zero failed TrainCapsule units.
- Exact installed files, roots, owners, modes, executable inodes, runtime dependency inventory, and
  source snapshot match signed manifests.
- Machine-policy, activation, ruleset, revocation, and external-evidence authorities are current,
  monotonic, non-replayable, and automatically renewed before expiry.
- Receipt expiry or revocation stops the controller before another claim or publication action.
- Cold boot and WSL restart reach authorized operation without interactive login.
- Backend credential expiry renews or fails over without a prompt; otherwise affected work pauses
  truthfully while unrelated lanes continue.

This is the installed security and supportability standard in
[04_TECHNICAL_ARCHITECTURE_V3.md, sections 04.17–04.18 and 04.23](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/04_TECHNICAL_ARCHITECTURE_V3.md)
(lines 747–805 and 941–965).

### C. Mandatory live fault acceptance

- All 20 mandatory canaries pass on the exact installed SHA.
- Kill the controller and every broker/worker at every durable publication/refresh/activation phase;
  each resumes idempotently or stops safely.
- Expire a GitHub token and prove automatic refresh.
- Expire and revoke machine-policy and activation receipts and prove renewal-or-stop.
- Simulate Claude quota and authentication expiry and prove typed pause/resume without repair-budget
  consumption.
- Submit a malicious or invalid candidate and prove rejection before branch publication.
- Trigger post-merge invariant failure and prove an automated protected revert PR.
- Keep one lane in `WAITING_EXTERNAL` and prove eligible unrelated lanes continue.

These tests directly instantiate the scheduler, retry, external-truth, release, context, and completion
regressions required by
[FACTORY_LOOP_REDESIGN_SPEC.md, section 31](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 1139–1191).

### D. End-to-end zero-human publication acceptance

At least three consecutive machine-originated cycles must complete this exact chain with no user
timeline event, terminal prompt, browser action, service restart, receipt placement, or credential
copy:

```text
scheduled controller event
→ bounded task selection
→ noninteractive backend execution
→ frozen candidate and independent gates
→ App-authenticated branch and PR
→ exact-head required checks
→ independent machine-policy check
→ machine-requested auto-merge
→ GitHub protected merge
→ exact merged-main verification
→ signed anchor promotion
→ atomic immutable runtime refresh
→ fresh machine-policy and LIVE activation
→ ordered seven-event observation
→ next eligible task starts
```

After the three cycles, run a minimum 72-hour unattended soak covering timer rotation, credential
refresh, external waits, idle cycles, and at least one controlled process restart. The three-cycle and
72-hour thresholds are explicit project acceptance thresholds, not claims that the original bundle
specified those exact numbers. They operationalize the bundle's healthy-factory requirement of no
manual babysitting for ordinary recoverable failures in
[FACTORY_LOOP_REDESIGN_SPEC.md, section 33](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md)
(lines 1264–1289).

### E. Product and commercial acceptance

- The complete bounded runner/reduction/recovery/qualification vertical passes unit, contract,
  controlled integration, adversarial, journey, and applicable external tests.
- Baseline/candidate comparison is exact, native-first, applicability-bounded, and independently
  reproducible.
- No GPU/native-advantage claim exists without real GPU evidence.
- No customer, payment, adoption, value, repeat, or support claim exists without attributable signed
  external evidence.
- A paid customer decision changes, a second paid action occurs, the same-family case repeats, and a
  non-founder operator can deliver the pack within the defined economics.

This is the product-success boundary in
[03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md, section 03.20](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md)
(lines 766–779), the commercial C0–C6 gate model in
[06_COMMERCIAL_MODEL_AND_GTM_V3.md, section 06.16](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/06_COMMERCIAL_MODEL_AND_GTM_V3.md)
(lines 535–605), and the M0–M6 roadmap in
[12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md, sections 12.3–12.9](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md)
(lines 49–351).

## Forbidden shortcuts

The following must never be used to obtain a green result:

- direct push or force-push to `main`;
- a user account manually marking ready, enabling merge, or merging;
- candidate/controller access to verifier private keys or GitHub App private credentials;
- local self-authored machine-policy, activation, external-evidence, customer, payment, or commercial
  receipts;
- converting `UNKNOWN`, `BLOCKED_POLICY`, `WAITING_EXTERNAL`, or `BLOCKED_PREREQUISITE` into PASS;
- treating a schema-valid document, unit test, mock backend, or local simulation as live proof;
- disabling expiry, revocation, canaries, ruleset checks, private gates, post-merge invariants, or
  rollback to keep the loop moving;
- marking M0/M1–M6 complete by editing YAML status rather than evaluating evidence;
- claiming permanent autonomy while a credential requires periodic manual browser renewal; or
- letting a blocked external/customer lane stop unrelated eligible engineering work.

These prohibitions follow the bundle's native-first and truth rules in
[14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md, sections Native-first, Truth rules, Human authority, and Stop conditions](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md)
(lines 76–153 and 398–415), its AI-role limitations in
[05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md, section 05.21](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md)
(lines 757–783), and the no-fabrication requirement in
[CODEX_MASTER_MIGRATION_PROMPT.md, section 1](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md)
(lines 43–61).

## Final completion statement

TrainCapsule may be called a **proven zero-human autonomous loop after bootstrap** only after sections
A through D pass simultaneously on one exact installed generation. It may be called a **completed
commercial product** only after section E also passes with real external evidence. Until then, the
truthful designation is:

> **Zero-human architecture substantially implemented; live authority continuity, M0 migration
> closure, unattended publication/restart proof, and the complete product remain unfinished.**

## Remediation checkpoint — 2026-08-14 initial revalidation

This checkpoint is a current observation, not a completion claim.

- Baseline `main` and `origin/main` both resolved to
  `5c9a9bca4cc53d7f6002c5ee3392293e9a61a4a8`; the exact tree was
  `0ebe5aa3095087736921c5a3b3dacbfaa12f576a`.
- The working branch is `codex/v31-zh-fail-closed-remediation`. Existing untracked canary,
  archive, download-metadata, and plan files were preserved.
- The authoritative V3 bundle integrity gate passed for all 30 manifest payloads. The complete
  31-file bundle was re-inventoried and read; the attached completion plan and this repository copy
  matched at SHA-256
  `cd3bc53dec1a768f7b4f431c4af15772f5683ac9ebf785b20de650b2aaaec682` before this update.
- Live system observation found the controller inactive/disabled with `Restart=no`, while
  `traincapsule-activation-supervisor.service` and
  `traincapsule-verifier-post-activation-observer.service` were failed and still timer-triggered.
- The selected LIVE activation receipt was `ACT:A5AD25CAF776EF40FB1C161B5CEE1282`, bound to
  machine-policy receipt `MPOL:397B02B306D663302566090AE573F35A` and exact main
  `5c9a9bca4cc53d7f6002c5ee3392293e9a61a4a8`. It expired at
  `2026-08-14T12:02:01.409934Z`; later observer logs rejected it as expired. Its receipt-bound
  controller binary digest was
  `sha256:504e08c2ccd14c9317cc9edf91a2da584b4c85f2b6b5451f8e8f4175e007ad99`.
  Direct root-only runtime inspection was unavailable to this session, so that digest is not yet
  claimed as a fresh installed-byte measurement.
- The available 20-canary suite at `CANARY-20260814T042527Z-DBA334529978/suite.json` remained
  `BLOCKED_PREREQUISITE` across every result; no blocked result was promoted.
- GitHub ruleset `20794549` was active for `main`, had no bypass actors, required pull requests and
  strict status checks, and bound eight GitHub Actions checks to integration `15368` plus
  `TrainCapsule / Machine policy` to integration `4580794`.

Implemented source correction:

- `PublicVerificationError` is now caught by both the post-activation observer's fail-closed
  transition and its command boundary. This closes the confirmed exception-type escape that
  previously skipped controller stop, STOP restoration, and the failure journal.
- Added a regression test proving the command boundary reports a public authority rejection as a
  fail-closed failure.
- Added a root-enforced 900-second pre-expiry safety window. The observer derives the earliest
  deadline across the LIVE activation receipt, its linked machine-policy receipt, and the active
  revocation authority. Entering the window invokes the same journaled controller stop and durable
  STOP restoration before authority expires. This is source-level stop-before-expiry proof only;
  successful independent renewal and reactivation remain unproven.

Verification completed:

```text
uv run pytest verifier/tests/test_post_activation_observer.py tests/test_v31_activation_and_canaries.py -q
26 passed

uv run ruff check verifier/src/traincapsule_verifier/post_activation_observer.py verifier/tests/test_post_activation_observer.py
All checks passed!

uv run python scripts/gates/v3_bundle_integrity.py
PASS: authoritative V3 bundle covers and matches all 30 payload files

uv run pytest verifier/tests/test_post_activation_observer.py verifier/tests/test_service_bootstrap.py -q
26 passed

uv run pyright verifier/src/traincapsule_verifier/post_activation_observer.py verifier/src/traincapsule_verifier/bootstrap.py verifier/tests/test_post_activation_observer.py
0 errors, 0 warnings, 0 informations
```

Repository-wide revalidation after the safety-window change also passed the complete pytest suite,
full Ruff, strict Pyright, V3.1 source generation (11 documents and 504 mapped headings), V3.1
package integrity, source-authority integrity, active-policy integrity (282 files), roadmap and V3/V3.1
schema generation (63 V3.1 schemas), legacy migration generation (124 entries), and the regenerated
644-path migration inventory. The migration-evidence gate remained truthfully red with:

```text
FAIL: V3-MIG-016 is pending; run .venv/bin/python scripts/finalize_v3_1_zh_m0_evidence.py
```

The finalizer was not used to invent or self-author the missing independent authority.

Remaining immediate blocker and next action: the installed runtime still contains the old observer
bytes, and normal authority renewal does not yet exist. Implement and hostile-test pre-expiry
machine-policy/activation renewal with a stop-before-expiry deadline, then publish only through the
protected machine-authorized path and verify the exact installed result.

That designation preserves the bundle's requirement to continue the company while replacing the
unsafe plan, finite factory, and premature claims described in
[README_FIRST.md](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/README_FIRST.md)
(lines 9–110) and the final authorization in
[00_EXECUTIVE_BUILD_DECISION_V3.md, section 00.18](../../TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11/traincapsule_v3_review_2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3.md)
(lines 498–519), while honoring the later controlling zero-human amendment.
