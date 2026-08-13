# TrainCapsule Repository, Product, Business, and Autonomous-Factory Audit

## 1. Audit scope

This audit covered the private repository at `TasfiqJ/TrainCapsule`, including:

- the protected source-of-truth bundle under `docs/source-of-truth/final-2026-08-09`;
- `SOURCE_PRECEDENCE.md`;
- `docs/CONTEXT_INDEX.yaml`;
- the feature ledger, task catalog, definition of done, current task packet, and task specifications;
- the controller, planner, pipeline, queue, checkpointing, value, completion, research, quality, repair, Git, GitHub, context, model-routing, and Claude execution code;
- role prompts and Claude project controls;
- execution, autonomy, role, risk, value, context, Claude-feature, and GitHub configuration;
- startup, recovery, control, and gate scripts;
- GitHub Actions;
- product package, schema, incident-pack, corpus, and example directories;
- recent commit and CI history;
- the current public competitive landscape.

The audit baseline was `main` commit:

```text
c31caefaeed7e605f6ef304fae6fcfe708a163b9
```

The latest workflow on that commit passed. That proves the factory's current tests passed. It does not prove that the TrainCapsule product exists, works, beats native alternatives, or has commercial value.

### Audit limits

- GitHub content, commits, Actions results, and repository files were readable through the connected GitHub integration.
- Repository branch-protection settings were not readable through the integration; the API returned `403 Resource not accessible by integration`. The migration must therefore inspect branch rules using an authenticated owner/admin path before assuming protection exists.
- Local runtime files intentionally excluded from Git—OAuth material, private gate implementations, transcripts, worktrees, and live queue state—were not available through the repository. This audit evaluated the code that governs those files, not their current machine contents.
- Public competitor capabilities were assessed from current public documentation and research. Private internal systems and unpublished roadmap work remain unknowable.

## 2. Executive diagnosis

The repository presently contains a sophisticated autonomous software factory and a highly detailed product design. It does not yet contain a substantive TrainCapsule product implementation.

Concrete state:

- `pyproject.toml` packages only `tcfactory`.
- No `packages/` product tree exists.
- Product schemas do not exist; `schemas/` contains factory task/report schemas.
- Each incident-pack directory contains only a short reserved-path README.
- The public incident corpus intentionally contains no incident.
- The sole GitHub workflow validates the factory rather than a product.
- The recent work history is dominated by factory hardening, recovery, specification, queuing, and repeated work on `T002`.

This is not inherently bad. A reliable factory can be an asset. The problem is that the control plane has become the project.

The current system optimizes for:

```text
take the next task
→ enlarge or repair its specification until it passes
→ merge it
→ repeat until all 124 tasks and completion audits say complete
```

A successful infrastructure business must optimize for:

```text
identify a consequential customer decision
→ establish the complete native substitute
→ build the smallest trusted workflow that changes that decision
→ obtain real evidence and payment
→ repeat without rewriting the trust core
→ expand only where paid evidence justifies expansion
```

The repository currently has good language about this distinction, but the controller does not enforce it.

## 3. Highest-priority findings

### P0-1 — The first commercial product is incorrectly separated

Current shape:

```text
assessment
→ incident closure
→ incident contract
→ later qualification
```

Commercial risk:

- the customer buys one investigation;
- the result becomes an internal or upstream test;
- TrainCapsule is not needed again.

Required replacement:

```text
one active or reconstructable incident
+ one planned stack/infrastructure change
+ one named release or migration decision
+ baseline and candidate environments
+ customer-local execution authority
→ Incident-to-Change Qualification Pilot
```

The first contract must include the second execution or an enforceable scheduled qualification event. Qualification cannot remain a vague future possibility.

### P0-2 — The roadmap and live task graph contradict the strategy

The source documents say discovery, competitor comparison, trust, and engineering should run together. The live feature ledger is essentially serial.

At the audited commit:

- `T002` had reached twelve revisions;
- `T003` depended on `T002`;
- subsequent work depended on the chain;
- a low-value naming task therefore blocked substantive product work.

Required change:

- introduce explicit lanes and lane-specific readiness;
- remove naming from the critical path;
- allow external, market, and research blockers to pause only their own lane;
- schedule by priority and milestone, not list order;
- limit work in progress.

### P0-3 — Unlimited persistence converts bad assumptions into more code

Current controls include settings where zero means unlimited:

- task re-specification;
- roadmap expansion;
- value redesign;
- renewable agent sessions;
- high infrastructure-failure ceilings.

This creates a ratchet:

```text
failure
→ more criteria
→ more prompts
→ more factory code
→ more tests
→ another attempt
```

The system lacks a credible way to conclude:

```text
this task is badly shaped
this feature is not valuable
this wedge lost
this evidence must come from a human/customer
stop spending agent capacity here
```

Required change:

- finite attempt limits;
- finite re-specification limits;
- a task-complexity budget;
- circuit breakers;
- `HUMAN_REVIEW`, `DEFERRED`, `SUPERSEDED`, and `WEDGE_REJECTED`;
- no autonomous business-roadmap expansion.

### P0-4 — AI audits can wrongly become commercial authority

Current completion logic asks multiple AI sessions to audit whether the product is complete and may append new work automatically.

Multiple sessions, prompts, worktrees, or model roles are useful process separation. They are not independent commercial, security, or distributed-systems authority.

Required rule:

> No external or commercial release may be approved solely by AI sessions. Before first external use and before every new commercial incident pack, a qualified human must approve the trust model, declared invariants, experiment semantics, security boundary, and permitted claims.

A machine-generated `COMPLETE` marker may mean only:

```text
predeclared engineering milestone gates passed
```

It may never mean:

```text
safe for external use
commercially validated
product-market fit achieved
```

### P0-5 — Competitor equivalence is a late audit instead of a continuous release gate

The repository correctly recognizes the complete substitute:

```text
framework-native tools
+ cloud/provider tooling
+ vendor support
+ internal scripts
+ approved engineering agents
```

But the strongest complete-substitute comparison is scheduled late.

Required change:

After every major capability, answer:

1. What does the current complete native/substitute workflow already do?
2. What exact incremental capability does TrainCapsule add?
3. Does it change a named operational decision?
4. Can an approved engineer plus current agents reproduce the same outcome?
5. Is the incremental outcome worth paying for?
6. What customer effort and compute remain?
7. Does TrainCapsule deserve a higher commercial maturity state?

No feature becomes `COMMERCIALLY_SUPPORTED` from internal tests alone.

### P0-6 — The product scope is too broad before access to real incidents

The architecture includes:

- generalized event/actor IR;
- native evidence adapters;
- generic experiment planning;
- generalized reduction;
- local and federated runners;
- recovery assurance;
- contracts;
- qualification;
- exchange;
- provider workflows;
- viewers;
- corpora;
- broad security and policy;
- two incident packs;
- potential ecosystem surfaces.

The trust architecture is thoughtful. The first build authorization is too broad.

Required first slice:

1. workload/environment identity lock;
2. PyTorch Flight Recorder/native evidence import;
3. evidence completeness and limitations;
4. one pack-specific planner;
5. a short, human-approved list of legal reductions;
6. customer-local isolated execution;
7. baseline-versus-candidate qualification;
8. named recovery-state checks;
9. applicability, expiry, and `UNKNOWN`;
10. independently runnable local contract.

Everything else remains designed but deferred.

### P0-7 — The task/value model applies product proof at the wrong level

Every foundational task is expected to name a user outcome, broad journey, commercial truth, and end-to-end proof. This makes low-level work invent artificial customer value.

Examples:

- a schema utility;
- a path guard;
- a naming investigation;
- a queue transition;
- a configuration check.

These should prove mechanical correctness, not pretend to prove paid value.

Required task classes:

```text
FACTORY_MECHANICAL
RESEARCH_DECISION
PRODUCT_CAPABILITY
TRUST_PROOF
MARKET_EVIDENCE
COMMERCIAL_EVIDENCE
MAINTENANCE
```

Each class needs a different evidence contract.

### P0-8 — Automatic direct-to-main promotion is too permissive for trust work

The factory creates isolated candidates and exact-SHA checks, which is good. It then squashes the candidate and fast-forwards `main`, and GitHub synchronization is explicitly restricted to pushing `main`.

For routine mechanical work this can be acceptable. For:

- trust-core code;
- product result semantics;
- commercial incident packs;
- security boundaries;
- qualification logic;
- source-of-truth changes;
- controller self-repair;

it is not acceptable.

Required change:

- routine low-risk work may retain automatic merge after deterministic gates;
- integration and trust work must produce a branch and pull request;
- external/commercial release requires a human approval artifact;
- factory-controller repairs must never self-promote directly;
- source-of-truth migrations must be human-reviewed.

### P0-9 — Claude is both the worker and too much of the operating substrate

The repository is explicitly packaged as a Claude subscription-only factory. Durable task state is mostly repository/local-file based, which is good, but the runner, model semantics, role assumptions, and quota behavior are Claude-specific.

Anthropic usage is rate-limited and shared across Claude and Claude Code. Parallel sessions consume the same allowance more quickly. Therefore, “no API bill” is not equivalent to “unbounded engineering capacity.”

Required change:

Create an internal backend contract:

```python
class EngineeringAgentBackend(Protocol):
    def start_task(self, task, context, limits) -> SessionRef: ...
    def resume_task(self, session) -> TaskResult: ...
    def cancel(self, session) -> None: ...
    def capabilities(self) -> AgentCapabilityReport: ...
    def usage_state(self) -> UsageState: ...
```

Claude remains the only configured backend initially. The ledger, packet schema, policy, evidence, hidden tests, handoffs, Git promotion, and release authority must not depend on it.

### P0-10 — Source-of-truth governance mixes immutable policy and live facts

The current dated bundle is locked, but it contains current competitive and external facts. It also includes duplicate physical files and authority-order inconsistencies noted in the prior review.

Required hierarchy:

```text
NORMATIVE PRODUCT AUTHORITY
current executive decision
→ product requirements
→ architecture
→ trust specification
→ roadmap/release policy
→ approved ADRs and released pack specifications

CURRENT FACTUAL AUTHORITY
current official primary source
→ current source register
→ claim registry
→ affected decision record
```

A source monitor may mark an assumption stale. It may not silently rewrite normative policy.

## 4. What is strong and should be retained

### 4.1 Truth discipline

Retain:

- explicit `UNKNOWN`;
- evidence-tier separation;
- observed boundary versus causal mechanism;
- applicability and expiry;
- refusal to infer unsupported hardware blame;
- no synthetic customer claims;
- no market proof from model output.

### 4.2 Candidate and provenance discipline

Retain:

- isolated worktrees;
- exact candidate SHA;
- deterministic gates;
- candidate-bound evidence;
- clean-base enforcement;
- no force-push;
- divergence detection;
- provenance logs;
- secret scans.

### 4.3 Private-gate concept

Retain the requirement that hidden/private gates execute outside the agent-visible repository and bind to a candidate SHA.

Add:

- signed gate metadata;
- runner version and digest;
- claim/milestone scope;
- expiry;
- reviewer identity when human approval is required.

### 4.4 Replaceable backend law

Retain the stable-backend principle. It is essential because native platforms and research systems will continue absorbing:

- tracing;
- alignment;
- replay;
- state checking;
- anomaly attribution;
- verification;
- diagnosis.

TrainCapsule must own the customer decision workflow, not every primitive.

### 4.5 Local-first security

Retain:

- customer-local execution;
- no default data egress;
- bounded evidence export;
- offline verification;
- explicit rights and privacy classification.

### 4.6 Recovery and interruption handling

Retain durable:

- checkpoints;
- handoffs;
- candidate commits;
- quota pause/resume;
- crash recovery.

Replace unlimited retry with bounded recovery.

## 5. Current product reality versus intended product

| Area | Intended | Current repository |
|---|---|---|
| Product package | stable core, adapters, packs, runner, CLI/API/viewer | no product package tree |
| Initial pack | pre-collective lifecycle contract | reserved README only |
| Second pack | checkpoint/resume consistency | reserved README only |
| Product schemas | incident, identity, evidence, experiment, contract, qualification | not implemented |
| Native ingest | Flight Recorder importer | not implemented |
| Local runner | customer-local execution | not implemented |
| Qualification | baseline versus candidate | not implemented |
| Public corpus | attributable incidents | intentionally empty |
| CI | factory and product validation | factory-only workflow |
| Commercial evidence | design partners/pilots/repeats | no validated evidence in repository |
| Factory | supporting control plane | substantial implementation |

This means the correct next move is not another round of factory perfection. It is a controlled migration that releases the first product lane.

## 6. File-by-file change matrix

### 6.1 Authority and product documents

#### `SOURCE_PRECEDENCE.md`

Change:

- point normative authority to a new `final-2026-08-11-v3` bundle;
- keep the old bundle as immutable historical material;
- remove duplicate physical files from active authority;
- separate normative product authority from current factual authority;
- define ADR and stale-assumption handling;
- state that acquisition and career documents are non-authoritative advisory material.

#### `docs/CONTEXT_INDEX.yaml`

Change:

- remove the giant master plan, acquisition thesis, and career thesis from normal build context;
- add narrow context packs:
  - `commercial_wedge`;
  - `native_baseline`;
  - `trust_core`;
  - `pre_collective_pack`;
  - `market_evidence`;
  - `factory_controller`;
- enforce source count and character budgets;
- add exact authority section references;
- never inject all high-authority documents into every task.

#### `00_EXECUTIVE_BUILD_DECISION.md`

Replace controlling doctrine:

```text
build complete local product before market proof
```

with:

```text
build the complete first commercial qualification slice
run market/native/trust lanes in parallel
expand only through milestone and external evidence gates
```

Add:

- first paid offer;
- human authority rule;
- product maturity states;
- explicit deferrals;
- kill conditions;
- prohibition on AI-only commercial completion.

#### `03_PRODUCT_STRATEGY_AND_REQUIREMENTS.md`

Add:

- joined Close + Qualify first offer;
- exact ideal-customer profile;
- buyer and decision owner;
- pilot entry criteria;
- second execution included;
- complete-substitute benchmark;
- commercial maturity model;
- no-value terminal states;
- open/free eligibility boundary;
- productized service posture;
- checkpoint pack classification as engineering reference only.

#### `04_TECHNICAL_ARCHITECTURE.md`

Refactor into:

1. stable long-term architecture;
2. V1 commercial slice;
3. deferred surfaces.

Resolve:

- duplicate repository layouts;
- Slurm-first versus partner-selected scheduler;
- generalized IR versus pack-specific V1;
- generic reduction versus allowlisted transformations;
- local runner first versus federation;
- thin report/CLI first versus broad viewer.

#### `05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC.md`

Add:

- qualified human release authority;
- independent oracle requirement;
- claim registry;
- commercial maturity;
- native-equivalence and no-value outcomes;
- signed approval schema;
- no AI-only external release;
- pack-specific legal-reduction registry;
- exact criteria for requalification and expiry.

#### `08_ACQUISITION_THESIS.md`

Keep as advisory only.

Remove it from:

- normal task context;
- planner defaults;
- completion audits;
- product definition of done;
- release gates.

Acquisition is not a task-acceptance criterion.

#### `09_CAREER_AND_HIRING_THESIS.md`

Keep as advisory only.

Remove it from:

- product planning context;
- completion;
- task value contracts;
- release authority.

Founder comprehension artifacts can remain a side lane; they must not block customer value.

#### `12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md`

Replace:

- fixed day ranges;
- serial P0–P10 dependency chain;
- late account mapping;
- late competitor benchmark;
- precommitted second commercial pack;
- complete-system completion target.

Use:

- four lanes;
- milestones;
- evidence gates;
- finite WIP;
- first qualification slice;
- paid-pilot and repeat gates.

#### `13_SOURCE_REGISTER.md`

Move to current-facts authority.

Add:

- PyTorch Flight Recorder;
- NVIDIA Mission Control/ARE;
- AWS HyperPod checkpointless recovery;
- CoreWeave Mission Control;
- Chamber;
- Harbor;
- Caladrius;
- Teyon;
- TrainCheck;
- TrainVerify;
- TTrace;
- ARGUS;
- relevant primary papers and official documentation.

Add:

- source owner;
- retrieval date;
- freshness interval;
- affected assumptions;
- claim status;
- stale-trigger action.

#### `14_CLAUDE_CODE_MASTER_BUILD_PROMPT.md`

Replace:

- complete-product mandate;
- unlimited work-until-done interpretation;
- Claude-only operating substrate;
- precommitted two-pack commercialization;
- AI completion authority.

Add:

- task classes;
- finite limits;
- lane scheduler;
- milestone outcomes;
- human gates;
- complete-substitute benchmark;
- tool-neutral backend;
- no fabricated external evidence.

#### `FINAL_MANIFEST.json`

For the new bundle:

- no duplicate logical documents;
- no file self-hash paradox;
- explicit normative versus factual classes;
- canonical hashing procedure;
- baseline commit;
- superseded bundle pointer;
- generated timestamp;
- schema version.

### 6.2 Factory ledgers and task packets

#### `factory/feature_ledger.yaml`

Add fields:

```yaml
lane:
task_type:
priority:
milestone:
maturity_target:
commercial_hypothesis:
native_baseline_required:
human_approval_required:
kill_condition:
external_dependency:
blocked_scope:
parent_experiment:
max_attempts:
max_respecifications:
```

Change readiness from list order to scheduler selection.

Add states:

```text
human_review
external_wait
deferred
superseded
rejected_value_or_stopped
cancelled
```

Do not require all tasks to pass for the product to operate.

#### `factory/task_catalog.yaml`

Rewrite catalog templates by task type.

Mechanical tasks:

- no commercial value fiction;
- one bounded outcome;
- small criteria/output count.

Research tasks:

- decision question;
- source level;
- claim impact;
- no code unless explicitly required.

Product tasks:

- user-visible capability;
- native baseline;
- product contract;
- integration test.

Trust tasks:

- invariant;
- oracle;
- negative cases;
- human approval if externally releasable.

Market/commercial tasks:

- AI prepares artifacts;
- humans supply conversations, decisions, payment, and signatures;
- no model may manufacture completion.

Correct allowed-path mismatches and remove catalog criteria that compound on every re-specification.

#### `factory/product_definition_of_done.yaml`

Split into milestone definitions:

```text
M0_FACTORY_MIGRATED
M1_NATIVE_BASELINE_AND_ELIGIBILITY
M2_CONTROLLED_QUALIFICATION_SLICE
M3_EXTERNAL_PREFLIGHT_READY
M4_PAID_PILOT_COMPLETED
M5_PAID_REPEAT_COMPLETED
M6_COMMERCIALLY_SUPPORTED_PACK
```

Only M0–M2 can be entirely machine-completed.

M3 requires human approval. M4–M6 require external evidence.

#### `tasks/T002.yaml`

Do not attempt a thirteenth expansion.

Replace status with:

```yaml
status: deferred
blocked_scope: naming_only
reason: provisional codename is sufficient for private development
reopen_gate: public launch, package publication, paid contract, or legal counsel request
```

Create a small non-blocking legal-clearance checklist. It must not block product implementation.

#### Other active/generated packets

- invalidate packets generated from the old catalog after the migration cutoff;
- retain their artifacts for audit;
- regenerate only tasks selected into the V3 roadmap;
- add a schema version;
- cap criteria and output counts;
- split packets that exceed the budget.

### 6.3 Models and schemas

#### `tcfactory/models.py`

Add enums:

```text
TaskType
Lane
MaturityState
CommercialResultState
HumanApprovalStatus
ScopeDisposition
```

Replace `FactoryConfig.execution_mode` as a Claude-only literal.

Add:

- backend name;
- lane limits;
- task class limits;
- wall-clock/session limits;
- PR policy;
- human approval paths;
- milestone identifiers;
- external evidence references.

Extend task packet with the ledger fields above.

Add packet complexity validation:

- one primary goal;
- criteria count by risk;
- output count;
- context-file count;
- gate count;
- maximum prompt size;
- no broad universal user journey on mechanical tasks.

#### `schemas/task.schema.json`

Regenerate from the new model. Preserve strict `extra=forbid`.

#### New schemas

Create:

- `human-approval.schema.json`;
- `external-evidence-receipt.schema.json`;
- `native-substitute-benchmark.schema.json`;
- `product-maturity.schema.json`;
- `qualification-decision.schema.json`;
- product-domain schemas under `schemas/product/`.

### 6.4 Scheduler and lifecycle

#### `tcfactory/feature_ledger.py`

Replace `next_ready()` list traversal with:

```text
dependency filter
→ lane capacity
→ external-blocker scope
→ milestone eligibility
→ priority
→ aging/fairness
→ cost/quota fit
```

Add lane and milestone summaries.

#### `tcfactory/queue.py`

Add:

- priority queue;
- lane labels;
- cancellation;
- supersession;
- scoped blocking;
- claim lease and recovery;
- per-lane WIP;
- fair scheduling.

Do not globally stop because the oldest task is blocked.

#### `tcfactory/autopilot.py`

Remove the invariant that `max_parallel` must equal one.

Implement:

- lane-aware dispatch;
- bounded concurrency;
- circuit breakers;
- task attempt budgets;
- scoped external waits;
- human-review queue;
- milestone audit;
- no automatic business-roadmap expansion;
- no product completion marker beyond engineering milestones;
- persistent stop/kill decisions that agents cannot reverse.

Recommended initial concurrency:

```text
mutating sessions: 1
read-only research/review sessions: 1
external market actions: tracked but not autonomously executed
trust work: scheduled when a candidate or release gate exists
```

The implementation may support more parallelism later, but the initial policy should minimize shared-subscription pressure, merge conflicts, and duplicated context. Lane independence does not require every lane to run a mutating agent simultaneously.

#### `tcfactory/checkpoints.py`

Retain the atomic temporary-file replacement and archive behavior.

Change the failure semantics. `list_active()` currently suppresses every parse or schema error and continues, which can make a corrupt active checkpoint disappear from recovery. Instead:

- add checkpoint schema version and content digest;
- keep the previous valid generation until the next save is verified;
- quarantine malformed checkpoints under `factory/state/checkpoints/quarantine/`;
- emit a blocking recovery event with the exact path and reason;
- never treat an unreadable active checkpoint as “no work exists”;
- bind the checkpoint to backend-neutral session reference, lane, milestone, task budget, candidate SHA, and source/context digests;
- record human-review and circuit-breaker transitions;
- test power-loss, partial write, incompatible-version, stale-candidate, and duplicate-active cases.

### 6.5 Backend, configuration, catalog, and operator surface

#### `tcfactory/auth.py`

Retain the strongest existing controls:

- reject API-key and alternate-provider routes;
- require a protected OAuth token file for lights-out operation;
- remove controller-only and unrelated secrets from agent environments;
- never log token contents.

Move this implementation behind the Claude backend instead of making subscription authentication part of the generic factory model. Add:

- `ClaudeCredentialProvider` owned by `tcfactory/backends/claude.py`;
- a backend-neutral authentication/capability report that contains no account secrets;
- explicit token-file permission tests on Linux and clear unsupported-platform behavior;
- log redaction tests covering exception strings and child-process stderr;
- an operator-visible distinction between `AUTHENTICATED`, `AUTH_EXPIRED`, `QUOTA_WAIT`, and `ROUTE_REFUSED`;
- no assumption that a credentials-file pathname by itself proves an active entitlement;
- no account email, organization identifier, or token-file path in public/PR artifacts.

Do not weaken Max subscription-only operation. Decouple it from factory-wide schemas so another executor can be added without rewriting durable work state.

#### `tcfactory/config.py`

Replace one-shot Pydantic loading with an explicit configuration migration layer:

- load V2 only in migration mode;
- produce a deterministic V2-to-V3 report;
- reject mixed-version files;
- record config source and permitted environment overrides;
- do not allow environment overrides for release authority, human approval, evidence trust, or security policy;
- validate all related files as one configuration set;
- provide `tcfactory config validate`, `config migrate --dry-run`, and `config explain <field>`;
- use atomic writes and keep a rollback copy during migration.

`TCF_MAX_PARALLEL` must not collapse lane-specific limits into one ambiguous integer. Replace it with explicit mutating/read-only limits or reject it after migration.

#### `tcfactory/catalog.py`

Replace the legacy 124-task catalog compiler with a V3 work-item compiler. Specific changes:

- remove the hard-coded `T002` research path;
- use typed `TaskType` instead of free-form `task_kind` strings;
- compile from the V3 work ledger and task-type template;
- do not append universal commercial/value prose to every task;
- do not make integration/trust tasks `auto_merge=True`;
- do not select private-gate suites merely from risk tier when a capability-specific suite is required;
- validate allowed paths against expected outputs before a packet is emitted;
- cap criteria, outputs, gates, source files, and prompt bytes;
- make naming/legal research non-blocking and reopenable by an explicit trigger;
- include decision contribution, milestone, lane, maturity target, oracle, rollback, and stop disposition;
- invalidate generated packets when source, work item, template, or compiler digest changes.

Keep deterministic compilation. Eliminate special cases and scope accumulation.

#### `tcfactory/claude_features.py`

Keep Claude-native features as optional adapter capabilities, not factory invariants.

Correct the current details:

- change stale `rp-` session prefixes to `tc-`;
- remove “continue through renewable sessions until complete” from the default goal;
- capability-check cross-session messaging, advisor, goal, workflow, and team features independently;
- do not require messaging for factory calibration or product correctness;
- keep peer messages non-authoritative and require a durable handoff before any result is used;
- cap peer-message count, total peer turns, and combined context use;
- do not start a scout merely because risk is `trust_core`; require a named question and expected decision value;
- disable dynamic workflow/tool injection unless the installed SDK explicitly supports it and a deterministic fallback exists;
- store only feature names and capability versions in durable state, not Claude-specific transcript semantics.

#### `tcfactory/cli.py`

Split operator commands into clear groups: factory, work, milestones, evidence, approvals, product, and migration.

Add:

```text
tcfactory migrate --dry-run
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

Change current behavior:

- `doctor` must inspect both factory controls and the product runtime, not only Claude/factory bootstrap;
- `autonomy-enable` must not edit and commit configuration directly on `main`;
- enabling execution requires an explicit local operator action and leaves a reviewable config diff or PR;
- calibration must be risk-specific and must not require every role, peer messaging, or one fixed Claude feature set;
- queue/status output must show lane, milestone, maturity, blocker scope, attempts remaining, and approval requirement;
- destructive resume/override commands require a reason and create an immutable decision record;
- human-review, kill, and rejected-value states cannot be bypassed by a generic `resume`;
- all JSON output intended for a PR or support bundle must be secret- and path-sanitized.

### 6.6 Planning and prompts

#### `tcfactory/planner.py`

Replace one universal outcome contract with deterministic templates by task type.

Rules:

- a re-specification may not add scope unrelated to the observed failure;
- after two re-specifications, transition to human review;
- split oversized tasks;
- catalog minimums may not accumulate repeatedly;
- source context must be minimal;
- no acquisition/career material;
- no fabricated user journey.

#### `prompts/global.md`

Replace “use the full allowance and work until the outcome exists” with:

- solve the bounded packet;
- stop at limits;
- report uncertainty;
- do not broaden scope;
- do not reinterpret external evidence;
- recommend deferral or wedge rejection when appropriate.

#### `prompts/autonomous_planner.md`

Add task-type templates and complexity budgets.

#### `prompts/research.md`

Add evidence levels:

```text
L0 navigation
L1 reproducible source record
L2 primary-source decision research
L3 claim/release-critical research
```

Naming is L1 and non-blocking. Competitor and trust claims are L2/L3.

#### `prompts/builder.md`

Require only packet-relevant installation, security, performance, and user-flow checks. Full product review occurs at milestones.

#### `prompts/adversary.md`

Require:

- exact packet;
- native substitute when applicable;
- counterexample;
- scope control;
- no generalized audit boilerplate.

#### `prompts/factory_repair.md`

Permit only:

- smallest causal controller repair;
- strict file and line-diff cap;
- one attempt;
- mandatory regression test;
- branch/PR;
- no source-of-truth, roadmap, value, or commercial-policy changes.

### 6.7 Pipeline, review, and release

#### `tcfactory/stage_policy.py`

Current normalization collapses each task into one writable owner plus one blind adversary. Replace the claims and policy with honest risk-adaptive stages:

```text
mechanical:
  owner + deterministic gates

standard:
  owner + blind adversary

integration:
  owner + integration verifier + adversary as needed

trust_core:
  owner + independently derived oracle + adversary
  + security review where relevant
  + human external-release approval
```

AI sessions may be isolated; they are not called independent human authority.

#### `tcfactory/pipeline.py`

Preserve candidate isolation and evidence binding.

Add:

- task wall-clock and session budgets;
- exact attempt ceilings;
- no repair loop for external rejection;
- no mutation after human-review transition;
- milestone-level value gates;
- native-substitute benchmark;
- branch/PR release for high risk;
- human approval validation;
- signed external evidence validation;
- `WEDGE_REJECTED` outcome;
- result semantics separated from task pass/fail.

Remove:

- renewable retries interpreted as effectively unlimited;
- automatic trust/commercial promotion;
- completion based on internal success alone.

#### `tcfactory/value.py`

Move value gates from every task to:

- product capability;
- milestone;
- external/commercial event.

Add fields:

```text
incremental_decision_value
complete_substitute_result
customer_retained_effort
experiment_cost_ratio
time_to_decision
decision_changed
second_execution_committed
paid_repeat
customer_attestation
```

A technical `PASS` can coexist with:

```text
NO_INCREMENTAL_DECISION_VALUE
NATIVE_WORKFLOW_SUFFICIENT
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
```

#### `tcfactory/completion.py`

Replace product-completion audit with milestone audit.

Auditors may:

- verify declared artifacts;
- identify missing proof;
- propose a scope request.

They may not:

- declare commercial completion;
- generate customer evidence;
- append arbitrary roadmap tasks;
- alter the wedge;
- approve a commercial pack.

A human product decision accepts or rejects scope requests.

#### `tcfactory/quality_policy.py`

Retain high-confidence checks:

- status laundering;
- skipped/removed tests;
- secret leakage;
- path violations;
- candidate mismatch.

Demote brittle textual heuristics to advisory warnings where false positives can block the factory. Require deterministic regression tests for every blocker.

### 6.8 Research, context, and agent execution

#### `tcfactory/research_policy.py`

Keep L3 rigor for claim-critical work.

Add risk levels and simplify low-risk research.

Do not require a full preregistered query DAG, raw capture set, candidate hash, and high-cost adversarial process for a provisional codename.

#### `tcfactory/context.py`

Retain hash-bound context manifests.

Add:

- maximum primary sources;
- maximum repository files;
- role-specific context;
- section/range pointers;
- explicit excluded material;
- context freshness metadata.

#### `tcfactory/claude_runner.py`

Implement `EngineeringAgentBackend`.

Enforce:

- task/session budgets even under subscription authentication;
- explicit tool allowlists;
- no `WebSearch`, `WebFetch`, `Agent`, or unsandboxed Bash by default;
- backend-neutral result schema;
- cancellation;
- usage reporting;
- capability checks.

Claude remains first backend.

#### `tcfactory/model_routing.py`

Route by:

- task type;
- risk;
- known complexity;
- context size;
- quota state.

Do not use Opus merely because a task has failed repeatedly. Repeated failure is often a specification or wedge signal.

#### `tcfactory/risk.py`

This file currently defeats several apparent safety controls and requires a direct rewrite.

Problems:

- mutating stages are rewritten to `allowed_paths: ["**"]`;
- `work_until_done=True` removes turn, token, and budget ceilings;
- planning and execution are deliberately renewed until pass/block;
- private-gate selection partly depends on numeric `T###` ranges;
- risk inference relies on keyword matching;
- every non-mechanical task receives a broad adversary, regardless of actual decision risk;
- GitHub push is forced true.

Replace it with typed task-class and capability risk. Required rules:

- risk can still move upward, never downward without an approved record;
- allowed paths remain packet-specific and are never widened to `**` by routing;
- no risk profile removes finite limits;
- gate suites are selected by changed capability and threat model, not task number;
- review depth is risk adaptive;
- repeated failure changes disposition, not model size automatically;
- routing never decides release mode or forces GitHub publication;
- deterministic tests cover every risk transition and path-preservation rule.

#### `tcfactory/prompts.py`

Current task composition instructs agents to read all relevant company, buyer, acquisition, architecture, and release context and to continue through renewable sessions until every criterion is satisfied. That directly conflicts with bounded context and finite work.

Change it so:

- the context manifest is an authority-constrained ceiling for the stage unless a deterministic missing-context request is approved;
- routine tasks cannot pull acquisition/career/GTM material;
- the packet is summarized or referenced rather than redundantly embedded when large;
- prompt byte count is checked before launch;
- renewable-session language is removed;
- the agent is explicitly authorized to return `DEFER`, `NATIVE_SUFFICIENT`, `REJECTED_VALUE`, or `WAITING_HUMAN` where appropriate;
- the prompt identifies information classes that must never enter transcripts.

#### `tcfactory/structured_runner.py`

Retain schema-enforced structured output, sandboxing, network denial, and machine-readable rate-limit handling.

Remove the subscription-unbounded path that nulls budgets and raises turn floors. Add:

- backend adapter instead of direct SDK/auth imports;
- finite wall-clock, turn, context, and retry ceilings;
- cancellation;
- transcript retention/redaction policy;
- no raw SDK-message serialization when it may contain private source or prompt content;
- artifact encryption or customer-local restricted storage for sensitive runs;
- backend-neutral usage and session references;
- explicit Bash subcommand allowlist even inside the sandbox;
- tests proving read-only execution cannot write through shell side channels.

#### `tcfactory/handoffs.py`

Upgrade handoffs from a convenience summary into a versioned durable contract.

Add:

- schema version and digest;
- work item, lane, milestone, task type, decision contribution, source/context/candidate digests;
- backend-neutral session reference;
- unresolved findings with owner and fingerprint;
- attempts remaining and circuit-breaker state;
- approval/external evidence requirements;
- exact next authorized transition;
- sanitization of commands, paths, account data, and private evidence.

Do not persist Claude session IDs or model-specific state as required durable semantics.

#### `tcfactory/peer_messaging.py`

Rename the stale `RPMSG/1` protocol to a neutral versioned protocol or preserve it only as a legacy parser. Peer messages must include run identity and artifact digest, validate that artifact paths remain inside the permitted local artifact root, and never count as evidence until the referenced durable artifact is verified. Malformed session records must be surfaced, not silently skipped. Add retention and redaction limits.

#### `tcfactory/quota.py`

Keep machine-readable SDK limit events as the preferred source. Regex classification must remain a fallback only.

Change:

- do not store arbitrary stderr excerpts without redaction;
- separate `AUTH_EXPIRED`, `ROUTE_REFUSED`, `SERVICE_CAPACITY`, `PLAN_LIMIT`, and `TRANSIENT_RATE_LIMIT`;
- paid-overage detection should create a hard route refusal, not be represented as ordinary authentication;
- cap probes/retries with the same circuit breaker as other infrastructure failures;
- bind pause records to backend and work item;
- test false-positive limit strings appearing in compiler/test output.

#### `tcfactory/ledger.py` and `tcfactory/usage.py`

The current JSON ledger is a useful bootstrap but is not a reliable scheduler or audit store.

Add:

- atomic append or SQLite/event-store implementation;
- concurrency safety;
- schema version and migration;
- work item/lane/milestone/backend dimensions;
- turn, context, wall-clock, attempt, and quota-window accounting;
- separation of estimated API-equivalent cost from actual subscription capacity;
- retention/compaction policy;
- no environment override that silently changes a reviewed capacity policy.

Do not optimize only for Sonnet/Opus share. Optimize for decision throughput, retry waste, and milestone progress.

#### `tcfactory/observability.py` and `tcfactory/provenance.py`

Retain compact local events and honest automation provenance. Add:

- event schema and sequence identifier;
- file locking or an append-safe event store;
- redaction before `detail` or `data` is written;
- lane, milestone, work item, disposition, and attempts remaining;
- integrity chaining or periodic digest snapshots for approval/release events;
- explicit local-only versus exportable event classes;
- corruption warnings instead of silently skipping malformed event lines.

#### `tcfactory/util.py` and `tcfactory/yamlutil.py`

Keep duplicate-key rejection in YAML.

Replace generic non-atomic `write_json()` for authority/runtime state with a durable writer that:

- writes a sibling temporary file;
- flushes and `fsync`s file contents;
- atomically replaces the destination;
- optionally `fsync`s the parent directory;
- preserves a previous valid generation for critical records;
- supports a lock or single-writer contract;
- validates the payload before replacement.

Add normalized path helpers that reject escapes and symlink surprises. Do not rely on glob matching alone for security boundaries. `run_command()` callers must pass an explicit sanitized environment when a subprocess can observe secrets; add safe wrappers for controller, agent, and export contexts.

### 6.9 Self-repair

#### `tcfactory/self_repair.py`

Current scope is too broad for autonomous self-modification.

New rule:

- one repair attempt;
- maximum diff size;
- controller-only paths;
- no prompts governing business policy;
- no source documents;
- no ledgers;
- no value or completion policy;
- separate branch and PR;
- exact regression reproduction;
- human review before merge when the repair affects scheduling, release, security, or authority.

After one failed repair:

```text
FACTORY_HUMAN_REVIEW
```

Do not auto-wake and try indefinitely.

### 6.10 Git and GitHub

#### `tcfactory/gitops.py`

Keep worktrees, exact tree preservation, divergence checks, and no force-push.

Add:

- PR-mode integration;
- signed release metadata;
- source-of-truth migration protection;
- human approval validation;
- protected task classes that cannot fast-forward main automatically.

#### `tcfactory/github_sync.py`

Current implementation explicitly pushes only `main`.

Add modes:

```text
auto_main_low_risk
pull_request_required
manual_release
```

For PR mode:

- push branch;
- create/update draft PR;
- attach candidate SHA and evidence;
- wait for required checks;
- never merge if human approval required.

#### `config/github.yaml`

Add task/risk mapping to integration modes and required workflows.

### 6.11 Configuration

#### `config/factory.yaml`

Change:

- `work_until_done: false`;
- bounded task limits;
- total parallelism 3;
- explicit lane limits;
- backend selection;
- PR policy;
- milestone completion;
- no task/dollar budget disabling;
- realistic completion audit budget.

Even with subscription authentication, use tokens/turns/wall time as capacity controls.

#### `config/autonomy.yaml`

Recommended:

```yaml
max_respecifications_per_task: 2
max_self_repair_attempts: 1
max_consecutive_factory_failures: 5
max_completion_expansions: 1
max_expansion_items: 5
roadmap_expansion_requires_human_approval: true
value_redesign_limit: 1
auto_expand_roadmap: false
```

Add circuit-breaker thresholds and human-review behavior.

#### `config/roles.yaml`

Reduce default model/turn/tool access.

Use Opus for:

- truth-critical specification;
- high-risk adversarial analysis;
- security;
- complex primary-source research.

Use Sonnet for routine implementation and review.

No role receives broad web, agent, and unsandboxed command access by default.

#### `config/risk_profiles.yaml`

Add task-class-specific limits. Remove “no artificial ceiling” as a principle.

#### `config/value_policy.yaml`

Replace one universal policy with task-class policies.

#### `config/context.yaml`

Add narrow context packs; remove broad authority injection.

#### `config/claude_features.yaml`

Keep cross-session messaging optional. The controller must never depend on ephemeral peer messages for durable truth.

Disable agent teams for small/mechanical work.

### 6.12 Startup and operations scripts

#### `scripts/windows_task_entrypoint.sh`

Current behavior restarts the controller indefinitely every fifteen seconds.

Add:

- exponential backoff;
- restart-rate ceiling;
- exit-reason classification;
- circuit-breaker file;
- health check before restart;
- no restart on human-review/kill decisions;
- config-driven paths.

#### `Control-TrainCapsuleBuilder.ps1`

Remove hardcoded:

- WSL distribution;
- repository path;
- scheduled task name;
- T###-only task ID validation.

Read from a local config file or environment.

Add actions:

```text
Lanes
Milestones
Commercial
Competitors
Pilot
Approvals
KillGates
Doctor
Migration
```

#### `scripts/factory_control.sh`

Add equivalent commands and a safe migration/pause workflow.

#### Pause/resume/recover/stop scripts

Differentiate:

- quota pause;
- external wait;
- human review;
- circuit breaker;
- operator pause;
- hard stop.

A generic resume must not override a wedge kill or human-review requirement.

### 6.13 Gates and CI

#### Existing gates

Keep:

- safe command allowlisting;
- path policy;
- no secrets;
- protected paths;
- candidate binding;
- private runner outside repository.

Revise:

- contract and milestone gates around V3 milestones;
- no-product-code gate after migration;
- no-paid-usage gate to permit configured backends later while preserving explicit billing policy;
- output integration gate to understand task types.

#### `.github/workflows/factory-smoke.yml`

Split into:

1. `factory-control-plane.yml`
2. `product-unit.yml`
3. `product-integration-fixtures.yml`
4. `packaging-install.yml`
5. `security-sbom.yml`
6. `docs-schemas.yml`
7. `source-freshness.yml`
8. `gpu-validation.yml` — protected/manual or scheduled where hardware exists

Do not make every public pull request execute sensitive self-hosted GPU workloads.

The product workflows must validate the product packages, not only `tcfactory`.

## 7. Required product and business state models

### 7.1 Engineering/commercial maturity

```text
DESIGN_ONLY
IMPLEMENTED_EXPERIMENTAL
CONTROLLED_VALIDATED
NATIVE_ADVANTAGE_UNPROVEN
NATIVE_ADVANTAGE_DEMONSTRATED
EXTERNAL_VALUE_DEMONSTRATED
COMMERCIALLY_SUPPORTED
DEPRECATED
```

### 7.2 Technical result

```text
PASS
FAIL
UNKNOWN
INAPPLICABLE
EXPIRED
```

### 7.3 Customer-value result

```text
DECISION_VALUE_DEMONSTRATED
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
EXTERNAL_EVIDENCE_REQUIRED
```

### 7.4 Task lifecycle

```text
backlog
ready
running
review
human_review
external_wait
passed
failed
deferred
superseded
rejected_value_or_stopped
cancelled
```

Do not collapse these dimensions into one `PASS`.

## 8. Required migration sequence

1. Pause autopilot.
2. Snapshot:
   - main SHA;
   - ledger;
   - queue;
   - active pipeline;
   - worktrees;
   - factory state;
   - current task packet.
3. Create migration branch.
4. Add V3 bundle.
5. Update source precedence and context.
6. Add schemas/models for lanes, task types, maturity, human approvals.
7. Migrate ledger and current task.
8. Implement lane scheduler and finite limits.
9. Implement task-type planner/value/research policies.
10. Implement PR and human-release modes.
11. Split completion into milestone audits.
12. Split CI.
13. Add product package skeleton.
14. Validate migration with deterministic tests.
15. Open draft PR.
16. Human review.
17. Merge.
18. Reinitialize queue from V3 ledger.
19. Resume the new loop.

## 9. Final repository judgment

### Engineering judgment

The factory demonstrates substantial systems thinking and defensive engineering. It is overfit to its own failures and has accumulated complexity faster than product code.

### Product judgment

The product architecture has a credible, narrow opportunity, but only in failure-derived change qualification. General GPU reliability, observability, diagnosis, restart, and replay are already heavily occupied.

### Business judgment

The plan does not become a business by completing the repository. It becomes a business when:

- a qualified customer supplies a real incident;
- a real upcoming change exists;
- TrainCapsule changes the release/recovery decision beyond the complete substitute;
- the reduced experiment is economically useful;
- the customer pays;
- the customer pays again;
- the same-family third case does not require a trust-core rewrite.

### Authorization

Authorize the V3 migration and the first commercial slice.

Do not authorize the current loop to continue unchanged.
