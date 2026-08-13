# CODEX MASTER MIGRATION AND INITIAL PRODUCT PROMPT

You are operating on the local checkout of:

```text
https://github.com/TasfiqJ/TrainCapsule.git
```

Your assignment is to migrate the repository from the current V2 bootstrap/autonomous-factory shape to the TrainCapsule V3 bounded commercial-product strategy, without losing history, runtime evidence, candidate work, or rollback ability.

This is a repository migration and first bounded product implementation. It is not authorization to build the entire historical 124-task platform.

## 0. Inputs

An accompanying V3 review bundle contains these files:

```text
README_FIRST.md
REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md
00_EXECUTIVE_BUILD_DECISION_V3.md
03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md
04_TECHNICAL_ARCHITECTURE_V3.md
05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md
06_COMMERCIAL_MODEL_AND_GTM_V3.md
FACTORY_LOOP_REDESIGN_SPEC.md
12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md
SOURCE_OF_TRUTH_MIGRATION_PLAN.md
13_SOURCE_REGISTER_V3.md
14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md
examples/
FINAL_MANIFEST_V3.json
```

Locate the bundle by searching for `README_FIRST.md` and `FACTORY_LOOP_REDESIGN_SPEC.md` outside and inside the repository. Prefer a directory explicitly supplied to the session. Do not download an arbitrary similarly named bundle from the internet.

When the bundle cannot be found:

1. make no repository changes;
2. write a short local `MISSING_V3_REVIEW_BUNDLE.md` outside the repository or in the session output;
3. report the exact expected filenames;
4. stop.

## 1. Non-negotiable outcome

At completion:

1. V3 documents are installed as the active source of truth; the 9 August bundle remains an immutable archive.
2. The factory uses typed V3 work items, milestones, lanes, dispositions, maturity, external evidence, and human approval.
3. No zero value means unlimited retries, respecifications, redesigns, completion expansions, or controller restarts.
4. The scheduler is lane-aware and critical-path/value-aware rather than list-order-only.
5. A blocked external or human item does not globally block unrelated product work.
6. Completion reviewers can propose work but cannot mutate the authoritative roadmap.
7. Claude is behind a backend-neutral executor protocol.
8. Release defaults to a draft pull request, not direct `main` promotion.
9. Factory CI is separated from product/source/security CI.
10. Startup controls have bounded restart/backoff and no hardcoded personal path.
11. Legacy tasks and state are preserved and migrated, but T001–T124 no longer define V3 company completion.
12. Product code exists separately from `tcfactory`.
13. The first product vertical reaches local install → Flight Recorder import fixture → identity/evidence lock → native baseline → evidence completeness → eligibility/preflight.
14. No customer, payment, adoption, native-advantage, or human-approval evidence is fabricated.
15. All changes are on a dedicated branch with a draft PR; do not merge it.

## 2. Safety and Git rules

Before editing:

1. Run `git status --short --branch`.
2. Record:
   - repository path;
   - current branch;
   - current HEAD;
   - remote URL;
   - uncommitted changes;
   - currently running TrainCapsule/factory processes;
   - configured scheduled task/service where discoverable without privilege escalation.
3. The audit baseline was:
   `c31caefaeed7e605f6ef304fae6fcfe708a163b9`.
4. Do not assume HEAD still equals that SHA.
5. Fetch `origin` without resetting or overwriting local work.
6. When there are user changes:
   - do not discard or stash them without explicit permission;
   - create a report and stop before mutating tracked files.
7. Stop the local TrainCapsule scheduled/autopilot process using existing safe controls where possible.
8. Verify it is stopped before schema/config migration.
9. Create a local safety branch or ref:
   `safety/pre-v3-<timestamp>`.
10. Create the work branch:
    `codex/traincapsule-v3-migration`.
11. Never force-push.
12. Never push directly to `main`.
13. Do not create or modify credentials.
14. Do not print OAuth tokens, environment secrets, private trace contents, or local runtime transcripts into Git.
15. Do not delete local runtime state under the external `projects/traincapsule/factory/` location.

Create an audited migration snapshot under a local non-secret path. Include hashes and metadata, not raw credentials.

## 3. Read and inspect before implementation

Read at least:

```text
SOURCE_PRECEDENCE.md
docs/CONTEXT_INDEX.yaml
docs/source-of-truth/final-2026-08-09/00_EXECUTIVE_BUILD_DECISION.md
docs/source-of-truth/final-2026-08-09/03_PRODUCT_STRATEGY_AND_REQUIREMENTS.md
docs/source-of-truth/final-2026-08-09/04_TECHNICAL_ARCHITECTURE.md
docs/source-of-truth/final-2026-08-09/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC.md
docs/source-of-truth/final-2026-08-09/12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md
docs/source-of-truth/final-2026-08-09/14_CLAUDE_CODE_MASTER_BUILD_PROMPT.md
factory/feature_ledger.yaml
factory/task_catalog.yaml
factory/product_definition_of_done.yaml
tasks/T002.yaml
config/factory.yaml
config/autonomy.yaml
config/roles.yaml
config/context.yaml
config/value_policy.yaml
config/github.yaml
tcfactory/models.py
tcfactory/autopilot.py
tcfactory/feature_ledger.py
tcfactory/queue.py
tcfactory/planner.py
tcfactory/pipeline.py
tcfactory/completion.py
tcfactory/value.py
tcfactory/research_policy.py
tcfactory/quality_policy.py
tcfactory/self_repair.py
tcfactory/context.py
tcfactory/claude_runner.py
tcfactory/github_sync.py
tcfactory/gitops.py
tcfactory/gates.py
prompts/global.md
prompts/autonomous_planner.md
prompts/research.md
prompts/builder.md
prompts/adversary.md
scripts/windows_task_entrypoint.sh
scripts/factory_control.sh
Control-TrainCapsuleBuilder.ps1
.github/workflows/*
pyproject.toml
README.md
```

Run the existing test suite and record the baseline. Do not “fix” unrelated failures silently. The migration report must distinguish pre-existing failures from introduced failures.

Create:

```text
docs/migrations/V3_BASELINE_REPORT.md
```

It must include current HEAD, audit-baseline comparison, test/CI baseline, active queue/packet summary, and any deviations that affect this prompt.

## 4. Implementation discipline

- Work in small reviewable commits.
- Preserve existing public APIs until their replacement has tests.
- Prefer additive V3 modules and adapters before deleting V2 code.
- Every config/state format change requires a version, validation, migration, and rollback.
- Every critical behavior requires positive and negative tests.
- Do not weaken current hidden/private gate security.
- Do not use a text-only test where executable behavior can be tested.
- Do not add a placeholder and call the phase complete.
- Do not implement deferred hosted/provider/platform breadth.
- Keep the repository private.
- Do not mark external milestones complete.

## 5. Phase A — Install the V3 authority bundle

### 5.1 Copy V3 documents

Create:

```text
docs/source-of-truth/v3-2026-08-11/
```

Copy the authoritative V3 files from the review bundle. Create `README.md` explaining:

- V3 is active after migration approval;
- the old bundle is historical;
- normative versus current factual authority;
- no customer/commercial claims are implied;
- migration base SHA.

Do not edit the copied V3 normative text unless needed to fix a verifiable path/format error. Record any change in the migration report.

### 5.2 Replace `SOURCE_PRECEDENCE.md`

Implement the authority model in `SOURCE_OF_TRUTH_MIGRATION_PLAN.md`.

Required behavior:

- active V3 directory;
- immutable historical bundle;
- signed human approval is scoped and SHA-bound;
- separate normative and current factual authority;
- source-monitor findings produce `STALE`/ADR/wedge-review requests, not silent policy rewrites;
- acquisition/career documents are advisory;
- duplicate `(1)` files are excluded from active authority;
- no broad glob ambiguity.

### 5.3 Replace `docs/CONTEXT_INDEX.yaml`

Version 3. Create explicit context groups:

```text
product_normative
technical_architecture
trust_core
commercial
roadmap
current_facts
factory_control
advisory_acquisition
advisory_career
```

Every entry includes:

- path;
- authority class;
- scope;
- include/exclude roles;
- freshness policy where applicable.

Routine product work must not receive career/acquisition context.

### 5.4 Manifest and integrity gate

Create a deterministic generator:

```text
scripts/generate_v3_manifest.py
```

Create:

```text
docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json
```

Hash normalized UTF-8 LF text with one trailing newline. Do not include a self-hash. Include migration base SHA and authority class.

Create:

```text
scripts/gates/source_of_truth_integrity.py
```

Tests must detect:

- missing file;
- changed hash;
- duplicate logical ID;
- active `(1)` file;
- self-hash;
- old bundle treated as active;
- unresolved context path;
- mixed normative/current-fact hierarchy;
- synthetic external evidence marked as commercial completion.

Add unit tests under `tests/test_source_of_truth_integrity.py`.

Commit this phase separately.

## 6. Phase B — Add V3 domain models and schemas

Prefer new modules over making `tcfactory/models.py` even larger.

Create:

```text
tcfactory/v3/
├── __init__.py
├── enums.py
├── work_items.py
├── milestones.py
├── maturity.py
├── approvals.py
├── external_evidence.py
├── dispositions.py
├── scheduler.py
├── retry_policy.py
├── migrations.py
└── candidate_manifest.py
```

Create JSON schemas under:

```text
schemas/factory/v3/
```

### 6.1 Enums

Implement exact enums:

```python
class Lane(str, Enum):
    PRODUCT = "PRODUCT"
    MARKET = "MARKET"
    COMPETITOR = "COMPETITOR"
    TRUST = "TRUST"
    FACTORY = "FACTORY"

class WorkKind(str, Enum):
    CODE = "CODE"
    SPECIFICATION = "SPECIFICATION"
    RESEARCH = "RESEARCH"
    CONTROLLED_EXPERIMENT = "CONTROLLED_EXPERIMENT"
    EXTERNAL_EVIDENCE = "EXTERNAL_EVIDENCE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    COMMERCIAL_EXPERIMENT = "COMMERCIAL_EXPERIMENT"
    MAINTENANCE = "MAINTENANCE"
    MIGRATION = "MIGRATION"

class WorkStatus(str, Enum):
    PROPOSED = "PROPOSED"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED_QUOTA = "PAUSED_QUOTA"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    WAITING_HUMAN = "WAITING_HUMAN"
    BLOCKED_TECHNICAL = "BLOCKED_TECHNICAL"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    PASSED_ENGINEERING = "PASSED_ENGINEERING"
    REJECTED_VALUE = "REJECTED_VALUE"
    NATIVE_SUFFICIENT = "NATIVE_SUFFICIENT"
    DEFERRED = "DEFERRED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"

class Disposition(str, Enum):
    KEEP = "KEEP"
    INTEGRATE_EXISTING_BACKEND = "INTEGRATE_EXISTING_BACKEND"
    UPSTREAM = "UPSTREAM"
    NARROW = "NARROW"
    REPLACE = "REPLACE"
    PAUSE = "PAUSE"
    STOP = "STOP"
    NOT_REVIEWED = "NOT_REVIEWED"
```

Engineering and commercial maturity enums must match the V3 docs.

### 6.2 `WorkItem`

Use strict Pydantic models with `extra="forbid"`.

Required fields:

- version;
- work item ID;
- title;
- lane;
- kind;
- milestone ID;
- decision contribution;
- customer outcome;
- hard and soft dependencies;
- commercial-release blocker flag;
- priority;
- risk tier;
- target maturity;
- disposition;
- status;
- owner type;
- automatable;
- packet path;
- evidence requirements;
- external receipt requirement;
- human approval requirement;
- retry policy;
- timestamps.

Validation:

- AI-owned item cannot be `EXTERNAL_EVIDENCE` or `HUMAN_REVIEW`;
- external/human items are not automatable;
- completed commercial items require trusted receipts;
- no missing dependency;
- no self-dependency;
- IDs are stable and unique;
- status transitions are explicit;
- target commercial maturity cannot exceed evidence.

### 6.3 Milestone

Implement bounded milestone models with entry/exit criteria, evidence, forbidden claims, and approval requirement.

No global “all product tasks done” milestone.

### 6.4 Human approval

Implement `HumanApprovalRecord` and verifier.

Requirements:

- exact candidate SHA;
- artifact digests;
- scope enum;
- reviewer identity and qualification text;
- decision, conditions, limitations, expiry;
- signature or approved external root;
- trusted approval root configurable outside agent-writable worktrees;
- expired/wrong-SHA/wrong-scope/agent-writable approval rejected.

Do not create a real approval fixture that can be confused with external approval. Test fixtures are labeled synthetic and isolated.

### 6.5 External evidence

Generalize the existing external value receipt.

Evidence types:

```text
CUSTOMER_CONVERSATION
INCIDENT_ARCHIVE_ACCESS
PAID_PREFLIGHT
PAID_PILOT
DECISION_CHANGED
SECOND_PAID_ACTION
INDEPENDENT_OPERATOR
HUMAN_REVIEW
UPSTREAM_ACCEPTANCE
PROVIDER_ACCEPTANCE
```

Requirements:

- issuer;
- date;
- subject;
- outcome;
- limitations;
- signature/trusted location;
- exact offer/candidate identity where applicable;
- synthetic fixture cannot advance commercial maturity.

### 6.6 Candidate manifest

Bind:

- base/candidate SHA;
- work item;
- packet/context digests;
- executor/backend identity;
- stage outputs;
- gate versions/results;
- findings;
- approvals;
- external evidence references;
- release decision.

Tests must fail on artifact substitution.

Commit this phase separately.

## 7. Phase C — Finite policy and lane-aware scheduling

### 7.1 Config files

Create:

```text
config/scheduler.yaml
config/milestones.yaml
config/human_approval.yaml
config/external_evidence.yaml
config/commercial_maturity.yaml
config/executors.yaml
```

Upgrade existing config to version 3 with migration support.

No zero value may mean unlimited. Explicitly reject zero for maximum attempts unless zero semantically means disabled and is documented per field.

Recommended defaults:

```yaml
maxPlanAttempts: 2
maxCandidateRepairCycles: 3
maxSameFindingRepeats: 2
maxCandidateRestarts: 1
maxInfrastructureRecoveriesPerRun: 3
maxFactorySelfRepairsPerIncident: 1
maxControllerRestarts: 3
maxValueRedesigns: 1
maxCompletionExpansionRounds: 1
maxExpansionItems: 5
roadmapExpansionRequiresHumanApproval: true
maxConcurrentMutatingSessions: 1
maxConcurrentReadOnlySessions: 1
```

Remove or deprecate `work_until_done: true`. A controller run advances work and checkpoints; it does not guarantee global completion.

### 7.2 Scheduler

Implement `tcfactory/v3/scheduler.py`.

Behavior:

- evaluate hard dependencies;
- isolate `WAITING_EXTERNAL` and `WAITING_HUMAN`;
- honor lane WIP;
- compute inspectable score from V3 spec;
- prioritize active milestone critical path;
- run competitor/native checks before duplicative implementation where configured;
- deterministic tie-breaking;
- no list-order default;
- no global block from one lane;
- founder override requires a signed/explicit decision record;
- produce a scheduler-decision artifact each cycle.

Add simulation CLI:

```text
tcfactory v3-schedule --dry-run --explain
```

### 7.3 Queue

Adapt `tcfactory/queue.py` or add V3 queue implementation.

Requirements:

- typed V3 entries;
- atomic moves;
- state transition validation;
- per-lane views;
- no duplicate active work item;
- recovery of interrupted item;
- archived V2 queue;
- no automatic V2 resume.

### 7.4 Retry policy

Implement finding fingerprint counts and bounded transitions.

When the same blocking finding repeats twice:

- preserve candidate;
- set `BLOCKED_TECHNICAL`;
- create a proposal for `NARROW`, `REPLACE`, or human review;
- do not continue the same loop.

When value redesign fails twice:

- set `REJECTED_VALUE` or `NATIVE_SUFFICIENT`;
- do not append implementation tasks.

When controller restarts exceed budget:

- write `HARD_STUCK.json`;
- stop launcher;
- include exact recovery instructions.

Tests:

- zero/unlimited rejected;
- independent lane progress;
- deterministic order;
- WIP;
- repeat finding;
- external/human wait;
- rejected value;
- hard stuck.

Commit this phase separately.

## 8. Phase D — Planner, pipeline, completion, and context changes

### 8.1 Planner

Modify `tcfactory/planner.py`.

Add hard packet limits:

- <=12 acceptance criteria;
- <=8 outputs;
- <=8 source documents by default;
- explicit decision contribution;
- explicit non-goals;
- oracle;
- rollback;
- stop conditions.

Reject:

- universal company criteria;
- external evidence created by AI;
- output/path contradictions;
- mixed product/factory changes;
- generic production/commercial wording;
- packet that restates full source bundle;
- oversized task without approved split.

Cache/reuse valid packet by work item/source/base digest.

### 8.2 Stage policy

Retain one writable owner and candidate-bound review for relevant work, but make review depth risk-based.

- mechanical: deterministic gates, optional review;
- standard: owner + deterministic gates + targeted verifier;
- integration: owner + independent adversary + journey;
- trust core: owner + independent oracle/adversary + human release approval.

Do not require an expensive adversarial session for a simple naming or formatting task.

### 8.3 Pipeline

Refactor incrementally; do not attempt a dangerous all-at-once rewrite unless tests prove parity.

Introduce clear services or functions for:

- candidate lifecycle;
- findings;
- value;
- human gate;
- external gate;
- release candidate;
- recovery.

Preserve existing exact-SHA/worktree/candidate-transplant strengths.

Route findings by owner class:

```text
PRODUCT
FACTORY
EXTERNAL
HUMAN
```

Advisory findings do not block.

No factory repair may change V3 normative docs, approval policy, external receipts, private gates, or value thresholds.

### 8.4 Completion

Change `tcfactory/completion.py`.

- completion is per milestone;
- deterministic evidence first;
- one independent adversarial review for integration/trust milestones;
- human approval for external release;
- reviewers write proposals only;
- authoritative roadmap mutation requires explicit accepted proposal;
- maximum one expansion round and five proposals;
- external milestones require trusted receipts;
- controlled fixtures cannot complete M3–M6.

### 8.5 Context

Modify `tcfactory/context.py`.

- consume V3 context index;
- emit manifest with digests/authority/relevance;
- exclude career/acquisition from routine tasks;
- distinguish current facts;
- freshness policy;
- context-size budget;
- missing/stale required fact blocks only affected work item.

### 8.6 Value

Modify `tcfactory/value.py` and policy.

Apply decision-level value gates only to:

- product outcomes;
- major integrations;
- packs;
- performance/economic claims;
- commercial milestones.

Mechanical/refactor/maintenance work inherits parent-milestone necessity and uses engineering acceptance.

Add terminal outcomes:

```text
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
INCREMENTAL_DECISION_VALUE_DEMONSTRATED
EXTERNAL_EVIDENCE_REQUIRED
```

A weak outcome must stop/defer the surface, not create unlimited work.

### 8.7 Catalog compiler

Modify `tcfactory/catalog.py` after the V3 models exist.

- remove the hard-coded `T002` output path;
- compile typed work items, not the archived 124-task sequence;
- use task-type templates;
- validate expected outputs are writable by the owner stage;
- cap packet complexity;
- include lane, milestone, maturity target, decision contribution, oracle, rollback, and stop disposition;
- invalidate cached/generated packets when the work item, template, context, source, or compiler digest changes;
- never set `auto_merge=True` for integration, trust-core, authority, or externally released work;
- do not infer a private-gate suite from risk alone when a capability-specific suite is required.

Add catalog/compiler tests for:

- no special task IDs;
- deterministic output;
- stale packet rejection;
- path/output consistency;
- criteria/output/source limits;
- correct task-type template;
- prohibited commercial boilerplate on mechanical tasks.

### 8.8 Configuration migration

Modify `tcfactory/config.py`.

- V2 may be read only by the migration command;
- normal V3 operation rejects mixed or legacy config;
- migrate as an atomic transaction with rollback copy;
- record which file or permitted environment override supplied each effective value;
- prohibit environment overrides of release mode, human authority, receipt trust, private-gate policy, security boundaries, or kill gates;
- replace `TCF_MAX_PARALLEL` with explicit lane/session limits;
- add `tcfactory config validate`, `config explain`, and `config migrate --dry-run`.

### 8.9 Claude feature adapter

Modify `tcfactory/claude_features.py`.

- change stale `rp-` session names to `tc-`;
- remove renewable-work-until-complete language from goal text;
- independently capability-check messaging, advisor, goal, workflow, and teams;
- treat every peer message as advisory until written to a durable handoff;
- do not make messaging, advisor, or workflow support a calibration prerequisite;
- require a named question before launching an integration scout;
- cap peer turns, message count, context, and wall time;
- provide deterministic no-feature fallback behavior.

### 8.10 Operator CLI

Refactor `tcfactory/cli.py` without breaking safe read-only legacy commands during migration.

Add commands:

```text
tcfactory migrate --dry-run
tcfactory config validate
tcfactory config explain <field>
tcfactory lanes
tcfactory milestones
tcfactory work explain <id>
tcfactory approvals list|show|record
tcfactory evidence validate <receipt>
tcfactory competitors status
tcfactory pilot init|validate|status
tcfactory kill-gates
tcfactory product doctor
```

Requirements:

- status shows lane, milestone, maturity, scoped blocker, attempts remaining, and approval status;
- `doctor` validates both factory and product runtime;
- no CLI command silently edits and commits `main`;
- autonomy enablement produces a reviewable local diff or PR and requires explicit acknowledgement;
- generic resume cannot override `WAITING_HUMAN`, kill, rejected-value, or stopped dispositions;
- overrides require reason and immutable decision record;
- output that may enter Git or a support package is secret- and path-sanitized;
- calibration is risk-specific and does not require every role or optional Claude feature.

### 8.11 Risk routing and prompt composition

Modify `tcfactory/risk.py` and `tcfactory/prompts.py`.

`risk.py` must no longer:

- replace allowed paths with `**`;
- set `work_until_done=True` internally;
- clear turn/token/budget ceilings;
- choose private-gate suites by numeric `T###` ranges;
- force `github_push=True`;
- add the same broad adversary to every non-mechanical task.

Use typed task/capability risk. Preserve path scope. Review depth and gate suites are selected by changed capability and threat model. Repeated failure changes state/disposition; it does not automatically buy a larger model.

`prompts.py` must no longer instruct every task to read all company, buyer, acquisition, and release context or continue through renewable sessions. Enforce context-manifest scope, prompt-size limits, information-class exclusions, and explicit lawful terminal states such as `DEFER`, `NATIVE_SUFFICIENT`, `REJECTED_VALUE`, and `WAITING_HUMAN`.

### 8.12 Durable support state

Upgrade:

```text
tcfactory/handoffs.py
tcfactory/peer_messaging.py
tcfactory/quota.py
tcfactory/ledger.py
tcfactory/usage.py
tcfactory/observability.py
tcfactory/provenance.py
```

Requirements:

- versioned, digest-bound, backend-neutral handoff;
- no required Claude session ID/model semantics;
- lane/milestone/work item/disposition/attempt state;
- peer messages advisory until referenced artifact digest is validated;
- validate peer artifact paths inside the permitted artifact root;
- machine-readable quota events preferred, regex fallback redacted and false-positive tested;
- paid-overage route is a hard refusal;
- bounded quota probes;
- concurrency-safe ledger/event append;
- estimated API-equivalent cost separated from actual subscription capacity;
- event schema, sequence, redaction, exportability class, and corruption warning;
- no silent skipping of malformed durable state.

Also upgrade `tcfactory/util.py` and retain `tcfactory/yamlutil.py` duplicate-key rejection. Use atomic validated writes with temporary files, `fsync`, parent synchronization where supported, critical-record rollback generations, and an explicit locking/single-writer rule. Add path-resolution helpers that reject escapes and symlink surprises, and environment-specific subprocess wrappers so controller secrets are not inherited unintentionally.

Commit this phase separately.

## 9. Phase E — Backend-neutral executor

Create:

```text
tcfactory/backends/
├── __init__.py
├── base.py
└── claude.py
```

Protocol:

```python
class EngineeringAgentBackend(Protocol):
    def capabilities(self) -> AgentCapabilityReport: ...
    def start(self, request: AgentTaskRequest) -> AgentSession: ...
    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult: ...
    def cancel(self, session: AgentSession) -> None: ...
    def usage_state(self) -> UsageState: ...
```

Adapt existing `claude_runner.py` behind `ClaudeBackend`. Preserve subscription authentication and quota recovery.

Move `tcfactory/auth.py` behind the Claude backend as `ClaudeCredentialProvider` while retaining its fail-closed protections. Add redaction tests proving that tokens, account identifiers, token-file paths, and controller-only secret paths cannot enter model prompts, artifacts, PR descriptions, or exception logs. Expose only a backend-neutral state such as `AUTHENTICATED`, `AUTH_EXPIRED`, `QUOTA_WAIT`, or `ROUTE_REFUSED`.

Upgrade `tcfactory/checkpoints.py`:

- schema version and content digest;
- previous valid generation/atomic rollback;
- quarantine corrupt or incompatible checkpoints;
- a corrupt active checkpoint is blocking, never silently ignored;
- backend-neutral session reference;
- work item, lane, milestone, budget, context/source digest, candidate SHA, approval state, and circuit-breaker reason;
- tests for partial writes, power loss, stale candidate, incompatible version, duplicate active work, and recovery.

Factory-owned state must not contain Claude-only assumptions.

Add explicit weekly/role allocation and concurrency policy even though monetary API budget is disabled.

Do not add another vendor backend unless needed for a contract test. A fake backend for deterministic unit testing is acceptable and must be named `FakeBackend`.

Refactor `tcfactory/structured_runner.py` through the backend protocol. Preserve schema output, sandboxing, and network denial, but remove the subscription-unbounded branch. Add finite wall time, cancellation, transcript redaction/retention, backend-neutral usage, and an explicit Bash allowlist. Do not serialize raw SDK messages when they may contain source, prompts, or private evidence.

## 10. Phase F — GitHub/PR release and CI

### 10.1 Release mode

Change default to:

```yaml
releaseMode: pull_request
directMainPush: false
```

Verified candidate flow:

```text
candidate branch
→ release branch
→ push
→ draft PR
→ required CI
→ human/authorized merge
```

Do not merge the migration PR.

Mechanical auto-merge remains disabled during initial migration. Integration/trust auto-merge is always false.

Preserve exact-SHA verification.

### 10.2 GitHub sync

Refactor `github_sync.py` so direct-main behavior is not the only path.

Implement:

- branch push;
- draft PR create/update;
- candidate SHA verification;
- required workflow status;
- no force;
- divergence detection;
- release metadata.

### 10.3 CI workflows

Create/rename:

```text
.github/workflows/factory-quality.yml
.github/workflows/product-unit.yml
.github/workflows/product-contract.yml
.github/workflows/security.yml
.github/workflows/source-of-truth-integrity.yml
```

Later GPU workflow can be separate.

Use GitHub-hosted runners for CPU/source/factory checks. Do not make one self-hosted runner the sole required validation.

Requirements:

- least permissions;
- pinned action SHAs where practical;
- timeouts;
- concurrency;
- artifact retention;
- exact package/test scope;
- no secrets in PR jobs.

Make workflow naming consistent with `config/github.yaml`.

## 11. Phase G — Startup and controls

### `scripts/windows_task_entrypoint.sh`

Replace infinite fixed restart loop with:

```text
attempt 1: 15 seconds
attempt 2: 60 seconds
attempt 3: 5 minutes
then HARD_STUCK and exit nonzero
```

Reset only after a configured healthy interval.

Before start:

- config version;
- source integrity;
- single-instance lock;
- credentials;
- migration-complete marker;
- clean required runtime state.

### PowerShell

Remove hardcoded repository and WSL distribution assumptions from `Control-TrainCapsuleBuilder.ps1`.

Support parameters/config:

```powershell
-RepoPath
-WslDistribution
-FactoryRuntimePath
-Action
```

Actions should include status, pause, resume, recover, stop, schedule dry-run, and milestone status.

Never display OAuth secrets.

### Dashboard/status

Show:

- active milestone;
- current work item and lane;
- retry budget;
- restart budget;
- human blockers;
- external blockers;
- candidate SHA;
- factory CI;
- product CI;
- last release PR.

## 12. Phase H — Prompt migration

Update existing prompts to match `14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md`.

Create:

```text
prompts/native_substitute_reviewer.md
prompts/commercial_experiment.md
prompts/human_approval_packet.md
prompts/wedge_reviewer.md
prompts/milestone_auditor.md
```

Rules:

- no “work until done”;
- no unlimited scope;
- no fabricated external truth;
- no automatic roadmap mutation;
- no career/acquisition context;
- native first;
- `UNKNOWN`;
- bounded finding format;
- human stop state;
- finite packet size.

Add tests that inspect prompt contracts only where text is genuinely normative; avoid brittle whole-repo substring policing.

## 13. Phase I — Legacy migration

Create:

```text
factory/roadmap/migrations/v2_to_v3.yaml
factory/roadmap/legacy_feature_ledger.yaml
factory/roadmap/milestones.yaml
factory/roadmap/work_items.yaml
factory/roadmap/dispositions.yaml
```

Requirements:

- preserve all 124 legacy entries and statuses;
- record mapping/disposition;
- do not delete task packets/specs;
- mark broad unselected work deferred;
- create V3 M0/M1/M2 work items from the new roadmap;
- no V3 dependency chain begins with T001/T002;
- current T002 does not block product work;
- migration is deterministic and tested.

Create a CLI command:

```text
tcfactory migrate-roadmap --from-v2 --dry-run
```

and then a real migration after dry-run output is reviewed by the code/tests. This does not count as human approval of V3 external release.

## 14. Phase J — Product package skeleton and native preflight vertical

The current repository has no substantive product runtime. Create product code separately.

### 14.1 Package layout

Create:

```text
packages/traincapsule-core/
packages/traincapsule-ingest-pytorch/
packages/traincapsule-qualify/
packages/traincapsule-cli/
schemas/product/
tests/product/
examples/product/
```

A local runner package may be scaffolded only to the extent needed for preflight interfaces. Do not implement broad execution yet in this migration PR unless all previous phases are stable and the work remains bounded.

Update workspace/build configuration cleanly.

### 14.2 Product models

Implement strict versioned models for:

- `WorkloadIdentity`;
- `EnvironmentIdentity`;
- `EvidenceArtifact`;
- `NativeFinding`;
- `IncidentCase`;
- `EvidenceCompletenessReport`;
- `EligibilityDecision`.

Implement technical result and operational decision enums without importing factory enums.

### 14.3 Canonical identity

Implement deterministic canonical JSON and SHA-256 identity.

Tests:

- field-order independence;
- LF/encoding;
- material drift;
- weak/customer-attested identity;
- secret redaction;
- no hidden nondeterministic timestamp in identity;
- cross-implementation golden vectors.

Create an independent reference identity verifier in a separate test/helper module or language/implementation path. Do not use the production serializer as its oracle.

### 14.4 Local evidence store

Implement content-addressed local metadata and artifact references.

Security:

- path traversal;
- symlink;
- duplicate/collision handling;
- no cross-case mix;
- size policy;
- hash before parse;
- raw evidence may remain at customer-local URI.

### 14.5 Flight Recorder importer

Implement an importer interface and initial PyTorch Flight Recorder adapter.

Because exact upstream trace formats may evolve:

- define supported fixture/version metadata;
- fail with `UNSUPPORTED_VERSION`;
- preserve unknown fields/raw digest;
- parse available collective type/state/tensor metadata/call-stack/rank/process-group;
- do not infer missing evidence;
- separate native findings from TrainCapsule findings.

Use lawful public/controlled fixtures. Do not copy private customer traces.

### 14.6 Evidence completeness

For the initial pack, represent:

```text
PRESENT_VALID
PRESENT_PARTIAL
PRESENT_CONFLICTING
PRESENT_CORRUPTED
MISSING_NOT_CAPTURED
MISSING_POLICY_RESTRICTED
MISSING_TECHNICALLY_INACCESSIBLE
MISSING_VERSION_UNSUPPORTED
IDENTITY_UNBOUND
NOT_APPLICABLE
```

### 14.7 Native baseline

Generate a machine-readable and human-readable record of:

- native tool/version;
- command/config where available;
- findings;
- limitations;
- unresolved decision.

Never call native tooling weak.

### 14.8 Eligibility/economic preflight

Return:

```text
ELIGIBLE_FOR_QUALIFICATION
ELIGIBLE_WITH_HUMAN_REVIEW
NEEDS_MORE_EVIDENCE
NATIVE_WORKFLOW_SUFFICIENT
TECHNICALLY_POSSIBLE_BUT_UNECONOMIC
OUTSIDE_SUPPORTED_ENVELOPE
POLICY_BLOCKED
UNKNOWN
```

Inputs include named decision, baseline/candidate access, evidence, pack fit, local execution authority, privacy, and cost hypothesis.

Do not calculate fake ROI. Permit unknown cost.

### 14.9 CLI

Implement:

```text
traincapsule doctor
traincapsule case init
traincapsule ingest pytorch-flight-recorder
traincapsule identity workload
traincapsule identity environment
traincapsule native-baseline
traincapsule preflight
```

Requirements:

- `--json`;
- deterministic exit codes;
- no network by default;
- useful errors;
- local paths;
- no SaaS.

### 14.10 Journey test

Create a controlled fixture and test:

```text
clean install
→ case init
→ workload/environment identity
→ evidence import
→ native baseline
→ evidence completeness
→ preflight outcome
```

Include:

- eligible controlled case;
- missing evidence;
- native sufficient;
- unsupported version;
- policy blocked;
- unknown;
- malicious archive/path.

Do not implement baseline/candidate runner, reduction, or commercial pack release in this migration PR unless the roadmap explicitly promotes them after M1.

## 15. Documentation changes

Update root `README.md` to state:

- repository now contains V3 factory migration and initial product preflight;
- product maturity is experimental;
- no commercial validation;
- how to run factory tests;
- how to run product preflight;
- source-of-truth path;
- no public/customer claims.

Create:

```text
docs/migrations/V3_MIGRATION_REPORT.md
docs/migrations/V3_ROLLBACK.md
docs/migrations/V3_TEST_MATRIX.md
docs/product/PREFLIGHT_QUICKSTART.md
```

The migration report must list every modified/new file, behavior change, legacy mapping, unresolved limitation, and deferred item.

## 16. Required test matrix

Run and record exact commands.

### Existing factory regression

- current unit suite;
- Ruff;
- Pyright;
- existing gate scripts;
- secret scan.

### V3 factory

- work-item validation;
- status transitions;
- scheduler;
- lane independence;
- WIP;
- finite retries;
- same finding;
- completion proposals;
- human approval;
- external receipts;
- candidate manifest;
- V2 migration;
- PR release dry-run;
- restart budget;
- context exclusion/freshness.

### Product

- canonical identity golden vectors;
- evidence CAS;
- Flight Recorder importer;
- native baseline;
- completeness;
- eligibility;
- CLI;
- malicious input;
- install-to-preflight journey.

### Source

- manifest generation;
- integrity positive;
- tamper negative;
- duplicate negative;
- old-bundle-active negative.

### Rollback

- migration dry-run;
- state snapshot;
- rollback rehearsal on a disposable clone/worktree.

Do not claim a GPU test ran unless it actually ran on GPU. Mark GPU work external/deferred where unavailable.

## 17. Acceptance criteria

The migration PR is ready for human review only when all are true:

- repository was clean or user changes were preserved without overwrite;
- V3 authority and manifest pass;
- historical bundle remains;
- V3 scheduler is lane-aware;
- finite limits are enforced and tested;
- completion cannot auto-append authoritative work;
- human/external evidence cannot be forged by AI-writable files;
- Claude is behind backend protocol;
- direct-main release is disabled by default;
- draft PR workflow exists;
- launcher restart is bounded;
- controls are portable/configurable;
- legacy roadmap mapping exists;
- current T002 no longer blocks V3 product critical path;
- product packages are separate;
- preflight vertical and journey pass;
- no external/commercial maturity is falsely advanced;
- documentation and rollback exist;
- no secrets were committed;
- draft PR is opened but not merged.

## 18. Commit plan

Use clear commits, approximately:

```text
docs: install v3 source authority
feat: add v3 factory models
feat: add lane scheduler and finite limits
refactor: route pipeline through v3 policy
feat: add executor backend interface
feat: release verified work by pull request
ci: split factory and product checks
fix: bound startup recovery
chore: migrate legacy roadmap
feat: add traincapsule preflight core
test: cover v3 migration and product journey
docs: add migration and rollback guide
```

Do not use vague or fake-user commit messages. Use the configured Git identity. Do not impersonate the user in prose beyond normal repository authorship.

## 19. Draft PR

When authenticated and permitted:

1. push `codex/traincapsule-v3-migration`;
2. open a draft PR to `main`;
3. title: `Migrate TrainCapsule to bounded V3 product loop`;
4. include:
   - baseline/current SHA;
   - major behavior changes;
   - tests;
   - product maturity;
   - explicit non-claims;
   - human-review checklist;
   - rollback;
   - deferred items.
5. Do not mark ready for review automatically.
6. Do not merge.

When GitHub authentication is unavailable, leave exact commands in the final report; do not fabricate a PR URL.

## 20. Final output to the operator

Return:

```text
1. actual base SHA and branch
2. draft PR URL or exact creation command
3. commits
4. files changed
5. tests and results
6. source authority status
7. legacy migration status
8. current active milestone
9. product preflight demonstration command
10. human approvals still required
11. external evidence still required
12. deferred scope
13. rollback command
14. any deviations from this prompt
```

Do not state that TrainCapsule is a successful business, commercially supported, production ready, customer validated, or superior to competitors. This migration creates the machinery and first product slice needed to seek that evidence.
