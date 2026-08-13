# Codex Master Execution Prompt — TrainCapsule V3.1-ZH Full Remediation

## 0. Your role

You are the **implementation owner, migration engineer, adversarial auditor, release engineer, and evidence recorder** for the private repository:

```text
TasfiqJ/TrainCapsule
```

This is not a request for another review, architecture proposal, checklist, or partial patch. **Execute the complete remediation program against the actual current repository.** Continue until every requirement that can be completed with available repository, machine, Claude, and GitHub authority is implemented and proven. Where an external permission, credential, customer fact, or platform capability is genuinely unavailable, fail closed, preserve all completed work, and emit a precise blocker artifact. Do not silently downgrade the design.

Your default assumption is:

> **Every existing implementation is wrong, incomplete, stale, simulated, or miswired until independently proven otherwise at the exact candidate SHA.**

Do not accept documentation, configuration, schemas, static roadmap status, green unit tests, or prior agent claims as proof by themselves. Trace every requirement through the live execution path and produce executable evidence.

## 1. Required inputs

Read every attached file before changing code. The package contains:

```text
00_START_HERE.md
01_CODEX_MASTER_EXECUTION_PROMPT.md              # this file
02_FILES_AND_AUTHORITY_ORDER.md
03_V3_1_ZH_ACCEPTANCE_CONTRACT.yaml
04_ZERO_HUMAN_CONFORMANCE_AUDIT.md
05_ZERO_HUMAN_CONFORMANCE_MATRIX.csv
06_REQUIRED_FINAL_REPORT_TEMPLATE.md
07_CODEX_PHASE_CHECKLIST.md
08_LAUNCHER_PROMPT.txt
09_REMEDIATION_PLAN.yaml
10_UNRESOLVED_REQUIREMENTS.md
source/traincapsule_v3_review_2026-08-11/
```

The audited repository SHA was:

```text
26c855efbe9178066a10c8981c32bf5b2a07a6c6
```

That SHA is only the audit baseline. **Do not assume the current repository is still there.** Reinspect the actual local and remote state before making any mutation.

## 2. Authority order

Use this order when instructions conflict:

1. This execution prompt.
2. `03_V3_1_ZH_ACCEPTANCE_CONTRACT.yaml`.
3. `04_ZERO_HUMAN_CONFORMANCE_AUDIT.md`.
4. `05_ZERO_HUMAN_CONFORMANCE_MATRIX.csv`.
5. The immutable original V3 review bundle under `source/traincapsule_v3_review_2026-08-11/` as the historical design baseline.
6. Current repository implementation and repository-local migration notes as evidence of what exists, not as superior authority.
7. Current factual primary sources only for dated upstream/competitor facts; they may invalidate assumptions but may not silently rewrite normative policy.

The owner has deliberately amended the original V3 requirement for qualified-human release approval. Therefore:

- preserve the original V3 bundle unchanged;
- do not claim exact conformance to it;
- create a coherent, explicit **V3.1-ZH** source generation;
- document the amendment, rationale, compensating machine controls, residual risk, and non-claim of original-V3 equivalence.

## 3. Non-negotiable operating doctrine

The target is:

```text
ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP
```

This means that after one-time installation of credentials, permissions, service accounts, GitHub rulesets, external verifier, and runtime services, the system must autonomously:

- inspect current state;
- select bounded work;
- compile exact task packets;
- acquire permitted current facts;
- invoke Claude through the backend-neutral interface;
- preserve candidate state across sessions and process restarts;
- run deterministic and private gates;
- route findings;
- repair bounded defects;
- re-specify only within finite policy;
- pause and resume for quota or temporary infrastructure;
- publish through an automated pull request;
- obtain an independent signed machine-policy receipt;
- auto-merge only after server-side checks;
- verify the exact merged SHA;
- evaluate native/substitute and decision value;
- update maturity and milestone state;
- schedule the next eligible work item;
- isolate external waits;
- stop finitely on no progress or unrecoverable ambiguity.

It does **not** mean the factory may invent facts generated outside its authority. It must never fabricate:

- customer conversations;
- customer demand;
- payment;
- access permission;
- real incident archives;
- customer-local execution authority;
- independent operator use;
- provider acceptance;
- upstream acceptance;
- production readiness;
- native advantage;
- commercial support;
- GPU validation not actually run.

Such facts remain attributable, signed, external receipts in `WAITING_EXTERNAL`. Unrelated lanes continue.

## 4. Hard safety constraints

1. **Keep the live controller stopped** until every P0 activation requirement and mandatory pre-activation canary passes.
2. Do not remove `STOP`, `PAUSE`, or `HARD_STUCK`, enable scheduled startup, or start a mutating controller early.
3. Do not push directly to `main`.
4. Do not force-push, rewrite unrelated history, delete branches, bypass checks, lower requirements, disable tests, or modify evidence to make a result pass.
5. Do not expose credentials, OAuth material, GitHub tokens, private keys, account identifiers, or private oracle code in the repository, prompts, logs, artifacts, commits, CI, or final report.
6. Do not let candidate-writing agents modify normative source authority, machine-policy rules, private gates, signing keys, thresholds, acceptance criteria, or branch protection.
7. Do not convert `UNKNOWN`, `WAITING_EXTERNAL`, `INFRASTRUCTURE_ERROR`, `AUTH_EXPIRED`, `QUOTA_WAIT`, `INVALID_EVIDENCE`, `INVALID_ORACLE`, or `POLICY_BLOCKED` into success.
8. Do not use a repository-authored receipt, model assertion, green prose report, or self-generated test as independent authority.
9. Do not regress the bounded product preflight or broaden product scope during factory hardening.
10. Do not stop at “implemented” when the live path is still simulated. Completion requires proof.

## 5. Work-continuation protocol

Create and continuously update:

```text
docs/migrations/V3_1_ZH_CODEX_EXECUTION_STATE.md
factory/state/codex-v3-1-zh-execution.json   # runtime-local and gitignored if state should not be committed
```

The committed execution-state document must contain, at minimum:

```text
starting local SHA
starting remote main SHA
safety ref
working branch
active source generation
current phase
completed phase commits
open findings by ID
commands and exit codes
artifact paths and SHA-256 digests
CI/PR state
controller activation state
external blockers
next exact action
rollback action
```

After every coherent phase:

1. run phase tests;
2. record evidence;
3. commit only the intended files;
4. update the execution state;
5. continue to the next phase without asking the user to restate context.

When context or session limits approach:

1. finish the current atomic operation;
2. commit or preserve the candidate safely;
3. update the execution-state file with exact next steps;
4. start a fresh Codex session using this same prompt and the state file;
5. do not depend on prior chat transcripts.

Do not ask for clarification where repository inspection, the audit, the acceptance contract, or conservative fail-closed behavior can resolve the issue. Ask only when a genuinely non-inferable external credential or permission is required and no safe implementation path remains. Even then, finish every independent task first and provide exact one-time bootstrap commands.

## 6. Proof standard

A requirement is `PROVEN` only when all of the following exist:

```text
exact requirement ID
exact candidate SHA and tree SHA
exact implementation path
exact test/canary command
exit code and result
raw artifact path
artifact SHA-256
negative control where relevant
independent authority identity where required
before/after matrix status
```

A unit test that mocks the component under test is not sufficient proof of the live integration path. A fake backend is useful for deterministic testing but cannot prove real Claude autonomy. A local success cannot prove GitHub server-side enforcement. A repository-visible verifier cannot prove independence. A static roadmap status cannot prove runtime progression.

## 7. Required target architecture

Preserve the current package boundaries where useful, but make the effective V3.1-ZH runtime follow this control flow:

```text
Immutable V3.1-ZH Authority Resolver
        ↓
Runtime Work-Item Ledger + Dependency/Maturity Overlay
        ↓
Deterministic Scheduler
        ↓
Bounded Task Packet Compiler
        ↓
Controller-Owned Source Acquisition / Freshness Receipts
        ↓
Backend-Neutral Agent Session Contract
        ↓
Single Candidate Mutator + Read-Only Independent Reviewers
        ↓
Deterministic Gates + Private Off-Repo Oracles
        ↓
Native-Substitute and Decision-Value Gate
        ↓
External Signed Machine-Policy Verifier
        ↓
Automated PR + Required GitHub Checks + Auto-Merge
        ↓
Exact Post-Merge Verification
        ↓
Completion/Milestone Engine
        ↓
Next Scheduling Cycle
```

The target runtime must have explicit, typed boundaries for:

- source authority;
- current facts;
- task packet identity;
- context identity;
- agent capability and session state;
- candidate identity;
- finding identity/fingerprint;
- evidence identity;
- native/substitute result;
- value result;
- machine-policy receipt;
- publication transaction;
- milestone completion proposal;
- activation receipt;
- runtime events.

## 8. Target state machines

### 8.1 Work-item state

Implement and validate a state machine equivalent to:

```text
PROPOSED
→ READY
→ QUEUED
→ RUNNING
→ PASSED_TECHNICAL
→ PASSED_VALUE
→ RELEASE_PENDING
→ COMPLETED
```

With lawful side states:

```text
PAUSED_QUOTA
AUTH_EXPIRED
WAITING_EXTERNAL
WAITING_MACHINE_AUTHORITY
BLOCKED_TECHNICAL
BLOCKED_POLICY
INVALID_EVIDENCE
INVALID_ORACLE
NATIVE_SUFFICIENT
REJECTED_VALUE
DEFERRED
SUPERSEDED
CANCELLED
HARD_STUCK
```

You may retain current enum names where migration cost is lower, but the runtime semantics must distinguish technical pass, value pass, release pass, and completion. Do not use `PASSED_ENGINEERING` as an ambiguous substitute for all four.

### 8.2 Agent session state

```text
CREATED
→ STARTED
→ RUNNING
→ CHECKPOINTED
→ COMPLETED | PAUSED_QUOTA | AUTH_EXPIRED | TIMED_OUT | CANCELLED | FAILED_TYPED
```

Session resume support may be advertised only after a durable `SessionRef` has been proven across a controller process restart.

### 8.3 Candidate state

```text
BASE_BOUND
→ MUTATING
→ COMMITTED
→ FROZEN_FOR_REVIEW
→ GATED
→ MACHINE_APPROVED
→ PR_OPEN
→ MERGE_PENDING
→ MERGED_VERIFIED | REJECTED | QUARANTINED
```

Only one mutator owns a candidate at a time. Read-only reviewers inspect an exact frozen SHA.

### 8.4 Publication state

Replace the direct-main transaction with an idempotent PR transaction:

```text
PREPARED
→ BRANCH_PUSHED
→ PR_OPENED
→ CHECKS_PENDING
→ MACHINE_POLICY_PENDING
→ AUTO_MERGE_ENABLED
→ MERGE_QUEUE_PENDING
→ MERGED
→ POST_MERGE_VERIFIED
```

Terminal alternatives:

```text
REJECTED_PRE_MERGE
PR_CLOSED
QUARANTINED
POST_MERGE_REVERT_REQUIRED
POST_MERGE_REVERTED
HARD_STUCK
```

A deliberately failing candidate must never become `main`.

### 8.5 Milestone state

```text
PROPOSED
→ ACTIVE
→ EVIDENCE_COMPLETE
→ MACHINE_POLICY_PENDING
→ COMPLETED
→ NEXT_ACTIVE
```

External commercial milestones may remain `WAITING_EXTERNAL`. Their wait must not prevent eligible product, competitor, trust, or factory work.

---

# 9. Execution phases

## Phase 0 — Re-baseline, preserve state, and establish rollback

### Objective

Establish the real starting point and guarantee that no user work, runtime state, or historical evidence is lost.

### Required actions

1. Locate the actual repository root.
2. Record:
   - local branch and HEAD;
   - `origin/main` SHA;
   - ahead/behind/divergence;
   - clean/dirty/untracked state;
   - local-only commits;
   - stashes;
   - tags and safety refs;
   - worktrees;
   - active processes;
   - WSL/systemd/Windows scheduled tasks;
   - V2 and V3 queues;
   - leases;
   - checkpoints;
   - publication transactions;
   - STOP/PAUSE/HARD_STUCK;
   - configured runtime root;
   - GitHub repository identity/visibility;
   - branch protection/rulesets;
   - workflow state;
   - current active milestone;
   - Claude credential route state;
   - private verifier/private-gate installation state.
3. If user-authored uncommitted work exists, create a lossless patch/bundle or dedicated preservation commit/branch. Do not blend it into this remediation.
4. Fetch remote refs without changing work.
5. Create an immutable annotated safety tag at the actual starting SHA:

```text
safety/traincapsule-pre-v3-1-zh-hardening-<UTC>
```

6. Create the working branch:

```text
codex/traincapsule-v3-1-zh-hardening
```

7. Create the execution-state artifacts.
8. Run the current full test/gate suite without modifying code. Record baseline failures separately from migration regressions.
9. Verify that the controller remains stopped.

### Required proof

- starting-state report with hashes;
- safety tag exists locally and remotely where permitted;
- rollback bundle/tag can restore the exact starting tree;
- baseline test outputs and digests;
- no controller mutation occurred.

### Commit

```text
chore: record v3.1 zh hardening baseline
```

## Phase 1 — Create coherent V3.1-ZH source authority

### Objective

Eliminate the contradictory combination of immutable V3 human-approval rules and higher-precedence zero-human shadow overrides.

### Required actions

1. Preserve unchanged:

```text
docs/source-of-truth/final-2026-08-09/
docs/source-of-truth/v3-2026-08-11/
```

2. Create:

```text
docs/source-of-truth/v3.1-zh-2026-08-12/
```

3. Include a complete logical document set derived from the V3 bundle, including at least:

```text
00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md
03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md
04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md
05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md
06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md
12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md
13_SOURCE_REGISTER_V3_1_ZH.md
14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md
FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md
SOURCE_OF_TRUTH_MIGRATION_PLAN_V3_1_ZH.md
README.md
FINAL_MANIFEST_V3_1_ZH.json
```

4. Rewrite every affected rule consistently. The active generation must explicitly state:
   - zero founder/operator intervention after bootstrap;
   - external people and customer facts remain external receipts;
   - no human approval runtime state;
   - no AI session may self-certify trust;
   - independent off-repo machine authority replaces release approval;
   - automated PR, required checks, and auto-merge replace direct-main publication;
   - exact-SHA, evidence, native-first, `UNKNOWN`, finite retries, and bounded milestones remain mandatory;
   - controlled fixtures cannot prove external value or commercial support;
   - activation requires a signed external activation receipt;
   - residual risk of replacing qualified-human review is disclosed.
5. Give every logical document a stable ID and authority class.
6. Generate a canonical manifest with logical ID, path, hash, authority class, sections, generation, and supersession metadata.
7. Implement one canonical `active_generation` pointer in configuration.
8. Update:

```text
SOURCE_PRECEDENCE.md
docs/CONTEXT_INDEX.yaml
CLAUDE.md
README.md
prompts/global.md
config/factory.yaml
```

9. Remove active dependence on:

```text
factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json
config/owner_directives.yaml
config/human_approval.yaml
```

They may remain immutable historical migration evidence. They must not shadow active authority.
10. Reject mixed normative generations at startup, packet compilation, context construction, gate evaluation, publication, and milestone advancement.
11. Implement source-monitor behavior:
   - current fact conflict marks affected assumption `STALE` or `RECHECK_REQUIRED`;
   - creates a bounded ADR/wedge-review work item;
   - never silently rewrites normative source.
12. Preserve and hash all 124 legacy items, packets, specs, and dispositions. Assert that T002 is non-blocking and cannot reenter the V3 critical path.
13. Recompute M0 under V3.1-ZH criteria; do not transform source text through ad hoc replacement during ledger generation.

### Required tests

- immutable V2/V3 bundle hash tests;
- duplicate logical ID rejection;
- mixed-generation rejection;
- missing source rejection before claim;
- stale current-fact transition;
- T002 non-blocking assertion;
- all-124 legacy inventory/hash assertion;
- manifest regeneration exactness;
- negative control: changed active source without manifest update fails.

### Required proof

- V3.1-ZH manifest digest;
- exact source-generation diff summary;
- immutable historical bundle hashes unchanged;
- context manifests show only active normative generation;
- M0 evidence recomputed rather than text-rewritten.

### Commit

```text
spec: add coherent v3.1 zh authority
```

## Phase 2 — Migrate schemas, configurations, and runtime semantics

### Objective

Make all machine-readable contracts describe the same V3.1-ZH architecture before wiring live behavior.

### Required actions

1. Version or replace schemas for:
   - source generation;
   - source freshness receipt;
   - work item;
   - task packet;
   - output declaration;
   - agent request;
   - agent capability;
   - session reference;
   - execution report;
   - finding and fingerprint counter;
   - checkpoint;
   - handoff;
   - candidate manifest;
   - native substitute benchmark;
   - decision value result;
   - machine-policy receipt;
   - machine-policy revocation list;
   - activation receipt;
   - PR publication transaction;
   - milestone completion proposal;
   - runtime status/event.
2. Use `extra=forbid`/`additionalProperties=false` and strict enums.
3. Add explicit schema version and migration path.
4. Separate technical, epistemic, value, release, and commercial maturity states.
5. Make zero invalid for every retry/attempt/expansion field where zero previously meant unlimited. Use explicit disabled booleans where needed.
6. Make `autonomy.enabled` authoritative. When false, only read-only status, validation, simulation, and explicit one-shot canary commands are permitted.
7. Add `activation_receipt_required=true` for live unattended mode.
8. Add per-lane network/source acquisition policy.
9. Add per-risk machine-policy requirements.
10. Add explicit runtime root/path configuration.
11. Generate all JSON schemas deterministically and verify checked-in output.

### Required proof

- schema generation exactness;
- unknown field rejection;
- migration tests from current V3 state;
- invalid zero/unbounded values rejected;
- configuration contradictions rejected;
- autonomy-disabled mutating controller refusal.

### Commit

```text
refactor: align v3.1 zh contracts
```

## Phase 3 — Install independent machine-policy and activation authority

### Objective

Replace human release approval with a genuinely separate, immutable, attributable machine authority—not another repository-visible AI role.

### Required trust boundary

Implement a local production-grade initial boundary compatible with Windows 11 + WSL/Linux:

```text
candidate/controller account
    can: write candidate branches, read public policy, request evaluation
    cannot: write verifier code installation, private policy, oracle fixtures, signing key, revocation state, verifier GitHub credential

traincapsule-verifier service account
    can: read exact candidate SHA, run off-repo private gates, sign scoped receipts, post GitHub check
    cannot: modify candidate code, push branches, merge PRs, change source authority
```

Prefer:

```text
/etc/traincapsule-verifier/                 # root-owned policy/public config
/var/lib/traincapsule-verifier/             # root/verifier-owned state and receipts
/var/lib/traincapsule-verifier/private/     # private oracles and key material
/var/log/traincapsule-verifier/             # redacted logs
```

The repository may contain installer/client/schema/reference code, but the active verifier installation, private policy, hidden oracle data, signing key, revocation list, and GitHub check credential must be outside repository and candidate write authority.

### Required receipt fields

A valid receipt must bind at least:

```text
schema_version
receipt_id
policy_id
policy_version
issuer_id
issuer_key_id
issued_at
expires_at
revocation_epoch
nonce
request_digest
work_item_id
milestone_id
lane
risk_tier
candidate_sha
candidate_tree_sha
base_sha
source_generation_id
source_generation_digest
context_manifest_digest
task_packet_digest
candidate_manifest_digest
checkpoint_digest
required_gate_results
private_gate_suite_id
private_gate_runner_digest
independent_oracle_ids
raw_evidence_artifact_hashes
native_substitute_disposition
decision_value_disposition
engineering_maturity_ceiling
commercial_maturity_ceiling
allowed_claims
forbidden_claims
publication_scope
signature_algorithm
signature
```

### Required verifier behavior

- Ed25519 or stronger signature verification.
- Exact canonical serialization.
- Reject missing, malformed, stale, expired, revoked, replayed, unknown-issuer, wrong-policy, wrong-risk, wrong-source-generation, wrong-base, wrong-candidate, wrong-tree, wrong-context, wrong-packet, wrong-manifest, wrong-gate, missing-oracle, writable-root, or repository-self-authored receipts.
- Bind permitted claims; a receipt is not a generic pass.
- Use independent private oracle code/fixtures where the trust model requires it.
- The verifier must not consume an agent's prose verdict as authority.
- The verifier posts a GitHub check named exactly:

```text
TrainCapsule / Machine policy
```

- The credential used to post the check must not be available to repository Actions or candidate agents.
- The verifier cannot push or merge code.
- Support revocation and policy rollover without changing candidate code.
- Support a signed activation receipt binding the exact verified `main` SHA, machine/environment digest, active source generation, controller binary/config digests, and expiry.

### GitHub integration

Use a GitHub App where practical. A fine-grained token stored only by the root-owned verifier service is an acceptable initial fallback if it is limited to checks/status/read-only repository metadata and cannot push or merge. Record the exact permission set.

### Required negative tests

- tampered receipt bytes;
- wrong candidate SHA;
- same commit but wrong tree binding;
- wrong source generation;
- wrong task packet;
- expired receipt;
- revoked receipt;
- replayed nonce;
- downgraded policy version;
- omitted required oracle;
- substituted raw artifact;
- self-authored repository receipt;
- group/world-writable receipt root;
- agent-readable signing key;
- GitHub check posted without matching local signed receipt;
- activation receipt for a different main SHA.

### Required proof

- service account/permission boundary;
- public key fingerprint and policy version;
- verifier binary/script digest;
- receipt schema and canonical vector;
- negative-control artifacts;
- no secrets in repo or logs;
- machine-policy check posted for a disposable candidate.

### Commit

```text
security: add external machine authority
```

## Phase 4 — Replace direct-main publication with automated PR and server-side enforcement

### Objective

Make release fully automatic without ever placing an unverified candidate on `main`.

### Required actions

1. Refactor `tcfactory/github_sync.py` and related publication code to use candidate branches and PRs.
2. Implement idempotent operations:
   - choose deterministic branch name from work item/run/candidate;
   - push exact candidate SHA without force;
   - create or find existing PR;
   - verify PR head/base and repository identity;
   - attach candidate/packet/source/context/receipt digests;
   - observe all required checks;
   - require `TrainCapsule / Machine policy` success for the exact head SHA;
   - enable auto-merge or merge queue;
   - verify merged commit/tree and exact expected candidate relation;
   - write durable publication state after every side effect;
   - reconcile safely after process crash.
3. Configure GitHub ruleset/branch protection for `main`:
   - PR required;
   - no force pushes;
   - no deletion;
   - required workflows;
   - required machine-policy check;
   - conversation resolution if repository uses review comments;
   - zero required human approvals under V3.1-ZH;
   - merge queue or auto-merge;
   - admin bypass disabled or tightly restricted and recorded;
   - branch up-to-date requirement according to merge-queue design.
4. Required workflows should include, using actual repository workflow names:

```text
TrainCapsule / Factory quality
TrainCapsule / Product unit
TrainCapsule / Product contract
TrainCapsule / Security
TrainCapsule / Source-of-truth integrity
TrainCapsule / Packaging install
TrainCapsule / Machine policy
```

Also require docs/schema/source-freshness workflows where they protect changed surfaces.
5. A pre-merge failure closes or quarantines the PR and blocks the work item; it does not revert `main` because the candidate never reached it.
6. Post-merge rollback is reserved for an invariant discovered after merge. Implement an automated revert PR/transaction, not direct history rewriting.
7. Reject remote divergence and ambiguous duplicate PRs.
8. Do not allow repository Actions to fabricate the machine-policy status.

### Required crash tests

Kill/restart after:

```text
branch push
PR creation
first check observation
machine receipt creation
machine check posting
auto-merge enablement
merge queue entry
merge completion
post-merge verification
```

Every retry must be idempotent and must not create duplicate PRs, checks, merges, or reverts.

### Required proof

- branch ruleset export;
- required checks list;
- harmless candidate auto-merged without human click;
- deliberately failing candidate rejected before `main`;
- crash-recovery transaction artifacts;
- direct-main push path removed/refused by tests.

### Commit

```text
ci: enforce automated pr release
```

## Phase 5 — Repair task compilation, source resolution, outputs, scopes, and context

### Objective

Ensure every selected work item produces one executable, bounded, correctly authorized task packet.

### Source resolution

- Remove hard-coded missing paths such as the absent V3 `CODEX_MASTER_MIGRATION_PROMPT.md` reference.
- Resolve source documents by logical ID through the active source manifest and context index.
- Bind source generation and exact file digests into the packet.
- Reject missing, stale, mixed-generation, or unauthorized sources before queue claim.

### Output declarations

Every work item must declare:

```text
output_id
path
schema_id
required/optional
evidence_class
mutating_owner
readers
content_digest_required
external_authority_required
```

Replace `outputs=[]` with generated task-specific outputs. A task cannot pass when a required durable output is missing, unparseable, outside scope, stale, or digest-mismatched.

### Lane/path policy

Implement task-specific scopes. Suggested root classes:

```text
PRODUCT
  packages/traincapsule-*/**
  schemas/product/**
  tests/product/**
  examples/product/**
  docs/product/**
  docs/evidence/product/**

MARKET
  docs/market/**
  docs/evidence/market/**
  factory/external-evidence/market-metadata/**

COMPETITOR
  docs/research/**
  docs/evidence/competitors/**
  controlled proposals for source/capability register changes

TRUST
  tests/**
  docs/evidence/trust/**
  private-gate request metadata only
  threat models and verification artifacts

FACTORY
  tcfactory/**
  config/**
  scripts/**
  prompts/**
  schemas/factory/**
  tests/test_v3_*.py and bounded factory tests
  docs/migrations/**
```

No routine lane edits active normative source. Normative changes require an explicit source-generation migration work item and machine-policy approval.

### Mutability/tool policy

Derive tools from the work item and packet, not the literal role name:

- one mutating owner gets only declared write roots;
- read-only reviewers receive no Write/Edit;
- research/specification/factory-repair may write only when the work item is mutating and output paths authorize it;
- Bash uses an explicit executable + argument policy;
- candidate agents cannot invoke `git push`, `gh`, credential commands, branch/ruleset changes, verifier commands, or service-control commands.

### Context policy

- Use task- and role-specific context groups.
- Include only exact authority sections needed.
- Never inject career/acquisition advisory material into routine work.
- Bind every source digest.
- Supply current-fact freshness receipts.
- If required context exceeds limits, split the work item through a machine-approved bounded proposal; never silently omit authority.
- Preserve prior findings as bounded fingerprints, not full transcripts.

### Strict agent execution report

Replace generic `{"type":"object"}` with a versioned strict schema containing at minimum:

```text
schema_version
request_id
work_item_id
role
base_sha
candidate_sha
source_generation_id
source_digest
context_digest
task_packet_digest
verdict
truth_state
criterion_results
findings
finding_fingerprints
changed_files
commands_run
tests_run
outputs
artifact_digests
external_receipt_refs
native_disposition
value_disposition
limitations
resource_usage
session_ref
resume_state
next_authorized_action
```

Each finding must include severity, blocking flag, criterion, fingerprint, reproducible evidence, expected/observed, owner class, and minimal repair. Preserve reports, findings, evidence, and limitations in the candidate manifest and handoff. Never initialize them to empty after execution.

### Required tests

- missing source;
- mixed generation;
- unauthorized path;
- undeclared output;
- missing required output;
- malformed report;
- report with unknown field;
- read-only mutation;
- mutator missing Write/Edit;
- research output allowed only in exact roots;
- active normative edit rejected;
- career/acquisition context leakage rejected;
- stale current-fact context rejected.

### Commit

```text
fix: repair v3 task execution contracts
```

## Phase 6 — Implement controller-owned current-fact acquisition and research evidence

### Objective

Allow market, competitor, and current-fact work to run autonomously without giving agents unrestricted network authority.

### Preferred architecture

Keep normal agent sessions network-denied. Implement a controller-owned source acquisition service that:

1. accepts a typed research/source request;
2. enforces exact allowlisted HTTPS domains and methods;
3. resolves redirects against the allowlist;
4. blocks private/local IPs, alternate schemes, credential-bearing URLs, and arbitrary downloads;
5. stores raw response bytes content-addressed;
6. records URL, final URL, retrieval time, status, headers subset, content type, source class, query plan, control query, SHA-256, parser version, and freshness policy;
7. emits a signed or controller-attested freshness receipt;
8. supplies the offline snapshot to research agents;
9. never lets fetched content become normative authority automatically.

Use current official primary sources for technical claims. Record `CLEAR`, `CONFLICT`, or `UNKNOWN`; preserve contradictory evidence and raw controls.

### Market actions

Implement a backend-neutral `ExternalActionAdapter` interface for permitted outbound actions, but keep it disabled unless an explicit machine policy, channel credential, recipient allowlist, legal/safety policy, and template are installed. When unavailable, work becomes `WAITING_EXTERNAL_CHANNEL`, not founder-blocked and not fabricated. Unrelated lanes continue.

### Required tests

- allowed primary domain;
- redirect to disallowed domain;
- private IP/localhost denial;
- non-HTTPS denial;
- stale receipt;
- conflicting sources;
- raw snapshot tamper;
- source parser failure returns `UNKNOWN`/typed error;
- external action unavailable isolates scope;
- no fetched text directly edits normative source.

### Commit

```text
feat: add controlled source acquisition
```

## Phase 7 — Make the Claude/backend contract truthful, finite, secure, and resumable

### Objective

Prove that the real Claude path follows the backend-neutral contract and survives the failures expected in unattended operation.

### Required actions

1. Keep Claude as the only configured initial backend, but ensure durable state is provider-neutral.
2. Make capability reporting truthful:
   - `resume=false` until proven;
   - report actual sandbox, structured output, cancellation, network denial, transcript policy, and tools.
3. Create durable `SessionRef` fields for provider session ID/ref, request digest, work item, role, candidate SHA, source/context/packet digests, checkpoint generation, resume capability/version, and state.
4. Preserve provider secrets only in the credential provider; export only redacted route state.
5. Distinguish:

```text
AUTHENTICATED
AUTH_EXPIRED
QUOTA_WAIT
TRANSIENT_PROVIDER_ERROR
TIMEOUT
CANCELLED
ROUTE_REFUSED
SCHEMA_FAILURE
SANDBOX_UNAVAILABLE
```

6. Propagate quota/auth/timeout dispositions to the controller rather than collapsing them into generic failure.
7. Implement cancellable wall-clock timeout around each query.
8. Enforce structured output and allow only a bounded report-finalization continuation when the model reached a turn ceiling without emitting its report.
9. Enforce Bash policy at controller/hook boundary, not only through prompt language.
10. Enforce sandbox fail-closed for mutating and read-only roles.
11. Scrub controller credentials from all model-launched subprocesses.
12. Retain redacted summaries and message-type metadata; do not retain raw secrets or unnecessary full transcripts.
13. Remove any subscription-unbounded path. Renewable sessions are allowed, but every session, task attempt, repair cycle, wall time, and restart remains finite.
14. Prove resume across controller process restart before setting capability true. If provider-native resume cannot be made reliable, implement candidate-preserving new-session continuation and report provider resume false.
15. Validate Max-only authentication and prohibit paid API-key fallback.

### Required live tests

- harmless real Claude structured task;
- malformed structured output retry;
- turn-ceiling report finalization;
- process kill during query;
- candidate-preserving continuation;
- injected quota event and automatic resume time;
- expired access token with automatic refresh/recheck where supported;
- sandbox unavailable;
- forbidden Bash command;
- secret-bearing prompt/path rejection;
- no network from normal agent session.

### Commit

```text
fix: harden claude backend execution
```

## Phase 8 — Unify runtime paths, queue ownership, leases, supervisor, and status

### Objective

Guarantee that every component observes and mutates one authoritative runtime state root.

### Required actions

1. Create one typed runtime path resolver used by controller, CLI, scheduler, queue, checkpoints, artifacts, worktrees, events, supervisor, publication, verifier client, and status.
2. Support an absolute runtime root outside the repository.
3. Never call `relative_to(repo_root)` on external runtime paths unless explicitly optional.
4. Migrate existing runtime state safely and preserve a rollback snapshot.
5. Make queue state authoritative at runtime; static roadmap seed status must not masquerade as live state.
6. Implement a durable lease with:
   - owner/controller instance ID;
   - random lease token;
   - generation;
   - claimed time;
   - heartbeat time;
   - expiry;
   - candidate/session binding.
7. Start a renewal coroutine at substantially less than TTL.
8. On renewal failure, stop mutation, checkpoint, and enter typed recovery; do not continue as an unowned mutator.
9. Detect and reject duplicate controllers through lock + lease ownership.
10. Recover an expired claim only from exact checkpoint/candidate/session identity. Never spawn a second ambiguous mutator.
11. Supervisor preflight must inspect V3.1-ZH paths, queues, active sessions, publication transactions, source integrity, machine authority, activation receipt, credentials, and branch/ruleset state.
12. `autonomy.enabled=false` must prevent live controller execution.
13. Status must report:

```text
active source generation and digest
active milestone
current work item and lane
runtime status
lease owner/token generation/expiry
base and candidate SHA
session reference/state
retry/repair/respec/restart budgets
external waits by scope
current-fact freshness
machine-policy state/receipt
PR/check/merge state
factory/product CI
last event
controller activation receipt
STOP/PAUSE/HARD_STUCK
```

### Required crash/power-loss tests

- transition journal before/after move;
- lease creation;
- lease renewal;
- checkpoint write;
- session checkpoint;
- candidate commit;
- gate evidence write;
- publication state write;
- milestone state write.

### Commit

```text
fix: unify v3 runtime and leases
```

## Phase 9 — Implement real finite repair, re-specification, no-progress, quota, and recovery loops

### Objective

Turn configured limits into an actual finite execution state machine.

### Required state flow

```text
RUNNING
→ PASS
| TYPED_NON_PASS
| QUOTA_WAIT
| AUTH_EXPIRED
| WAITING_EXTERNAL
| WAITING_MACHINE_AUTHORITY

TYPED_NON_PASS
→ candidate-preserving repair attempt
→ deterministic recheck
→ independent reviewer recheck
→ bounded re-specification if failure indicates packet/spec defect
→ terminal disposition when budgets or no-progress rules fire
```

### Required actions

1. Execute every configured budget; do not merely decrement and block.
2. Separate budgets for:
   - planning attempts;
   - candidate repair cycles;
   - same-finding repetitions;
   - candidate restarts;
   - re-specifications;
   - infrastructure recoveries;
   - factory self-repairs;
   - controller restarts;
   - value redesigns;
   - milestone expansion proposals.
3. Fingerprint findings using criterion, normalized reproduction, expected/observed class, owner, and exact candidate/source context.
4. A repeated fingerprint at the configured limit triggers no-progress handling and a terminal bounded disposition.
5. Repair agents may edit only the candidate's authorized surface. They cannot edit tests/requirements/policy to hide the finding.
6. Factory repair can modify factory code only under a controller-failure work item and cannot modify product truth, normative source, private verifier, or value thresholds.
7. Re-specification creates a new immutable task packet version, records why the prior packet was invalid, and preserves the candidate. It cannot broaden the milestone or acceptance criteria without machine-policy approval.
8. Quota waits persist `resume_at` and automatically retry after reset.
9. Auth expiry persists a typed wait and automatically rechecks the credential broker; no paid API fallback.
10. Infrastructure failures do not count as product failures.
11. Candidate salvage is automatic and content-addressed, with exact checkpoint/session/source identities.
12. HARD_STUCK is durable and requires a new signed activation/recovery receipt—not ad hoc file deletion—to resume.

### Required tests

- repair fixes one product defect;
- repair fails and second repair succeeds;
- repeated identical finding terminates;
- different valid findings do not collapse incorrectly;
- re-specification limit terminates;
- factory defect routes to factory repair;
- product agent cannot edit factory/policy;
- quota wait resumes;
- auth wait rechecks;
- infrastructure failure preserves candidate;
- HARD_STUCK cannot be bypassed.

### Commit

```text
fix: add finite repair and recovery
```

## Phase 10 — Preserve evidence, findings, handoffs, checkpoints, and candidate identity end to end

### Objective

Eliminate evidence loss and status laundering between stages.

### Required actions

1. Candidate manifest must aggregate validated execution reports, findings, raw artifacts, external receipts, native/value results, gate results, checkpoint digest, source/context/packet digests, and limitations.
2. Read-only reviewer findings remain attached to the exact frozen candidate SHA.
3. A candidate mutation taints prior reviewer/gate evidence and requires revalidation.
4. External receipt references must be verified, not just listed.
5. Handoff must be backend-neutral and sufficient for a fresh session without prior transcript.
6. Checkpoints use atomic envelope, generation, digest, and previous-generation recovery.
7. Corrupt or incompatible checkpoints quarantine and block ambiguous resume.
8. Never promote a task because a report says “pass” while its required artifacts are missing.
9. Add status-laundering tests across every transition.

### Commit

```text
fix: preserve v3 evidence across stages
```

## Phase 11 — Integrate complete-substitute benchmarking and decision-value maturity gates

### Objective

Prevent technically valid but commercially redundant work from being counted as product success.

### Required `NativeSubstituteBenchmark`

At minimum:

```text
schema_version
benchmark_id
work_item_id
case_id
candidate_sha
environment_digest
source_freshness_receipts
native_tool_names_versions_configs
approved_agent_assistance_baseline
native_inputs
native_outputs
native_findings
native_operational_decision
traincapsule_incremental_capability
traincapsule_outputs
traincapsule_operational_decision
operational_decision_changed
cost_time_resource_comparison
reproducibility
limitations
truth_state
raw_artifact_hashes
oracle_identity
issuer_identity
```

### Required behavior

1. Compare the complete approved substitute, including native tools, provider tools, internal scripts, and approved agent assistance where applicable.
2. Do not compare against a deliberately weak strawman.
3. Run the benchmark early and repeatedly after major product surfaces.
4. Invoke the value evaluator after technical validation and before release/maturity promotion.
5. Legal outcomes include:

```text
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
INCREMENTAL_DECISION_VALUE_DEMONSTRATED
EXTERNAL_EVIDENCE_REQUIRED
```

6. Apply outcomes to work-item and product maturity.
7. Controlled evidence may establish controlled technical behavior, but not payment, adoption, external value, or commercial support.
8. `EXTERNAL_VALUE_DEMONSTRATED` and `COMMERCIALLY_SUPPORTED` require signed external receipts.
9. Keep checkpoint/resume as an engineering reference until its own native/value gate proves a customer-important difference.
10. Explicitly test TrainCheck and other relevant complete substitutes against incident-derived contracts where current sources support it.

### Required negative tests

- same operational decision -> native sufficient/rejected value;
- lower technical metric but no decision change -> no commercial promotion;
- synthetic payment/adoption receipt rejected;
- stale competitor fact blocks claim;
- unapproved native baseline rejected;
- missing raw artifacts rejected.

### Commit

```text
feat: gate native and decision value
```

## Phase 12 — Wire milestone completion, bounded roadmap mutation, and automatic advancement

### Objective

Allow the loop to progress across milestones without founder operation while preventing AI-authored prose from rewriting the roadmap.

### Required actions

1. Evaluate milestone completion after every terminal work-item transition and when scheduler becomes idle.
2. Read authoritative runtime state, not static seed statuses.
3. Verify required evidence classes, source generation, exact SHA, native/value outcomes, machine receipts, and external waits.
4. Generate at most one bounded completion or expansion proposal per configured cycle.
5. Proposal must include exact new/changed work items, dependency graph, scope, rationale, evidence, size, and rollback.
6. Reject cycles, oversized expansion, broadening beyond milestone, fabricated external facts, and policy/threshold changes.
7. Obtain a signed machine-policy receipt for roadmap mutation.
8. Apply accepted state atomically with write-ahead journal.
9. Mark current milestone completed and activate exactly one next milestone.
10. Emit an event, state digest, and rollback record.
11. Never treat `WAITING_EXTERNAL` as pass.
12. External milestones remain waiting while unrelated engineering continues.
13. Add a disposable M1→M2 canary and rollback test.

### Commit

```text
feat: advance v3 milestones automatically
```

## Phase 13 — Make market, competitor, and trust lanes executable and isolated

### Objective

Turn the four/five-lane roadmap into a real autonomous scheduler rather than static declarations.

### Market lane

- Produce a reachable-account map only from attributable sources.
- Preserve source controls and freshness.
- Store conversations/incidents/payments only as external signed receipts.
- Generate pilot/account artifacts in exact writable roots.
- Do not claim demand from counts or synthetic data.
- Outbound actions require configured external-action authority; otherwise isolate wait.

### Competitor lane

- Refresh source register through controlled source acquisition.
- Record `CLEAR`, `CONFLICT`, `UNKNOWN`.
- Compare complete substitutes.
- Create proposals rather than directly editing normative strategy.
- Include current relevant threats from the active source register.

### Trust lane

- Independently attack identity, canonical serialization, evidence completeness, native baseline, false green, machine receipt, release, and claim law.
- Use off-repo private oracles.
- Cannot alter candidate or authority.

### Scheduler

- Continue eligible lanes while market/external work waits.
- Enforce global and per-lane WIP.
- Renew leases.
- Use deterministic scores and fairness rotation.
- Record every selection and rejection reason.
- Ensure factory mutation is only scheduled for controller/factory failure or explicit migration.

### Required canary

Place a market item in `WAITING_EXTERNAL`, then prove product/competitor/trust work continues and the status view shows the scoped blocker.

### Commit

```text
feat: execute isolated v3 lanes
```

## Phase 14 — Preserve and strengthen the bounded product preflight

### Objective

Do not regress the useful product work already implemented while hardening the factory.

Preserve these package boundaries:

```text
packages/traincapsule-core/
packages/traincapsule-ingest-pytorch/
packages/traincapsule-qualify/
packages/traincapsule-cli/
```

Required product proof:

- deterministic canonical identity with independent vectors;
- content-addressed evidence storage and tamper/path/symlink limits;
- bounded real-format Flight Recorder import;
- evidence completeness and limitations;
- native baseline preservation;
- explicit `UNKNOWN`, invalid evidence, native sufficient, and uneconomic states;
- install-to-first-value CLI journey;
- strict schemas;
- no factory enum/runtime coupling;
- truthful README and claims;
- no claim of reduction, GPU qualification, full pilot, customer adoption, or commercial support without evidence.

Do not build hosted SaaS, broad federation, universal reduction/replay, managed GPU fleet, autonomous production remediation, broad dashboards, or a commercially released second pack as part of this hardening. Preserve those as bounded/deferred roadmap items where the active plan retains them.

### Commit

```text
fix: preserve product preflight contracts
```

## Phase 15 — Build exhaustive deterministic, security, crash, and live validation

### Test tiers

#### Tier 1 — Static and schema

```text
ruff
pyright/mypy as configured
schema generation
YAML uniqueness
source manifest integrity
secret scan
forbidden API/paid usage scan
```

#### Tier 2 — Unit/property/negative

- all typed models and transitions;
- source generation;
- packet compiler;
- path/tool/network policy;
- findings/fingerprints;
- retry budgets;
- native/value gates;
- receipt validation;
- publication transactions;
- milestone engine;
- product models.

#### Tier 3 — Integration

- queue + controller + fake backend;
- controller-owned source acquisition;
- external verifier client/service;
- GitHub API behavior against disposable branch/PR where safe;
- supervisor/runtime root outside repo;
- checkpoint and candidate recovery.

#### Tier 4 — Crash and fault injection

Kill or fault every durable boundary and verify idempotent recovery.

#### Tier 5 — Live Claude observation

Run one harmless mechanical task with real Claude, no publication first. Prove exact packet/context/report, process restart, automatic continuation, gates, terminal result, and next scheduling.

#### Tier 6 — Live automated PR

Run one harmless candidate through branch, PR, required checks, external machine receipt, auto-merge, and exact post-merge verification. Run a deliberately bad candidate and prove it never reaches main.

### Required commands

Use the repository's actual commands, but run at least equivalents of:

```text
uv sync --extra dev --frozen
uv run ruff check .
uv run pyright
uv run pytest -q
bash scripts/gates/secret_scan.sh
bash scripts/gates/full_quality.sh
uv run python scripts/generate_product_schemas.py --check
uv run python scripts/generate_v3_schemas.py --check
uv run python scripts/generate_v3_roadmap.py --check
uv run python scripts/gates/source_of_truth_integrity.py
```

Run each GitHub workflow's commands locally where possible. Do not weaken tests to turn them green.

### Failure classification

Every failure must be classified as:

```text
PRE_EXISTING
MIGRATION_REGRESSION
PRODUCT_DEFECT
FACTORY_DEFECT
INFRASTRUCTURE
QUOTA
AUTH
EXTERNAL_WAIT
POLICY_BLOCKER
INVALID_EVIDENCE
INVALID_ORACLE
```

### Commit

```text
test: prove v3.1 zh rejection paths
```

## Phase 16 — Mandatory autonomy canaries and activation

### Mandatory canaries

Run every canary in `03_V3_1_ZH_ACCEPTANCE_CONTRACT.yaml`, including:

```text
real_claude_mechanical_task
process_kill_and_resume
quota_pause_and_resume
authentication_expiry_and_recovery
repeated_finding_finite_stop
external_wait_lane_isolation
bad_candidate_rejected_before_main
release_transaction_crash_idempotency
automatic_milestone_advancement
machine_receipt_missing_invalid_expired_revoked
```

Also run:

- duplicate-controller rejection;
- lease renewal failure;
- stale current facts;
- missing source authority;
- malformed report;
- private gate missing for trust risk;
- machine verifier unavailable;
- activation receipt wrong SHA;
- runtime root outside repo;
- post-merge invariant failure and automated revert PR.

### Activation requirements

Do not activate until:

1. every CRITICAL matrix item is `PROVEN` or a legitimate `EXTERNAL_WAIT` that does not block engineering activation;
2. every HIGH engineering/runtime item is `PROVEN`;
3. all mandatory canaries pass;
4. GitHub ruleset is active;
5. external verifier service is active and independent;
6. exact `main` SHA has passed all required checks;
7. signed activation receipt matches exact `main`, environment, source generation, config, and controller digests;
8. no nonterminal publication transaction exists;
9. no ambiguous queue/checkpoint/lease exists;
10. STOP/PAUSE removal is performed by the activation command only after receipt verification;
11. scheduled startup/service is enabled and a restart/reboot observation succeeds;
12. status reports `interventionMode=NONE` truthfully.

If any requirement cannot be proven, keep the controller stopped and report `NOT_ACTIVATED`.

### Post-activation observation

Observe at least:

- one complete autonomous cycle;
- an idle cycle;
- an external-wait-isolated cycle;
- service restart;
- next-work scheduling;
- no direct-main push;
- no human click.

### Commit

```text
ops: activate verified v3.1 zh controller
```

Only make this commit if activation actually occurs. Otherwise commit a truthful stopped-state report.

---

# 10. File-specific inspection and likely modification targets

Inspect all of these before planning edits. Modify only where required by evidence and preserve repository style:

```text
SOURCE_PRECEDENCE.md
CLAUDE.md
README.md
docs/CONTEXT_INDEX.yaml
config/factory.yaml
config/autonomy.yaml
config/scheduler.yaml
config/executors.yaml
config/external_evidence.yaml
config/github.yaml
config/roles.yaml
config/risk_profiles.yaml
config/milestones.yaml
config/commercial_maturity.yaml
prompts/global.md
prompts/*.md
schemas/factory/v3/**
.github/workflows/**
tcfactory/v3/configuration.py
tcfactory/v3/controller.py
tcfactory/v3/scheduler.py
tcfactory/v3/queue.py
tcfactory/v3/planning.py
tcfactory/v3/work_items.py
tcfactory/v3/milestones.py
tcfactory/v3/recovery.py
tcfactory/v3/migrations.py
tcfactory/v3/external_evidence.py
tcfactory/v3/pipeline_services.py
tcfactory/backends/base.py
tcfactory/backends/claude.py
tcfactory/claude_runner.py
tcfactory/structured_runner.py
tcfactory/context.py
tcfactory/checkpoints.py
tcfactory/github_sync.py
tcfactory/runtime_status.py
tcfactory/supervisor.py
tcfactory/value.py
tcfactory/cli.py
scripts/gates/**
scripts/*setup*
scripts/*autostart*
scripts/*factory*
tests/test_v3_*.py
tests/product/**
```

Likely new modules may include equivalents of:

```text
tcfactory/v3/authority.py
tcfactory/v3/runtime_paths.py
tcfactory/v3/execution_reports.py
tcfactory/v3/source_acquisition.py
tcfactory/v3/machine_policy.py
tcfactory/v3/native_benchmark.py
tcfactory/v3/completion_engine.py
tcfactory/v3/publication.py
tcfactory/v3/activation.py
```

These are suggestions, not permission to create unnecessary abstractions. Reuse existing code when it is correct and testable.

# 11. Git and commit policy

- Work only on the hardening branch.
- Use small coherent commits.
- Never mix unrelated user work.
- No force push.
- No direct main push.
- No commit containing secrets, runtime tokens, private receipts, private oracle code, or generated transient state.
- Commit messages should be short and plain.
- After each commit, record SHA and tests in the execution state.
- Push the branch and open a draft PR early, then update it.
- Suggested PR title:

```text
Harden TrainCapsule V3.1 zero-founder loop
```

- The final merge must occur only through required checks and automated merge policy.

# 12. Definition of done

The task is complete only when all of the following are true:

1. A coherent V3.1-ZH source generation is active and historical bundles remain immutable.
2. No shadow override contradicts active authority.
3. All source/context/packet/candidate/evidence identities are exact and digest-bound.
4. Machine release authority is external, signed, scoped, expiring, revocable, and independent.
5. `main` is protected by server-side required checks and candidates enter through automated PRs.
6. A bad candidate cannot reach `main`.
7. The real Claude path completes a task unattended and survives restart.
8. Queue leases renew and duplicate mutation is impossible.
9. Quota/auth/timeout are typed and resume or stop lawfully.
10. Repair, re-specification, no-progress, and factory recovery are finite and executed.
11. Findings/evidence survive every transition.
12. Native/substitute and decision-value outcomes gate maturity and release.
13. Milestones advance automatically through signed bounded policy.
14. External waits isolate only dependent scope.
15. Product preflight remains correct and claims remain truthful.
16. All critical/high matrix requirements are proven.
17. Mandatory live canaries pass.
18. A signed activation receipt permits exact-SHA startup.
19. Controller activation state is truthful.
20. Final report contains exact evidence and no unsupported claim.

# 13. Required final response

Use `06_REQUIRED_FINAL_REPORT_TEMPLATE.md` exactly. At minimum report:

1. actual starting local/remote SHAs;
2. safety ref and rollback proof;
3. branch and PR URL;
4. all commits;
5. V3.1-ZH generation ID and manifest digest;
6. changed files grouped by phase;
7. before/after status for all 158 matrix rows;
8. exact test commands, exit codes, artifact paths, and hashes;
9. external verifier installation, service account boundary, public key fingerprint, policy version, and negative tests without secrets;
10. GitHub ruleset and required checks;
11. PR/auto-merge and bad-candidate evidence;
12. Claude live canary and restart evidence;
13. quota/auth/recovery evidence;
14. queue/lease/runtime status evidence;
15. native/value gate evidence;
16. milestone advancement evidence;
17. product regression results;
18. controller activation receipt and state;
19. remaining legitimate external waits;
20. remaining unproven GPU/customer/commercial claims;
21. exact deviations and blockers;
22. exact rollback procedure.

Do not say “fully autonomous,” “production ready,” “commercially validated,” “GPU validated,” or “complete” unless the corresponding acceptance evidence exists.

# 14. Exhaustive unresolved audit requirements

The following appendix is generated from the 158-row conformance matrix. Treat every row as required. The matrix file remains the canonical machine-readable source.

### Authority & migration

#### `A006` — Run the V3 migration on an isolated branch and draft PR.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Create a safety tag/ref now, stop direct migration on main, and use a hardening branch plus automated PR/merge queue going forward.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A007` — Do not let the current factory autonomously rewrite its governing rules.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Create a new V3.1-ZH source bundle explicitly approved as owner policy; do not shadow the original bundle with higher-precedence runtime files.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A008` — Keep the active authority internally non-contradictory.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Rewrite every affected active document coherently as V3.1-ZH, regenerate the manifest, update context routing, and archive V3 unchanged.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A009` — Route every active governing directive into role context.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Make the active source bundle itself authoritative; remove hidden override dependence. Ensure context manifests include the active policy digest.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A010` — Use a canonical active-source pointer and reject mixed authority generations.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Add active_generation metadata and fail closed when active contexts mix V3 and V3.1-ZH normative generations.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A011` — Record an actual safety ref and rollback path before migration.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Create an immutable tag at the pre-hardening SHA and rehearse exact rollback in a disposable clone.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A012` — Make source-monitor findings create STALE/ADR/wedge-review requests rather than silent rewrites.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Wire freshness receipts into context construction and create deterministic STALE work-item transitions.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A013` — Defer T002 from the product critical path while preserving legacy traceability.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Add a deterministic migration assertion that T002 is DEFERRED_NON_BLOCKING and cannot block any V3 milestone.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A014` — Preserve all 124 legacy entries, statuses, packets, and specs.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Add a manifest of all 124 source entries and deterministic count/hash/mapping tests.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A017` — Bind migration evidence to the exact candidate SHA and actual execution mode.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Separate SIMULATED, CONTROLLED_VALIDATED, and LIVE_VALIDATED evidence; do not let simulation satisfy live migration criteria.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A018` — Keep original V3 documents as an immutable review artifact after adopting a new owner policy.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Archive V3 as historical review generation and activate a new complete V3.1-ZH manifest.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Zero-human semantics

#### `B001` — No routine founder/operator intervention after bootstrap.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Define ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP and prove a live canary through task selection, model execution, recovery, release, and next-task scheduling.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B003` — Allow product/factory lanes to continue while market evidence waits.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Run a live test where market items wait while product/competitor/trust items continue.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B005` — If human trust approval is removed, disclose that this is a plan amendment rather than full V3 conformance.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Publish V3.1-ZH with explicit rationale, compensating controls, residual risk, and non-claim that it matches original V3.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B006` — Machine approval must be independent of the candidate-writing agent.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Use a separate root-owned/off-repo verifier with signed scoped receipts, policy version, issuer, expiry, candidate SHA, oracle IDs, and raw evidence hashes.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B008` — A technically valid native duplicate must fail product value.

- **Audit verdict:** `PARTIAL`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement and require NativeSubstituteBenchmark before NATIVE_ADVANTAGE_DEMONSTRATED or commercial promotion.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B010` — Market actions must be executable without founder orchestration where legally authorized.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Add an explicitly authorized MarketOperationsBackend, consent/identity controls, and attributable inbound/outbound event receipts, or accept external_wait.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Product strategy

#### `C002` — First serious offer is Incident-to-Change Qualification Pilot.

- **Audit verdict:** `PARTIAL`
- **Severity:** `INFO`
- **Required remediation:** Keep as hypothesis and collect external receipts.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C007` — Identity lock must be deterministic and candidate-bound.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Prove golden vectors with an independently implemented verifier, not the production serializer.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C012` — Customer-local execution/security is retained in architecture.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Build a controlled isolated runner and later obtain external customer-local evidence.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C013` — Complete-substitute comparison starts early and repeats.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Enable allowlisted current-source research and make native differential a recurring promotion gate.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C014` — Commercially support only surfaces that change real decisions.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Create signed external value receipt transition and block COMMERCIALLY_SUPPORTED without it.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### V3 model & roadmap

#### `D002` — Typed work lifecycle includes external/human/technical/value dispositions.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** For V3.1-ZH, replace WAITING_HUMAN with WAITING_MACHINE_AUTHORITY, not with implicit approval.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D005` — M0 completion must reflect actual evidence, not rewritten criteria.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Define V3.1-ZH M0 criteria first, then recompute from independent evidence; do not rewrite requirements during ledger generation.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D007` — External waits are non-blocking to unrelated lanes.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Add integration test and live canary.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D008` — Completion proposals cannot mutate authoritative roadmap directly.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Integrate proposal generation, deterministic validation, machine-authority acceptance, and bounded expansion.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D009` — Milestone completion is evaluated from evidence.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Invoke it at every idle/no-ready transition and after work-item completion.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D010` — Milestone advancement occurs automatically when gates pass.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement atomic transition, event, source digest, next milestone activation, and rollback.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D011` — Roadmap expansion is finite and cannot be silently accepted.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Implement one bounded proposal round and machine-authority acceptance/rejection.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D013` — Work items bind source/context/candidate/evidence.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Populate source groups, output contracts, evidence requirements, and candidate digest in every packet.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D014` — Static roadmap status cannot substitute for runtime state.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Create one authoritative runtime state store and derive dashboards from it.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Scheduler & recovery

#### `E003` — Task lease is renewed during long execution.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Add heartbeat/lease-renewal coroutine and ownership token; abort if renewal fails.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E004` — Expired work resumes from durable candidate/session state rather than restarting ambiguously.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Persist backend-neutral SessionRef and resume token; recover candidate worktree/checkpoint exactly.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E005` — Quota limits create QUOTA_WAIT and automatic resume.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Propagate typed quota/auth dispositions to scheduler, persist resume_at, and retry after reset.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E006` — Authentication expiry creates AUTH_EXPIRED wait and automatic recheck.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Add typed auth wait and credential refresh without exposing token.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E007` — Finite candidate repair cycles are actually executed.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement repair sessions, candidate preservation, exact findings, and rerun independent checks.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E008` — At most two re-specifications, then terminal disposition.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Implement bounded packet recompile with requirement digest and terminal NARROW/DEFER/REJECT/MACHINE_REVIEW.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E009` — Repeated identical findings trigger no-progress handling.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Hash normalized finding+candidate and stop after configured repeat threshold.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E010` — Factory self-repair is finite and does not rewrite product truth.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Route only controller defects to one bounded repair, with independent gate and no requirement changes.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E011` — Restart policy uses finite exponential backoff and HARD_STUCK.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Run kill-loop test and verify exact backoff/HARD_STUCK persistence.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E012` — Single-instance lock governs all launcher paths.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Test Windows scheduled task plus manual duplicate launch against same lock.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E014` — autonomy.enabled must be authoritative.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Refuse run when disabled unless an explicit one-shot simulation flag is used.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E015` — Runtime root may live outside repository safely.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Use URI/absolute runtime references and a safe display helper; route all state/worktrees/artifacts through runtime root.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E016` — Queue CLI/status and controller use the same queue root.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Centralize path resolution in one config object and regression-test every command.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E017` — Interrupted mutating candidates are salvaged automatically.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Add crash-at-each-phase tests and automatic candidate transplant/quarantine behavior.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Backend & execution

#### `F002` — Claude is first backend, not durable state model.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Persist neutral session references and implement actual resume semantics.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F003` — Backend capability report is truthful.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Report resume=False until implemented, then add crash/restart tests before enabling.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F004` — Mutating roles receive Write/Edit only when authorized by work item.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Derive tools from mutability and allowed paths, not role string.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F006` — Role-specific network policy supports current research without broad network.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement allowlisted HTTPS source adapters for research/market/competitor lanes; keep product/trust default deny.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F007` — Finite wall-clock timeout is enforced.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Wrap stage query in cancellable timeout and persist typed TIMEOUT disposition.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F008` — Bash allowlist is enforced.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Gate commands at hook/controller boundary and reject undeclared executable/arguments.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F009` — Transcripts are redacted and retained by policy.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Store structured event summaries, redact prompt/source/private payloads, and enforce retention expiry.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F010` — Task packets name required outputs.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Generate stable output IDs/paths/schemas and fail if required outputs are missing.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F011` — Agent reports conform to a strict V3 schema.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Use versioned AgentExecutionReport with verdict, findings, owner, evidence, changed files, commands, limits, next action.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F012` — Candidate manifests preserve findings and external evidence.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Fan in validated role reports and external receipts; never drop non-pass evidence.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F013` — Handoffs are backend-neutral and durable.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Persist schema-versioned handoffs independent of transcript/session implementation.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F014` — Source path references in packets exist.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Use manifest-resolved source IDs; startup must reject any missing source before claiming a task.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F015` — Market lane can write account/interview/evidence artifacts.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Create lane-specific writable roots and task-specific output paths.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F016` — Competitor lane can write capability/source registers.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Authorize exact research output roots; protect normative docs from direct mutation.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F017` — Trust lane can write test/evidence artifacts but not authority.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Declare trust evidence paths and external verifier ownership.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F018` — Context routing is lane/task specific.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Add deterministic lane+task context selectors and tests preventing advisory/acquisition leakage.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F019` — Current-fact freshness receipts are supplied.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Implement a source-retrieval service that records source URL/version/time/hash/control and passes receipt IDs.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Trust, value & release

#### `G002` — Observed boundary remains distinct from causal mechanism.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Maintain in first incident pack and independent oracle tests.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G005` — Machine policy approval is evaluated before release.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Make signed machine receipt a mandatory pre-release gate for all standard/integration/trust work.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G006` — Machine policy verifier is external and immutable to candidate agents.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Move verifier and private oracle out of repository/agent access; root-own it and sign receipts.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G007` — Receipt is scope-bound, expiring, attributable, and revocable.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Add policy_id/version, issuer key ID, allowed claims, work item, risk, candidate, expiry, nonce, revocation status, oracle identities.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G009` — Value/native disposition is applied to work-item maturity.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Run value evaluator after technical pass and before maturity/release transition.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G010` — Complete-substitute benchmark is a required promotion gate.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Create benchmark schema/executor and require evidence for native-advantage state.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G012` — Release does not put an unverified candidate on main.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Use automated PR + required checks + merge queue/auto-merge; zero human involvement does not require direct-main push.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G013` — Server-side branch protection/required checks enforce release policy.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Enable branch protection/ruleset, required workflows, no force/deletion, and merge queue or equivalent.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G014` — Private gate is mandatory where risk requires it.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Fail closed when required private runner/receipt is absent; test with hidden mutations.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G016` — GPU validation is separate and truthful.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Do not elevate GPU maturity; require signed exact-SHA runner evidence when available.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G018` — Green CI cannot certify policy that rewrites the requirements being audited.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Separate conformance tests from policy implementation; test against immutable V3.1-ZH manifest and external verifier.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Live autonomy & operations

#### `H001` — Controller is enabled and running only after migration gates pass.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Do not start until P0 defects are fixed; then run observation/canary and enable via signed activation receipt.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H002` — A real Claude-backed work item completes unattended.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Run a harmless mechanical canary with real Claude, exact artifacts, restart, and automatic next selection.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H003` — A live controller survives process kill and resumes the same work item.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Kill during planning, execution, gate, publication, and verify idempotent recovery each time.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H004` — A quota event pauses and resumes without human action.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement typed pause/resume and run injected plus real-reset canaries.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H005` — A failed CI release is contained before main.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Move to pre-merge required checks and test a deliberately failing candidate.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H006` — A repeated product defect stops finitely rather than loops.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Run deterministic repeated counterexample canary and verify terminal disposition.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H007` — A waiting external item does not stall product work.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Create concurrent lane fixture and live no-network canary.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H008` — Milestone advances automatically after evidence gates.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement and canary M1→M2 in a disposable roadmap.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H009` — Status shows authoritative milestone, lane, retry budget, blockers, candidate, CI, and release.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Unify runtime state and add stale/mismatch tests.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H010` — Portable Windows/WSL startup has no hardcoded personal paths.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Run install/start/status/stop in a fresh user/path and WSL distribution.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H013` — Automatic publication is idempotent across crash/restart.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Test crash before push, after push, during checks, before merge, after merge, and during rollback.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H014` — Supervisor preflight reads V3 queue/checkpoint/runtime locations.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Route preflight through the same V3 PathConfig and enumerate active leases/checkpoints.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H015` — Controller cannot operate when source integrity or machine authority is missing.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Make both mandatory before claim/merge; refuse any publication without signed activation/policy receipt.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H016` — Runtime events distinguish simulation, controlled validation, live validation, and external validation.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Add evidence_class enum and prevent lower classes from satisfying higher gates.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Product implementation

#### `I012` — Real GPU behavior is exact-SHA and environment-bound.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Add environment digest, runner identity, raw logs, and signed receipt when run.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Research & market lanes

#### `J001` — Reachable-account map is generated from attributable sources.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Fix lane execution; use public/company/contact sources and label uncertainty.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J002` — Interview guide and pilot qualification artifacts are created.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Declare and generate versioned artifacts with evidence/source boundaries.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J008` — Competitor/source register is current and freshness-bound.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Enable allowlisted adapters and scheduled source-monitor work items.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J009` — Teyon/Harbor/TrainCheck/TrainVerify/TTrace/Clockwork are tracked.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Add source-specific checks and last-verified timestamps.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J010` — TrainCheck differential is explicitly tested against incident-derived contracts.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Create a controlled healthy-invariant versus incident-derived qualification comparison.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J011` — Trust lane independently attacks false green, identity, evidence, and release.

- **Audit verdict:** `PARTIAL`
- **Severity:** `CRITICAL`
- **Required remediation:** Use off-repo hidden verifier and real adversarial canaries.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J012` — Research process distinguishes CLEAR/CONFLICT/UNKNOWN and preserves raw controls.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Integrate V3 research tasks with preregistered query/evidence manifest policy.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.


# 15. Begin

Begin now with Phase 0. Re-baseline the actual repository, preserve all state, keep the controller stopped, and proceed through the phases. Do not return only a plan.
