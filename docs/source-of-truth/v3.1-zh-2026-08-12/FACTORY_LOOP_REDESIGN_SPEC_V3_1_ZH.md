# TrainCapsule Autonomous Factory and Business Loop Redesign Specification V3.1-ZH
| Field | Value |
|---|---|
| Logical ID | `TC.V3_1_ZH.FACTORY_LOOP` |
| Generation | `traincapsule-v3.1-zh-2026-08-12` |
| Authority class | `normative_factory` |
| Derived from | `TC.V3.FACTORY_LOOP` |

## V3.1-ZH controlling amendment

This document is a complete, self-contained V3.1-ZH derivation of the identified immutable V3
source. Every V3 section is preserved below in source order unless its heading/body is explicitly
superseded by the deterministic generation rules recorded in
`SECTION_COVERAGE_V3_TO_V3_1_ZH.json`. No runtime consumer may inherit normative clauses from the
historical V3 directory.

The controlling doctrine is `ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP`. After one-time bootstrap,
no founder, operator, reviewer, or other person is a runtime approval or release dependency. There is
no human-approval runtime state. Missing machine authority is a scoped `BLOCKED_POLICY`; missing
outside facts are `WAITING_EXTERNAL`/`UNKNOWN` and block only dependent scope.

`B004` is critical and explicitly nonblocking: zero founder intervention is not a claim of literal
zero people. External people and organizations may asynchronously supply attributable conversations,
incident access, payment, adoption, independent-operation, acceptance, or other customer facts only
through authenticated external receipts. The loop may not fabricate those facts and must continue
all unrelated lanes while they are absent.

No AI session, candidate code, repository workflow, or mutable repository file may self-certify
trust, release, or activation. A separately administered off-repository machine verifier uses
protected policy, private oracles, signing keys, revocation state, and credentials to issue scoped,
expiring, revocable, non-replayable exact-SHA receipts. An unavailable or invalid authority fails
closed.

Release is frozen candidate → required local/private gates → valid independent machine-policy
receipt → race-checked non-force exact-SHA push to `main` → post-push hosted checks and exact-main
verification. Pull requests, candidate-branch publication, force push, deletion, bypass, and reuse
of another SHA's pass are forbidden. Controller activation requires a separate signed external
receipt binding the exact published SHA, environment, generation, controller, configuration,
policy, canaries, and expiry.

All original V3 laws for exact identity, evidence provenance, native-first and complete-substitute
comparison, explicit `UNKNOWN`, controlled-evidence ceilings, finite retry/recovery, bounded roadmap,
and truthful commercial claims remain mandatory. Controlled or synthetic fixtures cannot prove GPU,
customer, payment, adoption, independent-operation, external-value, or commercial-support facts.

This generation is a disclosed amendment, not a claim of exact original-V3 conformance. Replacing
qualified-person review with encoded independent machine policy loses contextual judgment that might
detect novel ambiguity outside declared policy/private oracles. Separation of authority, hidden
checks, scoped receipts, expiry, revocation, exact-SHA binding, complete evidence, fail-closed release,
and rollback reduce but do not eliminate that residual risk.


## 1. Objective

The present factory is optimized to keep producing and validating repository work until a large predefined product is complete. The replacement must optimize for a different objective:

> Advance the shortest evidence-backed path to one repeatable paid incident-to-change qualification decision, while preserving trust, security, and recoverability and stopping work that does not change customer outcomes.

The factory remains an engineering accelerator. It is not the company, the product authority, the customer, the machine-policy evaluationer, or the source of commercial truth.

## 2. Current-system diagnosis

The existing implementation has valuable controls:

- isolated Git worktrees;
- exact candidate SHA review;
- path allowlists;
- deterministic gates;
- private hidden gates;
- explicit uncertainty;
- crash checkpoints;
- quota pause/resume;
- secret scanning;
- clean-main integration;
- candidate preservation across controller repair;
- externally signed value-receipt support.

The harmful behavior comes from the combination of:

- one list-ordered dependency chain;
- `max_parallel: 1`;
- universal planning/specification expansion;
- zero/unlimited retry semantics;
- work-until-done doctrine;
- task-level “commercial value” contracts on nearly every node;
- completion auditors that can append more work;
- broad source context injected into routine tasks;
- one global product-completion target;
- direct promotion to `main`;
- no first-class independent machine-policy receipt state;
- no commercial-maturity state;
- no scheduler concept of market evidence, native-equivalence, or stop decisions.

The result is a factory that can spend large amounts of model capacity making the factory more rigorous while no customer-facing product exists.

## 3. New separation of systems

Create four explicit systems.

```text
A. PRODUCT ROADMAP
   What software or controlled evidence is being built.

B. MARKET EVIDENCE SYSTEM
   What external facts exist: conversations, incidents, pilots, payment, repeat use.

C. TRUST AND RELEASE SYSTEM
   What may be externally used or claimed, and who approved it.

D. ENGINEERING EXECUTOR
   Claude or another backend that plans, edits, tests, and reviews bounded repository work.
```

These systems interact through typed records. They must not share status fields or silently substitute for one another.

## 4. New source layout

```text
factory/
├── roadmap/
│   ├── milestones.yaml
│   ├── work_items.yaml
│   ├── dispositions.yaml
│   └── migrations/
├── market/
│   ├── account-map.template.yaml
│   ├── discovery-ledger.template.yaml
│   ├── pilot-pipeline.template.yaml
│   ├── pricing-ledger.template.yaml
│   └── external-receipts/
├── trust/
│   ├── machine-policy-receipts/
│   ├── release-candidates/
│   ├── oracle-register.yaml
│   └── claim-register.yaml
├── state/
├── queue/
└── artifacts/
```

Private customer data should live outside the repository. Repository entries are schemas, templates, sanitized records, or signed references.

## 5. Work-item model

Replace the current feature-only ledger with a typed work-item schema.

```yaml
version: 3
workItemId: V3-PROD-001
title:
lane: PRODUCT | MARKET | COMPETITOR | TRUST | FACTORY
kind: >
  CODE | SPECIFICATION | RESEARCH | CONTROLLED_EXPERIMENT |
  EXTERNAL_EVIDENCE | MACHINE_POLICY_ATTESTATION | COMMERCIAL_EXPERIMENT |
  MAINTENANCE | MIGRATION
milestone:
decisionContribution:
customerOutcome:
dependsOn:
softDependsOn:
blocksCommercialRelease:
priority:
riskTier:
maturityTarget:
disposition:
status:
ownerType: AI | MACHINE_POLICY_VERIFIER | CUSTOMER | EXTERNAL_PARTY
automatable:
packetPath:
evidenceRequired:
externalReceiptRequired:
machinePolicyReceiptRequired:
retryPolicy:
createdAt:
updatedAt:
```

### Status vocabulary

```text
PROPOSED
READY
QUEUED
RUNNING
PAUSED_QUOTA
WAITING_EXTERNAL
BLOCKED_POLICY
BLOCKED_TECHNICAL
BLOCKED_POLICY
PASSED_ENGINEERING
REJECTED_VALUE
NATIVE_SUFFICIENT
DEFERRED
SUPERSEDED
CANCELLED
COMPLETED
```

`COMPLETED` means the work item reached its declared outcome. It does not mean the product or company is complete.

### Disposition vocabulary

```text
KEEP
INTEGRATE_EXISTING_BACKEND
UPSTREAM
NARROW
REPLACE
PAUSE
STOP
NOT_REVIEWED
```

A disposition is an explicit product decision. It is not inferred from task status.

## 6. Milestone model

Replace “all 124 tasks passed” with bounded commercial milestones.

```yaml
milestoneId: M2_CONTROLLED_QUALIFICATION
type: ENGINEERING | COMMERCIAL | TRUST
entryCriteria:
exitCriteria:
requiredEvidence:
forbiddenClaims:
machinePolicyReceiptRequired:
status:
```

Initial milestones:

```text
M0_FACTORY_MIGRATED
M1_NATIVE_PREFLIGHT
M2_CONTROLLED_QUALIFICATION
M3_EXTERNAL_PREFLIGHT
M4_PAID_PILOT
M5_PAID_REPEAT
M6_COMMERCIALLY_SUPPORTED_PACK
```

Engineering completion may be automated for M0–M2, but M3–M6 depend on external evidence or independent machine-policy evidence and must never be fabricated.

## 7. Four-lane scheduler

### Lanes

#### PRODUCT

Build and validate the bounded product slice.

#### MARKET

Track external/customer actions and external evidence. AI may research accounts, prepare interview packets, or summarize attributable notes. It may not mark conversations, interest, payment, or customer outcomes as complete without external receipts.

#### COMPETITOR

Continuously test the complete native/bundled/agent substitute and update the source register.

#### TRUST

Develop independent oracles, security evidence, independent machine-policy requests, and release policies.

A fifth `FACTORY` lane handles controller maintenance and may not dominate normal scheduling.

### Lane independence

A blocked customer conversation must not stop an unrelated controlled product task. A missing independent machine-policy authorization must block external release, not internal testing. A competitor finding may stop a feature without stopping all product work.

### Initial WIP policy

```yaml
productMutating: 1
factoryMutating: 0 unless controller failure
readOnlyResearch: 1
externalTracking: unlimited records, no autonomous external action
machinePolicy: scoped BLOCKED_POLICY state
```

The machine may support more parallelism later, but shared subscription limits and merge complexity make concurrency a controlled resource.

## 8. Scheduler score

For each `READY` item:

```text
score =
  100 × current_milestone_critical_path
+  60 × customer_decision_relevance
+  50 × external_evidence_unblock
+  40 × native_equivalence_risk
+  30 × trust_release_blocker
+  20 × reusable_same_family_value
+  10 × short_feedback_cycle
-  30 × speculative_surface_area
-  25 × security_or_integration_burden
-  20 × likely_native_duplication
-  10 × context_or_quota_cost
```

Boolean factors may be 0/1; continuous factors use normalized values. The score is inspectable and overrideable through a signed bounded machine-policy decision.

Tie-breakers:

1. shortest path to current milestone;
2. evidence collection before implementation when uncertainty is material;
3. native comparison before proprietary duplication;
4. trust-core before dependent UI;
5. smaller reversible item before broad architecture;
6. stable ordering by ID.

Never select merely by file order.

## 9. Commercial gate behavior

Every product capability has two independent states:

```yaml
engineeringMaturity:
commercialMaturity:
```

Engineering:

```text
DESIGN_ONLY
IMPLEMENTED_EXPERIMENTAL
CONTROLLED_VALIDATED
EXTERNAL_VALIDATED
DEPRECATED
```

Commercial:

```text
NOT_EVALUATED
NATIVE_ADVANTAGE_UNPROVEN
NATIVE_ADVANTAGE_DEMONSTRATED
EXTERNAL_VALUE_DEMONSTRATED
COMMERCIALLY_SUPPORTED
WITHDRAWN
```

A controlled test can advance engineering maturity. Only attributable external evidence can advance external/commercial maturity.

### Value outcomes

```text
INCREMENTAL_DECISION_VALUE_DEMONSTRATED
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
EXTERNAL_EVIDENCE_REQUIRED
```

`NATIVE_WORKFLOW_SUFFICIENT`, `NO_INCREMENTAL_DECISION_VALUE`, and `TECHNICALLY_VALID_BUT_NOT_ECONOMIC` complete the experiment and stop or defer the feature. They must not trigger automatic implementation expansion.

## 10. Retry and recovery policy

Remove every “zero means unlimited” interpretation.

### Planning

```yaml
maxPlanAttempts: 2
maxAcceptanceCriteria: 12
maxOutputs: 8
maxSourceDocuments: 8
```

After two failed plans:

- classify the failure;
- split only if the outcome is genuinely multi-part;
- otherwise route to `BLOCKED_POLICY` or `REJECTED_VALUE`;
- do not repeatedly rewrite the packet.

### Implementation

```yaml
maxCandidateRepairCycles: 3
maxSameFindingRepeats: 2
maxCandidateRestarts: 1
```

If the same blocking-finding fingerprint appears twice:

- preserve candidate and artifacts;
- mark `BLOCKED_TECHNICAL`;
- create a bounded redesign decision;
- do not ask the same owner to try indefinitely.

### Infrastructure recovery

```yaml
maxInfrastructureRecoveriesPerRun: 3
maxFactorySelfRepairsPerIncident: 1
maxConsecutiveControllerRestarts: 3
```

Then:

- write `HARD_STUCK.json`;
- retain exact recovery instructions;
- stop automatic restart;
- never loop every 15 seconds forever.

### Value redesign

```yaml
maxValueRedesigns: 1
```

A second failure moves to a product disposition:

```text
NARROW
INTEGRATE_EXISTING_BACKEND
DEFER
STOP
```

### Completion expansion

```yaml
maxExpansionRoundsPerMilestone: 1
maxNewItemsPerExpansion: 5
machinePolicyForExpansion: true
```

Completion evaluation roles may propose work. They may not mutate the roadmap directly.

## 11. Task sizing

A work item is correctly sized when one accountable owner can deliver one independently verifiable outcome.

### Mechanical

- one deterministic edit;
- no broad product research;
- no adversary unless a gate fails;
- maximum five acceptance criteria;
- expected diff under roughly 300 lines, not a hard rule.

### Standard product

- one user/operator outcome;
- one integration boundary;
- one independent verifier;
- maximum ten acceptance criteria;
- explicit non-goals.

### Integration/trust

- one end-to-end contract;
- may cross packages;
- independent oracle;
- security/performance review where applicable;
- independent machine-policy authorization if externally exposed.

A naming/clearance task must not require the same universal criteria as a qualification engine.

## 12. Planner redesign

### Current failure mode

The planner receives a broad company corpus and expands catalog text into an exhaustive task packet. This creates self-referential, oversized packets and repeated planning.

### Replacement

The planner receives:

- one work item;
- current milestone;
- exact dependencies and evidence;
- relevant product docs only;
- changed native/competitor facts;
- a hard packet complexity budget.

The planner must produce:

```yaml
outcome:
decisionContribution:
acceptanceCriteria:
nonGoals:
allowedPaths:
forbiddenPaths:
gates:
risk:
oracle:
rollback:
stopConditions:
```

### Planner validation

Reject a packet when:

- criteria repeat source-document policy instead of task behavior;
- it requires unrelated product completion;
- allowed paths cannot satisfy outputs;
- it asks one task to create its own external evidence;
- it mixes product and factory changes;
- it contains customer/payment claims;
- it lacks a deterministic or independent verification path;
- it exceeds complexity bounds without a recorded exception.

### Plan reuse

If an existing packet remains valid at the current base SHA and source versions, reuse it. Do not regenerate it on every queue cycle.

## 13. Pipeline redesign

Split `pipeline.py` into explicit services:

```text
pipeline/
├── coordinator.py
├── candidate.py
├── stages.py
├── verification.py
├── value_gate.py
├── machine_policy_gate.py
├── release.py
├── recovery.py
└── artifacts.py
```

### Candidate lifecycle

```text
BASELINE_LOCKED
→ OWNER_MUTATION
→ DETERMINISTIC_GATES
→ INDEPENDENT_VERIFICATION
→ SPECIALIST_REVIEW_IF_REQUIRED
→ VALUE/TRUST GATES
→ RELEASE_CANDIDATE
→ PR
```

Do not repeat all stages after every advisory note. Only concrete blocking findings route back to the owner.

### Finding routing

```yaml
finding:
  fingerprint:
  blocking:
  ownerClass: PRODUCT | FACTORY | EXTERNAL | MACHINE_POLICY
  affectedCriterion:
  evidence:
  repairPaths:
```

- `PRODUCT`: return to product owner.
- `FACTORY`: preserve product candidate; run one bounded factory repair.
- `EXTERNAL`: wait; do not edit code to fabricate resolution.
- `MACHINE_POLICY`: request independent signed authorization.
- Advisory findings remain in release evidence and do not block.

### Candidate preservation

Retain the existing exact-SHA and worktree behavior. Add an immutable candidate manifest containing:

- base SHA;
- candidate SHA;
- task packet digest;
- source-context digest;
- stage artifacts;
- gate versions;
- model/backend identity;
- independent machine-policy authorizations;
- release decision.

## 14. Completion redesign

Replace global “commercialization-ready production build complete” with milestone completion.

### Deterministic completion

Each milestone owns:

- required product journeys;
- required schemas;
- required controlled cases;
- required security checks;
- forbidden claims;
- external evidence requirements;
- independent machine-policy authorizations.

### Review behavior

Three blind AI reviews are excessive for every milestone. Use:

- one deterministic verifier;
- one independent adversarial review for integration/trust milestones;
- one independent machine-policy authorization for external release;
- optional second independent private oracle for disputed trust-core changes.

### Expansion behavior

Independent evaluation roles return proposals. The controller writes:

```text
factory/roadmap/proposals/<milestone>/<timestamp>.yaml
```

Independent bounded machine policy accepts or rejects each proposal. No automatic append to the authoritative ledger.

## 15. Machine-policy authorization state

Add first-class records and status.

### Work-item state

```text
BLOCKED_POLICY
```

### Machine-policy authorization scopes

```text
SOURCE_OF_TRUTH_MIGRATION
EXTERNAL_RELEASE
COMMERCIAL_PACK_RELEASE
TRUST_CORE_CHANGE
SECURITY_BOUNDARY_CHANGE
CUSTOMER_CLAIM
ROADMAP_EXPANSION
WEDGE_DECISION
```

### Verification

- machine-policy receipt is signed and stored in the protected external authority root;
- exact candidate SHA and artifact digests are included;
- expiry and conditions are enforced;
- AI cannot write to the protected machine-authority root;
- invalid or missing machine-policy receipt fails closed.

## 16. External evidence state

The existing signed external-receipt design is valuable. Generalize it beyond one task ID.

```yaml
receiptVersion:
receiptId:
evidenceType:
subjectId:
issuer:
observedAt:
candidateOrOfferIdentity:
outcome:
artifacts:
limitations:
signature:
```

Evidence types:

```text
CUSTOMER_CONVERSATION
INCIDENT_ARCHIVE_ACCESS
PAID_PREFLIGHT
PAID_PILOT
DECISION_CHANGED
SECOND_PAID_ACTION
INDEPENDENT_OPERATOR
MACHINE_POLICY_ATTESTATION
UPSTREAM_ACCEPTANCE
PROVIDER_ACCEPTANCE
```

External receipts advance milestones but never mutate technical results.

## 17. Agent backend abstraction

Claude may remain the only configured executor initially, but durable state must be tool-neutral.

```python
class EngineeringAgentBackend(Protocol):
    def capabilities(self) -> AgentCapabilityReport: ...
    def start(self, request: AgentTaskRequest) -> AgentSession: ...
    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult: ...
    def cancel(self, session: AgentSession) -> None: ...
    def usage_state(self) -> UsageState: ...
```

`AgentTaskRequest` contains:

- role;
- system prompt;
- task packet;
- source-context manifest;
- allowed/forbidden paths;
- tools;
- network policy;
- output schema;
- candidate worktree;
- session limits.

Factory-owned and backend-neutral:

- roadmap;
- work-item schema;
- queue;
- checkpoints;
- path policy;
- gates;
- hidden tests;
- candidate manifests;
- finding routing;
- machine-policy receipts;
- Git release;
- audit log.

Rename Claude-specific fields in core models:

```text
advisor_model       → advisor_backend_config
peer_messaging      → collaboration_mode
session_name        → executor_session_name
claude_features     → executor_features
```

Keep a `ClaudeBackend` adapter under `tcfactory/backends/claude.py`.

## 18. Model and quota policy

The factory must have throughput budgets even under subscription authentication.

```yaml
weeklyAllocation:
  planning: 10%
  productImplementation: 45%
  adversarialVerification: 20%
  trustResearch: 15%
  factoryMaintenance: 5%
  reserve: 5%
maxConcurrentMutatingSessions: 1
maxConcurrentReadOnlySessions: 1
maxTurnsByRisk:
maxWallClockByStage:
priorityUnderPressure:
  - current paid/external milestone blocker
  - trust/security blocker
  - controlled product critical path
  - native comparison
  - factory maintenance
  - deferred platform breadth
```

Do not disable all task budgets. Monetary API-style budget may be irrelevant under Max, but turn, wall-clock, context, retry, and weekly-allocation limits are still necessary.

Quota exhaustion should:

- checkpoint;
- push or preserve the candidate;
- schedule resume;
- allow non-agent deterministic tasks;
- not start duplicate sessions.

## 19. Context redesign

### Context groups

```text
PRODUCT_NORMATIVE
TASK_SPECIFIC
CURRENT_UPSTREAM_FACTS
TRUST_POLICY
CUSTOMER_SANITIZED
FACTORY_CONTROL
```

Routine product tasks should not receive:

- acquisition thesis;
- career thesis;
- entire master plan;
- unrelated incident packs;
- full factory implementation;
- old superseded documents.

Context builder emits a manifest:

```yaml
documents:
  - path:
    digest:
    authority:
    relevance:
    maxLines:
omissions:
currentFactSnapshot:
```

A task is invalid if relevant current upstream facts are stale beyond the configured review period.

## 20. Prompt redesign

### `prompts/global.md`

Replace “work until done” with:

- deliver the bounded work item;
- preserve uncertainty;
- stop on unsupported external facts;
- do not expand scope;
- do not optimize task count;
- use native systems before proprietary duplication;
- report value-rejection states honestly.

### `prompts/autonomous_planner.md`

Require:

- packet complexity budget;
- decision contribution;
- native/substitute check;
- non-goals;
- finite acceptance criteria;
- rollback;
- machine-policy/external boundary.

### `prompts/research.md`

Separate:

1. current upstream fact research;
2. competitor benchmark;
3. product hypothesis research.

Do not require elaborate positive/negative-control manifests for a trivial stable fact. Apply evidence depth by claim risk.

### `prompts/builder.md`

Require:

- inspect existing product code before factory code;
- implement smallest complete outcome;
- no broad platform scaffolding;
- no test weakening;
- no product claim from synthetic evidence;
- produce operator and failure-path evidence.

### `prompts/adversary.md`

Focus on executable counterexamples and current criterion. Do not search for future improvements as blockers.

### New prompts

```text
prompts/native_substitute_reviewer.md
prompts/commercial_experiment.md
prompts/machine_policy_request.md
prompts/wedge_reviewer.md
prompts/milestone_auditor.md
```

## 21. Research-policy redesign

Keep strong source provenance for high-risk/current facts. Introduce levels.

### R0 — Stable repository fact

Evidence: exact repository path/SHA.

### R1 — Current official product fact

Evidence: official documentation/product page, retrieval time, quoted capability boundary.

### R2 — Technical design claim

Evidence: primary docs, source code, standards, or research paper; competing evidence; limitations.

### R3 — Commercial/market claim

Evidence: attributable customer/external receipt. Web research can establish competitor positioning, not customer demand.

Only R2/R3 require preregistered query plans or extensive controls. A naming-clearance task should not become an indefinite research experiment.

## 22. Value-gate redesign

The current value system is strong at binding evidence but too universal.

### Apply value gates to

- user-visible product outcomes;
- major integration;
- incident pack;
- qualification decision;
- performance/cost claim;
- external/commercial milestone.

### Do not apply commercial value gates to

- formatting;
- typo/naming cleanup;
- internal refactor;
- test fixture;
- controller repair;
- dependency maintenance.

These use engineering acceptance and parent-milestone linkage.

### Parent-milestone value

Foundational work is valuable only if:

- necessary for a bounded milestone;
- on the active critical path;
- not already provided by a native dependency;
- minimal for the milestone.

A generic statement such as “supports paid qualification” is insufficient.

## 23. Quality-policy redesign

Retain:

- secret detection;
- changed-path policy;
- test-skip/weakening detection;
- uncertainty laundering detection;
- candidate cleanliness;
- hidden gates.

Reduce brittle text scanning where it blocks legitimate prose or self-referential detector tests.

Required changes:

- parse executable ASTs where possible;
- scope text heuristics to live code;
- report warnings separately;
- unit-test false positives;
- require a concrete exploit or result change for blocking status;
- avoid scanning the entire historical repository for each small diff;
- version policy and record the version in candidate manifests.

## 24. Self-repair redesign

Factory self-repair is disabled during normal product work unless a controller-owned failure is demonstrated.

Allowed:

- reproduce controller failure;
- fix minimal causal code;
- add regression test;
- preserve product candidate.

Forbidden:

- product docs;
- product requirements;
- value thresholds;
- machine-policy authorization policy;
- external evidence;
- source precedence;
- private gates;
- broad dependency upgrades;
- network research unless specifically needed and read-only.

Policy:

```yaml
maxSelfRepairsPerIncident: 1
machinePolicyReviewAfterRepeat: true
mutatingTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash
network: deny
subagents: disabled
```

A self-repair that changes more than a small configured surface becomes a normal reviewed migration task.

## 25. Startup and restart redesign

### Current behavior to remove

An outer shell loop restarts the controller every 15 seconds until `STOP` or `HARD_STUCK`.

### Replacement

Use a supervised process with exponential backoff and a restart budget.

```text
15s
60s
5m
stop and mark HARD_STUCK
```

Reset the budget only after a healthy interval.

The launcher must:

- verify configuration version;
- verify clean/migrated state;
- verify single-instance lock;
- verify credentials;
- run deterministic health check;
- record boot ID;
- never delete recovery state;
- never start when source-of-truth migration is incomplete.

## 26. Git and GitHub release redesign

### Current risk

The factory may push only the exact receipt-authorized candidate to `main` with a race check and a normal non-force fast-forward push.

### Replacement

Use receipt-authorized exact-SHA direct-main release only.

```text
verified candidate
→ release branch
→ push
→ ordinary non-force push to `main`
→ required CI
→ independent machine-policy authorization and automated merge policy
```

Modes:

```yaml
releaseMode: DIRECT_MAIN_EXACT_SHA
autoMergeAllowed:
  mechanical: true after CI
  standard: true after required CI and a valid machine-policy receipt
  integration: true after required CI, private gates, and a valid machine-policy receipt
  trust_core: true after required CI, private oracles, and a valid machine-policy receipt
```

Required checks:

- factory unit/typing;
- product unit/contract;
- product controlled journey;
- secret/security;
- schema compatibility;
- source-of-truth integrity;
- independent machine-policy authorization where applicable.

Do not make a self-hosted runner the only required CI path. Add a GitHub-hosted CPU workflow for repository integrity and unit tests. Keep GPU/self-hosted workflows as separate explicit gates.

## 27. CI redesign

Workflows:

```text
factory-quality.yml
product-unit.yml
product-contract.yml
product-controlled-journey.yml
security.yml
source-of-truth-integrity.yml
gpu-controlled.yml
release.yml
```

`factory-quality` must not be named or treated as product CI.

Every workflow should have:

- least permissions;
- pinned actions;
- concurrency;
- timeout;
- artifact retention;
- exact package scope;
- clear required/optional status.

## 28. CLI and operator control

Add:

```text
tcfactory milestone-status
tcfactory lanes
tcfactory next-work
tcfactory dispositions
tcfactory approve
tcfactory reject-proposal
tcfactory external-receipt-status
tcfactory commercial-maturity
tcfactory retry-budget
tcfactory candidate-manifest
```

Control scripts and PowerShell wrapper must:

- accept repository and WSL distribution configuration;
- remove hardcoded user path;
- expose active milestone and lane;
- show retry/restart budgets;
- show external/machine-policy blockers separately;
- display product versus factory CI.

## 29. Configuration V3

### `config/factory.yaml`

Required changes:

```yaml
version: 3
executionMode: backend_protocol
releaseMode: direct_main_exact_sha
maxConcurrentMutatingSessions: 1
maxConcurrentReadOnlySessions: 1
workUntilDone: false
milestoneCompletion: true
directMainPush: true
```

### `config/autonomy.yaml`

```yaml
version: 3
autoPlan: true
autoEnqueue: true
autoMergeMechanical: false initially
autoResumeQuota: true
autoRecoverInterrupted: true
autoRespecFailedTasks: true
maxPlanAttempts: 2
maxCandidateRepairCycles: 3
maxSameFindingRepeats: 2
maxValueRedesigns: 1
maxCompletionExpansionRounds: 1
maxExpansionItems: 5
roadmapExpansionRequiresMachinePolicy: true
maxSelfRepairsPerIncident: 1
maxControllerRestarts: 3
```

No value uses zero to mean unlimited.

### New configuration

```text
config/scheduler.yaml
config/milestones.yaml
config/machine_authority.yaml
config/external_evidence.yaml
config/commercial_maturity.yaml
config/executors.yaml
```

## 30. Data migrations

Write explicit migrations.

### V1/V2 feature ledger to V3

- preserve every old task and notes;
- map statuses;
- mark noncritical broad tasks `DEFERRED`;
- map T001/T002 factory tasks to `FACTORY`;
- create new V3 milestone work items;
- retain old IDs as legacy references;
- do not consider legacy task count part of V1 completion.

### Queue

- checkpoint current running/queued packet;
- do not execute it during migration;
- archive old queue entries;
- create a migration receipt with hashes;
- resume only after source-of-truth and config V3 validation.

### Pipeline checkpoints

- preserve read-only;
- do not blindly resume V2 packet in V3;
- provide a salvage command that extracts candidate SHA/artifacts and asks whether the work remains relevant.

## 31. Required regression tests

### Scheduler

- selects critical-path item rather than list order;
- does not let one lane block others;
- honors WIP;
- prioritizes native comparison before duplicate implementation;
- stops rejected-value item;
- deterministic tie-breaking.

### Retry

- no unlimited interpretation;
- same-finding fingerprint escalation;
- completion expansion requires signed machine-policy authorization;
- controller restart budget stops loop;
- candidate preserved.

### External truth

- AI-writable receipt rejected;
- invalid signature rejected;
- synthetic receipt cannot advance commercial maturity;
- missing payment/second-use receipt remains external required.

### Independent machine-policy authorization

- exact SHA binding;
- expired machine-policy receipt rejected;
- wrong scope rejected;
- AI-generated local file rejected when trusted root required.

### Release

- no direct main push;
- PR created from verified candidate;
- integration/trust direct-main publication only after all required gates and a valid independent machine-policy receipt;
- CI identity bound to candidate SHA.

### Context

- acquisition/career docs excluded from routine build;
- stale current-fact snapshot blocks affected task;
- task context stays within configured budget.

### Completion

- M2 can complete without M4 external evidence;
- M4 cannot complete from synthetic fixtures;
- evaluation-role proposals do not mutate roadmap.

## 32. Migration execution order

### Step 0 — Pause

- stop scheduled/autopilot process;
- create clean baseline tag/branch;
- export current queue, ledger, checkpoints, and logs;
- verify CI.

### Step 1 — Install V3.1-ZH authority

- add V3 documents;
- update source precedence;
- keep old bundle immutable as archive;
- generate manifest and hashes.

### Step 2 — Add V3 schemas/models

- work items;
- milestones;
- maturity;
- machine-policy receipts;
- external receipts;
- dispositions;
- executor protocol.

### Step 3 — Implement scheduler and finite limits

- lane-aware queue;
- score;
- WIP;
- retry budgets;
- stop states;
- proposal-only completion expansion.

### Step 4 — Release and CI

- PR mode;
- split factory/product CI;
- portable control scripts.

### Step 5 — Product skeleton

- create packages;
- product schemas;
- CLI;
- controlled case scaffold;
- no broad platform implementation.

### Step 6 — Migrate roadmap

- archive 124-task chain;
- create gate-based V3.1-ZH work items;
- preserve history;
- do not resume T002 as company-critical work.

### Step 7 — Controlled validation

- run factory tests;
- run migration dry-run;
- run scheduler simulation;
- run one mechanical task;
- run one standard product task;
- simulate quota, failure, external wait, policy block, and rollback.

### Step 8 — Machine authorization and activation

- review source authority;
- review security/release policy;
- merge migration PR;
- restart with V3 config;
- observe first cycles.

## 33. Definition of a healthy factory

The factory is healthy when:

- it advances the active milestone;
- product code grows faster than controller code after M0;
- retry counts remain bounded;
- rejected work stops;
- external blockers are visible and isolated;
- no AI claims external validation;
- no direct trust-core merge occurs;
- current native facts are refreshed;
- status makes the active decision operator-readable;
- the queue does not require manual babysitting for ordinary recoverable failures.

The factory is unhealthy when:

- the same small task is repeatedly respecified;
- factory commits dominate product commits;
- completion creates an expanding backlog;
- all work is globally blocked by one item;
- task packets restate the entire company plan;
- controlled tests are presented as commercial proof;
- broad architecture progresses without market/native evidence;
- the process restarts indefinitely.

## 34. Factory success metric

Primary factory metric:

> Median time from a validated product or market uncertainty to a trustworthy decision and reusable artifact.

Supporting metrics:

- critical-path cycle time;
- first-pass plan validity;
- same-finding recurrence;
- candidate salvage rate;
- factory-to-product code ratio;
- percentage of work stopped/deferred before implementation;
- complete-substitute checks completed;
- independent machine-policy authorization turnaround;
- external evidence freshness;
- quota efficiency;
- escaped gate defects.

“Tasks completed” is not the primary metric.
