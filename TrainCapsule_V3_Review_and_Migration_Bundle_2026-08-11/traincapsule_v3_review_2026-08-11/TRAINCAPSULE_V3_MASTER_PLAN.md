# TrainCapsule V3 Consolidated Master Plan

**Prepared:** 11 August 2026  
**Audit baseline:** `TasfiqJ/TrainCapsule@c31caefaeed7e605f6ef304fae6fcfe708a163b9`  
**Status:** proposed V3 replacement bundle; no repository changes made by this review

This generated document consolidates the V3 replacement documents for convenient reading. In the repository, the individual files remain the authoritative operational units according to `SOURCE_PRECEDENCE.md`.

## Consolidated contents

1. Executive build decision
2. Product strategy and requirements
3. Technical architecture
4. Trust, replay, reduction, recovery, and contract specification
5. Commercial model and go-to-market
6. Autonomous factory redesign
7. Gate-based roadmap
8. Source-of-truth migration
9. Current source and competitive register
10. Claude Code build prompt

---



<!-- BEGIN 00_EXECUTIVE_BUILD_DECISION_V3.md -->

# 00 — Executive Build Decision V3

- **Document date:** 11 August 2026
- **Status:** BUILD AUTHORIZED — bounded commercial-slice build
- **Working codename:** TrainCapsule
- **Primary company objective:** create repeatable paid customer value
- **Initial category:** failure-derived change qualification for private distributed-training workloads
- **First serious paid product:** Incident-to-Change Qualification Pilot
- **Initial technical lane:** Linux, current pinned PyTorch, c10d/DDP/FSDP, NCCL, NVIDIA GPUs, customer-local execution
- **Initial commercial incident pack:** `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1`
- **Checkpoint pack status:** engineering reference pack; not commercially released by default
- **External release authority:** qualified human approval required
- **Supersedes:** the controlling build and commercial instructions in the 9 August 2026 bundle where they conflict with this document

## 00.1 Final decision

Continue TrainCapsule.

Do not continue the existing build plan or factory loop unchanged.

Build one complete, credible, customer-local qualification workflow before broadening the platform. Run market evidence, competitor/native benchmarking, and trust validation in parallel from the first milestone. Expand only after explicit evidence gates.

The controlling doctrine is:

> **Build the smallest trusted workflow that turns one real private training failure into a lower-cost experiment and a bounded release decision for one real upcoming change. Sell and repeat that decision before building the broader platform.**

The long-term architecture remains an option set. It is not the initial definition of done.

## 00.2 The product being built

TrainCapsule is not:

- a generic GPU observability dashboard;
- another NCCL error explainer;
- a general AI root-cause agent;
- an automatic restart system;
- a hardware-health product;
- a generic deterministic-replay platform;
- a universal training-correctness verifier;
- a hosted GPU fleet;
- or a multi-cloud control plane.

TrainCapsule is:

> **A customer-local evidence and experiment system that converts a costly distributed-training incident into a bounded, cheaper qualification contract for an upcoming software, hardware, topology, checkpoint, scheduler, or cloud change.**

The complete V1 outcome is:

```text
real incident
→ native evidence import
→ workload and environment identity lock
→ evidence-completeness and limitation report
→ first observed inconsistent boundary
→ pack-specific faithful experiment plan
→ baseline execution
→ candidate execution
→ named recovery-state checks
→ bounded release/migration decision
→ expiring local incident contract
→ scheduled or included second execution
```

## 00.3 The first paid offer

### Incident-to-Change Qualification Pilot

Required customer inputs:

```text
one active or reconstructable incident
+ one planned change within approximately 90 days
+ one named release, recovery, or migration decision
+ one baseline environment
+ one candidate environment
+ customer-local experiment authority
+ a named technical owner
+ a named budget owner
```

The engagement includes:

1. paid evidence and feasibility preflight;
2. complete native/substitute baseline;
3. identity and evidence lock;
4. one bounded pack-specific experiment;
5. approved legal reductions;
6. baseline and candidate execution;
7. Recovery Assurance for named state properties;
8. a release/migration decision with limitations;
9. an installed local contract;
10. one second execution or a contractually scheduled second execution.

The deliverable is not a diagnosis report. It is a decision artifact and a reusable local execution contract.

## 00.4 Why the change is necessary

A standalone incident investigation can be valuable and still fail as a business.

The customer may:

- resolve the problem once;
- convert the result into a free regression test;
- upstream the defect;
- accept restart and residual uncertainty;
- never need TrainCapsule again.

Joining incident closure to a real upcoming change tests recurring value in the first commercial engagement.

## 00.5 Product boundary

### Stable trust core to retain

- canonical identity and immutable evidence references;
- native evidence import;
- evidence completeness and perturbation reporting;
- observed-boundary analysis;
- explicit `UNKNOWN`;
- pack-specific experiment specification;
- reduction-faithfulness contracts;
- customer-local runner;
- Recovery Assurance;
- applicability envelopes;
- drift and expiry;
- baseline-versus-candidate qualification;
- offline verification;
- replaceable technical backends.

### V1 commercial slice

Build only:

1. environment/workload lock;
2. PyTorch Flight Recorder importer;
3. native findings record;
4. evidence eligibility and limitation report;
5. `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1` planner;
6. allowlisted pack-specific reductions;
7. local isolated runner;
8. baseline/candidate qualification;
9. named recovery-state checks;
10. signed/verifiable report and installed contract;
11. CLI and minimal local report viewer;
12. controlled fixtures and one head-to-head case.

### Deferred until evidence gates

- generic actor IR for every workload type;
- universal reduction compiler;
- broad multi-cloud federation;
- provider exchange standard;
- hosted multi-tenant platform;
- broad dashboards;
- automatic production remediation;
- owned GPU fleet;
- commercial release of the checkpoint pack;
- numerical-divergence pack;
- hardware-dependence pack;
- public marketplace or ecosystem;
- billing and enterprise administration;
- broad framework/scheduler/accelerator coverage.

Deferred does not mean rejected. It means not allowed to block the first paid proof.

## 00.6 Initial customer

The first target customer is a middle-sized AI organization that:

- runs recurring multi-node PyTorch/NCCL workloads;
- has a small infrastructure team serving multiple researchers or product teams;
- already uses framework and provider diagnostics;
- has suffered at least one costly unresolved or weakly explained incident;
- has a real upcoming stack, hardware, topology, checkpoint, scheduler, or cloud change;
- controls its launch, containers, traces, checkpoints, and experimental capacity;
- cannot or will not export all private code/data/evidence;
- has a technical owner who bears the release decision;
- can pay for expert-led delivery.

Do not begin with:

- frontier labs with extensive internal systems;
- hyperscalers;
- tiny teams whose incidents do not justify enterprise spend;
- customers without evidence or execution authority;
- customers seeking guaranteed root cause or universal correctness.

## 00.7 Competitive posture

TrainCapsule must use incumbents as inputs.

For every case:

```text
What did PyTorch/native tooling already establish?
What did the cloud/provider establish?
What did internal scripts and approved agents establish?
What remains decision-relevant?
What experiment can TrainCapsule run that changes the decision?
```

TrainCapsule receives no product credit for reproducing:

- a missing/mismatched collective already identified by Flight Recorder;
- a node-health issue already handled by a provider;
- a recovery consistency check already supplied by the recovery platform;
- a root-cause summary already produced by a diagnostic vendor;
- a healthy-run invariant already covered by an existing verifier;
- deterministic replay that does not produce a cheaper or more useful decision.

The competitive claim is intentionally narrow:

> Existing systems detect, diagnose, restart, replay, or verify selected properties. TrainCapsule converts a specific private incident into a lower-cost, applicability-bounded release gate against a future change.

## 00.8 Complete-substitute gate

Every product capability and every commercial pack must be tested against:

```text
framework-native tools
+ cloud/provider tooling
+ hardware/vendor tooling
+ relevant commercial diagnostic products
+ internal scripts
+ an approved engineer using current coding/operations agents
```

Possible outcomes:

```text
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
NATIVE_ADVANTAGE_DEMONSTRATED
EXTERNAL_VALUE_DEMONSTRATED
```

A technically correct feature may be rejected commercially.

## 00.9 Maturity model

Every pack, backend, and product surface has an explicit maturity:

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

Rules:

- implementation does not imply validation;
- controlled validation does not imply native advantage;
- native advantage does not imply willingness to pay;
- one paid case does not imply supported product;
- commercial support requires repeatability, documentation, security review, and operator independence.

## 00.10 Human authority

No external or commercial release may be approved solely by AI sessions, even if the sessions have:

- different prompts;
- different model names;
- separate worktrees;
- hidden tests;
- blind review;
- cross-session messaging;
- agent teams.

Before first external use and before every new commercial incident pack, a qualified human reviewer must approve:

1. trust model;
2. declared invariants;
3. experiment semantics;
4. legal reductions;
5. applicability and expiry;
6. security boundary;
7. result semantics;
8. permitted customer claims.

Trust-critical modules also require an independently derived oracle or reference:

- canonical identity/serialization;
- boundary alignment;
- reduction faithfulness;
- applicability/drift;
- recovery-state assurance;
- qualification decision semantics.

## 00.11 Engineering-factory doctrine

AI remains the primary implementation workforce. It is not the authority on demand, payment, customer value, or external safety.

The factory must be:

- lane-aware;
- bounded;
- task-type aware;
- backend-neutral;
- milestone-driven;
- capable of rejecting scope;
- incapable of fabricating external evidence;
- incapable of autonomously overturning a kill decision;
- incapable of commercial release without human approval.

Finite failure handling:

```text
attempt
→ bounded repair
→ at most two re-specifications
→ HUMAN_REVIEW / DEFER / SUPERSEDE / WEDGE_REJECT
```

Never:

```text
retry forever
→ enlarge packet forever
→ expand roadmap forever
```

## 00.12 Parallel lanes

### Lane A — Product and commercial slice

Build the V1 workflow.

### Lane B — Market evidence

- named account map;
- incident interviews;
- evidence-access qualification;
- planned-change qualification;
- paid pilot offer;
- human-led outreach and sales.

AI may prepare and organize. It may not invent conversations, commitments, signatures, or payments.

### Lane C — Native and competitor baseline

- current official source register;
- reproducible native workflows;
- differential benchmarks;
- backend absorption decisions;
- monthly wedge review.

### Lane D — Trust validation

- hidden tests;
- independent oracles;
- security review;
- GPU validation;
- qualified human approval.

A block in one lane does not stop independent work in another.

## 00.13 Milestone gates

### M0 — Factory migrated

- V3 authority installed;
- finite limits;
- lanes and task types;
- no current critical-path T002;
- PR/human release modes;
- old bundle archived;
- tests pass.

### M1 — Native baseline and eligibility

- Flight Recorder importer;
- evidence inventory;
- native findings;
- case eligibility;
- explicit no-value outcome;
- one controlled fixture.

### M2 — Controlled qualification slice

- workload/environment lock;
- pack-specific experiment;
- legal reduction;
- local runner;
- baseline/candidate comparison;
- recovery checks;
- expiry/UNKNOWN;
- independent clean execution.

### M3 — External preflight readiness

- qualified human trust approval;
- security package;
- operator guide;
- paid preflight scope;
- data-handling terms;
- no unsupported claims.

### M4 — Paid pilot

- real incident;
- real planned change;
- customer-local execution;
- paid commitment;
- decision artifact;
- second execution scheduled or included.

### M5 — Paid repeat

- same customer pays for a second execution or qualification;
- customer confirms incremental value;
- delivery effort and economics measured.

### M6 — Commercially supported pack

- at least two organizations or an explicitly approved strategic exception;
- third same-family case without trust-core rewrite;
- independent operator;
- mature security and support process;
- human release approval current;
- native advantage remains current.

## 00.14 Proof requirements before expansion

Before broad platform expansion, require:

- at least 20 detailed qualified conversations;
- at least three genuine incident archives or customer-local cases;
- at least one paid pilot;
- TrainCapsule materially exceeds the complete substitute in at least two cases;
- at least one paid repeat;
- third same-family case without trust-core rewrite;
- one operator other than the founder executes and understands the result;
- customer confirms decision value exceeds price and retained effort.

These are evidence gates, not vanity metrics.

## 00.15 Kill and replacement rules

Stop, narrow, or replace the wedge when:

- the complete native workflow reaches the same release decision;
- customers accept restart and uncertainty;
- no customer pays for a second execution;
- every case requires a new trust core;
- the reduced experiment costs nearly as much as the original;
- customer retained effort remains too high;
- evidence and local execution access are consistently unavailable;
- the product creates reports but does not alter decisions;
- security review makes delivery uneconomic;
- a competitor makes the incremental gap non-material.

The factory may recommend a disposition. A human records the final wedge decision.

## 00.16 Commercial hypotheses

These are internal experiments, not validated prices:

| Offer | Internal test range |
|---|---:|
| Evidence/feasibility preflight | USD 15,000–25,000 |
| Incident-to-Change Qualification Pilot | USD 40,000–75,000 |
| Additional qualification event | USD 20,000–50,000 |
| Annual protected-workload agreement | USD 100,000–200,000 |
| Provider integration | USD 250,000+ |

A provisional USD 1 million annual model:

```text
6 annual customers × $125,000 = $750,000
5 pilots × $50,000           = $250,000
                              ----------
                              $1,000,000
```

This is a falsifiable planning model, not a forecast.

## 00.17 External message

Lead with:

> **We turn your worst distributed-training failure into a customer-local release gate for your next PyTorch, CUDA, NCCL, driver, checkpoint, GPU, topology, scheduler, or cloud change.**

Do not lead with:

- black-box recorder;
- GPU root cause;
- NCCL debugger;
- replay engine;
- AI incident agent;
- observability;
- universal reliability.

## 00.18 Final authorization

Authorized now:

- V3 source-of-truth migration;
- factory-loop redesign;
- first qualification slice;
- parallel market/native/trust lanes;
- expert-led productized service;
- provisional open eligibility tool;
- controlled head-to-head case.

Not authorized without further evidence:

- broad platform completion;
- second commercial pack;
- federation ecosystem;
- hosted SaaS;
- autonomous remediation;
- claims of customer demand, ROI, accuracy, market size, or acquisition interest.

This is the controlling build decision.


<!-- END 00_EXECUTIVE_BUILD_DECISION_V3.md -->


<!-- BEGIN 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md -->

# 03 — Product Strategy and Requirements V3

## 03.1 Product definition

TrainCapsule is a customer-local failure-derived change qualification system for private distributed-training workloads.

Its first commercial job is:

> Given one costly active or historical distributed-training incident and one real upcoming stack or infrastructure change, establish the best available native baseline, construct a bounded lower-cost faithful experiment when possible, evaluate named recovery-state properties, and return an applicability-bounded release or migration decision.

## 03.2 Primary job to be done

When an AI infrastructure owner is preparing to change:

- PyTorch;
- CUDA;
- NCCL;
- driver or firmware;
- container image;
- checkpoint format or resume policy;
- GPU generation or node type;
- topology;
- scheduler;
- cloud or provider;
- relevant workload code;

and a past incident creates material uncertainty, help that owner answer:

```text
Can we approve this change?
Should we block it?
What remains unknown?
What evidence would resolve the unknown?
When does this decision expire?
Can we rerun the same contract later without reconstructing the incident?
```

## 03.3 Buyer, user, and decision owner

### Economic buyer

Usually:

- Head/Director of ML Infrastructure;
- VP Engineering at a model company;
- platform engineering leader;
- research infrastructure leader;
- neocloud support/reliability leader;
- technical founder with meaningful training spend.

### Primary user

- distributed-training engineer;
- ML infrastructure engineer;
- GPU systems engineer;
- reliability/SRE engineer;
- forward-deployed or field engineer.

### Decision owner

The named individual accountable for:

- framework upgrade;
- hardware migration;
- cloud migration;
- recovery policy;
- checkpoint strategy;
- critical workload release.

A case without a named decision owner is not yet a qualified pilot.

## 03.4 Ideal customer profile

### Required characteristics

- recurring multi-node PyTorch/NCCL training or post-training;
- at least one materially expensive incident;
- upcoming change with a date and owner;
- access to native evidence;
- ability to run customer-local experiments;
- control of images, launch configuration, and relevant workload artifacts;
- enough engineering or compute cost to justify a paid engagement;
- willingness to state the decision and acceptance boundary.

### Positive signals

- repeated provider escalations;
- cross-cloud or provider migration;
- private workload evidence that cannot leave the environment;
- disagreement about workload versus provider responsibility;
- an unresolved checkpoint/recovery concern;
- high-cost reruns;
- small infrastructure team supporting several research teams;
- fear of a stack upgrade because a prior failure was never converted into a regression contract.

### Disqualifiers

- single-GPU or low-cost workloads;
- no planned change;
- no evidence and no ability to rerun;
- native restart is accepted and residual uncertainty is immaterial;
- request is only for a dashboard or alert;
- demand for guaranteed root cause;
- demand for universal model correctness;
- insufficient value relative to integration effort;
- prohibited data export with no customer-local execution route;
- no budget owner.

## 03.5 First commercial offer

### Name

**Incident-to-Change Qualification Pilot**

### Entry conditions

The pilot is accepted only when all are present:

```text
incident
planned change
named decision
baseline
candidate
local execution authority
technical owner
budget owner
```

### Pilot phases

#### Phase 1 — Paid preflight

Outputs:

- evidence inventory;
- rights/privacy classification;
- native workflow baseline;
- case eligibility;
- likely experiment classes;
- explicit disqualifiers;
- statement of unknowns;
- bounded pilot proposal.

Possible results:

```text
ELIGIBLE
ELIGIBLE_WITH_LIMITATIONS
NATIVE_WORKFLOW_SUFFICIENT
INSUFFICIENT_EVIDENCE
NO_ECONOMIC_CASE
DECLINE
```

#### Phase 2 — Qualification build and execution

Outputs:

- identity lock;
- native findings;
- experiment specification;
- legal-reduction record;
- baseline result;
- candidate result;
- Recovery Assurance record;
- decision and limitations;
- installed local contract.

#### Phase 3 — Included or scheduled second execution

The initial commercial contract must include either:

- one second qualification execution; or
- a specific second-use date/change and prepaid or contractually committed execution.

The initial pilot does not count as evidence of recurring business until the second event occurs.

## 03.6 Product workflow

```text
INTAKE
→ NATIVE_BASELINE
→ IDENTITY_LOCK
→ EVIDENCE_ASSESSMENT
→ ELIGIBILITY
→ EXPERIMENT_PLAN
→ REDUCTION_REVIEW
→ BASELINE_RUN
→ CANDIDATE_RUN
→ RECOVERY_ASSURANCE
→ QUALIFICATION_DECISION
→ CONTRACT_INSTALL
→ REQUALIFICATION
```

## 03.7 Product outputs

### Incident Intake Record

Contains:

- customer case ID;
- decision owner;
- incident summary;
- business/compute impact as customer-supplied data;
- planned change;
- decision deadline;
- evidence locations;
- privacy and rights;
- permitted execution environment;
- explicit prohibited operations.

### Workload Identity Lock

Contains:

- source revision;
- container/image digest;
- dependency lock;
- PyTorch/CUDA/NCCL versions;
- driver/firmware where available;
- GPU architecture;
- rank/process-group topology;
- scheduler/launcher;
- environment variables relevant to the pack;
- data contract and controlled input identity;
- checkpoint identity and format where relevant;
- canonical serialization version.

### Evidence Inventory

For each evidence item:

- source;
- time range;
- rank/node coverage;
- integrity;
- collection configuration;
- known perturbation;
- rights class;
- completeness;
- limitations;
- content hash.

### Native Findings Record

Must state:

- native tools executed;
- exact versions/configuration;
- findings already produced;
- unresolved questions;
- native decision, if any;
- customer effort;
- compute cost;
- time to decision.

### Experiment Specification

Must state:

- hypothesis;
- observed boundary;
- manipulated variable;
- controlled variables;
- expected discriminating observations;
- legal transformations;
- forbidden transformations;
- budget;
- stop conditions;
- applicability;
- oracle;
- result semantics.

### Reduction Faithfulness Record

Must state:

- original scope;
- reduced scope;
- transformation sequence;
- preserved properties;
- unpreserved properties;
- comparison evidence;
- rejected reductions;
- confidence/evidence tier;
- expiry implications.

### Recovery Assurance Record

Evaluates only named properties, such as:

- model/optimizer state;
- scheduler state;
- RNG state;
- sampler/data cursor;
- shard ownership;
- replay/skip semantics;
- short-window numerical trajectory;
- throughput after recovery;
- application-specific state.

It must not claim long-horizon model correctness unless independently supported.

### Qualification Decision

Possible technical states:

```text
PASS
FAIL
UNKNOWN
INAPPLICABLE
EXPIRED
```

Possible customer-value states:

```text
DECISION_VALUE_DEMONSTRATED
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
EXTERNAL_EVIDENCE_REQUIRED
```

Decision output includes:

- named decision;
- scope;
- evidence;
- result;
- limitations;
- invalidation triggers;
- expiry;
- required follow-up;
- reviewer and approval metadata.

### Workload Incident Contract

Contains:

- stable contract ID/version;
- workload/environment applicability;
- evidence and native baseline;
- executable plan;
- expected observations;
- decision rules;
- Recovery Assurance profile;
- expiry/drift rules;
- local execution package;
- offline verifier;
- approved claims.

## 03.8 Initial incident pack

### `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1`

This pack addresses a bounded family in which a distributed actor fails to satisfy a collective or lifecycle contract because of an upstream event.

Candidate mechanisms include:

- omitted collective;
- reordered collective;
- incompatible collective arguments;
- data-dependent branch;
- data-loader stall preventing progress;
- checkpoint path preventing progress;
- process exit;
- process-group membership inconsistency;
- bounded runtime/kernel lifecycle condition distinguishable from ordinary delay.

### Native baseline

PyTorch Flight Recorder and `fr_trace` are mandatory inputs when applicable.

TrainCapsule gets no incremental credit for:

- identifying the missing rank;
- listing a collective mismatch;
- displaying an existing call stack;
- reporting shapes/dtypes already supplied by native tooling.

### Incremental product requirement

At least one must hold:

- preserve or reconstruct the upstream trigger;
- reduce execution burden materially;
- create a faithful executable customer-local experiment;
- distinguish customer-important mechanism classes;
- evaluate the proposed correction or guard;
- qualify a real candidate environment;
- create a durable re-runnable contract.

### V1 legal-reduction classes

The initial implementation is allowlisted, not generic.

Potential transformations, subject to pack-specific proof:

1. **Iteration-window reduction**
   - retain only the window needed to reach the first observed boundary.
2. **Rank-set reduction**
   - reduce participating ranks only when process-group and mismatch semantics are preserved.
3. **Input minimization**
   - minimize input while preserving the controlling branch predicate and relevant data contract.
4. **Model-graph pruning**
   - remove unrelated operations only when pre-boundary event and collective signatures remain equivalent.
5. **State snapshot**
   - start from a verified earlier state when doing so preserves the causal path.
6. **Environment variable isolation**
   - vary exactly one suspected configuration while locking the rest.
7. **Topology substitution**
   - prohibited by default; allowed only under a separately declared structural-evidence tier.

### V1 prohibited reductions

- changing the candidate variable while claiming it is controlled;
- replacing distributed execution with single-device execution without an explicit structural tier;
- changing rank/process-group relationships without proof;
- replacing private data with synthetic data without preserving the branch/control contract;
- changing framework/CUDA/NCCL/driver versions except as the named qualification variable;
- dropping evidence gaps;
- calling statistical similarity deterministic reproduction.

## 03.9 Checkpoint pack policy

`CHECKPOINT_RESUME_STATE_CONSISTENCY_V1` remains an engineering reference pack.

It may be built for:

- trust-core exercise;
- controlled evaluation;
- architecture validation;
- internal demo.

It is not automatically the second commercial wedge.

Commercial release requires:

- a customer-important state property not covered by the complete native recovery workflow;
- a real recovery/release decision changed by that property;
- native advantage demonstrated;
- qualified human approval;
- external value evidence.

## 03.10 Open and paid boundary

### Open or freely accessible eligibility layer

Candidate surface:

```text
traincapsule ingest flight-recorder/
traincapsule evidence assess
traincapsule native compare
traincapsule eligibility report
```

It may:

- import native evidence;
- lock basic environment identity;
- show evidence gaps;
- summarize native findings;
- identify whether a qualification pilot is feasible.

### Paid outcome

- private incident modeling;
- faithful experiment construction;
- private reference management;
- baseline/candidate execution;
- recovery-state assurance;
- maintained qualification;
- customer-specific local runner;
- expert review;
- requalification.

Do not open-source the customer-specific operational outcome by default. Open interfaces, schemas, verifier, selected fixtures, and upstreamable tests where trust and distribution benefit.

## 03.11 Productized service posture

The first version is expert-led.

Acceptable:

- founder/adviser reviews evidence;
- software constructs and executes the bounded workflow;
- customer operates local runner with assistance;
- human approves experiment semantics;
- delivery produces reusable code, contract, or pack improvements.

Unacceptable:

- every case is a bespoke consulting project;
- no reusable artifact survives;
- founder intuition is the only oracle;
- delivery effort does not fall;
- customers do not repeat;
- product is called SaaS when it is service delivery.

Track:

```text
reusable software ratio
founder hours
customer hours
compute cost
time to decision
new trust-core code required
new pack-specific code required
repeat execution effort
gross delivery margin
```

## 03.12 Complete-substitute differential benchmark

For every major milestone, execute:

### Baseline A — Native only

Framework-native tools and documented workflow.

### Baseline B — Native plus provider/vendor

Relevant platform support and recovery.

### Baseline C — Native plus internal engineer and approved agent

A competent engineer using current scripts and coding/operations agents.

### Candidate — TrainCapsule

Same evidence access and decision target.

Measure:

- decision reached;
- correctness/grounding;
- time;
- human effort;
- compute;
- privacy exposure;
- repeatability;
- applicability;
- residual unknowns;
- ability to rerun after change.

Commercial success requires more than a prettier report.

## 03.13 Product maturity

Each product surface records:

```yaml
engineering_maturity: DESIGN_ONLY | IMPLEMENTED_EXPERIMENTAL | CONTROLLED_VALIDATED
native_advantage: UNPROVEN | DEMONSTRATED | LOST
external_value: UNPROVEN | DEMONSTRATED
commercial_support: NO | LIMITED | YES | DEPRECATED
```

The flattened public status maps to:

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

## 03.14 Required nonfunctional properties

### Truth

- unsupported facts remain unknown;
- native findings are attributed;
- causal language is bounded;
- technical and commercial outcomes are separate.

### Security

- local by default;
- no outbound network by default;
- least privilege;
- explicit evidence rights;
- secret scanning;
- audit trail;
- signed outputs where required.

### Reproducibility

- immutable identities;
- versioned schemas;
- executable plan;
- pinned environment;
- offline verifier;
- deterministic serialization.

### Usability

A qualified engineer should:

- install the eligibility tool in under one hour on a supported environment;
- import a supported Flight Recorder case without editing product code;
- understand evidence gaps;
- execute a prepared contract from documented commands;
- distinguish `PASS`, `FAIL`, `UNKNOWN`, `INAPPLICABLE`, and `EXPIRED`.

These are target requirements and must be measured before being claimed.

### Performance

No universal overhead claim is authorized.

For each case, measure:

- ingest time;
- storage;
- capture overhead where TrainCapsule adds capture;
- experiment runtime;
- cost ratio to original/full reproduction;
- qualification rerun time.

## 03.15 Pilot success contract

A pilot is technically successful only if:

- evidence and identity are valid;
- result semantics are correct;
- limitations are explicit;
- independent execution reproduces the reported outcome.

A pilot is commercially successful only if:

- it changes or materially supports the named decision;
- it adds value beyond the complete substitute;
- cost and retained effort are acceptable;
- the customer approves a second execution or annual path.

Suggested internal target hypotheses, adjustable per account:

```text
experiment cost ≤ 25% of a credible full reproduction
or at least 4× lower than the practical alternative

customer retained effort ≤ 16 engineer-hours after access/setup
repeat execution ≤ 4 operator-hours
decision delivered before the customer's change deadline
```

These are experiment thresholds, not public promises.

## 03.16 Product metrics

### North-star commercial metric

```text
paid qualification decisions repeated per protected workload
```

### Supporting metrics

- paid pilots;
- paid repeats;
- protected workloads;
- qualification events;
- complete-substitute wins;
- time to decision;
- experiment cost ratio;
- customer retained effort;
- contract re-use;
- trust-core rewrites per case;
- operator independence;
- gross delivery margin;
- expired/unknown decisions handled correctly;
- false confirmed-attribution count;
- customer-approved outcome value.

### Anti-metrics

Do not optimize for:

- lines of code;
- task count;
- agent turns;
- generated tests;
- number of dashboards;
- number of adapters;
- number of incident packs;
- GitHub stars alone;
- model-written quality scores.

## 03.17 Discovery requirements

Before M4, obtain at least:

- 20 detailed conversations about specific incidents and planned changes;
- three real incident archives or customer-local cases;
- two credible pilot candidates;
- one paid pilot.

Each conversation must capture:

- incident;
- current workflow;
- total elapsed resolution time;
- engineer effort;
- compute loss;
- decision affected;
- upcoming change;
- evidence access;
- security constraints;
- native tools used;
- willingness to run locally;
- budget process;
- what would make the result not worth buying.

A generic “this sounds useful” is not qualifying evidence.

## 03.18 Scope dispositions

Every surface receives one monthly disposition:

```text
KEEP
INTEGRATE_EXISTING_BACKEND
UPSTREAM
NARROW
REPLACE_WEDGE
PAUSE
STOP
```

The factory cannot preserve a feature because code already exists.

## 03.19 Claims policy

Permitted before external evidence:

- design description;
- controlled benchmark results;
- supported input/output behavior;
- measured fixture performance;
- limitations;
- maturity state.

Prohibited before external evidence:

- customer count;
- revenue;
- production savings;
- root-cause accuracy;
- general overhead;
- market size;
- broad reliability improvement;
- willingness to pay;
- acquisition interest.

## 03.20 Definition of product success

TrainCapsule is becoming a successful business product when:

1. qualified customers provide real evidence;
2. the system changes real decisions beyond native tooling;
3. at least one customer pays twice;
4. the third same-family case does not require trust-core redesign;
5. another operator can execute it;
6. delivery economics improve;
7. the product remains useful as native tooling advances;
8. commercial support is based on current human-approved trust and security evidence.

Repository completion alone is not success.


<!-- END 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md -->


<!-- BEGIN 04_TECHNICAL_ARCHITECTURE_V3.md -->

# 04 — Technical Architecture V3

## 04.1 Architectural objective

Build the smallest production-credible system that can complete one paid **Incident-to-Change Qualification Pilot** without pretending to be a general GPU-reliability platform.

The V1 architecture must answer this bounded question:

> Given one real or controlled distributed-training incident, one baseline environment, one candidate environment, and a declared release decision, can TrainCapsule construct and execute a lower-cost experiment whose preserved properties are explicit, evaluate named recovery-state properties, and issue a bounded decision with honest limitations?

Everything that does not materially help answer that question belongs outside the first commercial slice.

## 04.2 Architecture doctrine

The architecture is governed by twelve rules.

1. **Native tools are inputs, not enemies.** Import PyTorch Flight Recorder and other approved evidence before adding proprietary capture.
2. **Customer-local by default.** Private code, data, checkpoints, topology, and raw traces stay inside the customer's boundary unless the customer explicitly exports them.
3. **Immutable identity before interpretation.** No experiment, comparison, or qualification result is valid without workload, environment, evidence, pack, plan, and candidate identities.
4. **Observed boundary is not root cause.** The system may state the first observed inconsistency and supported mechanism evidence; it may not silently promote correlation to causation.
5. **Reduction is a contract.** A reduced experiment is valid only with declared preserved properties, legal transformations, counterexamples attempted, applicability limits, and invalidation conditions.
6. **Baseline and candidate are symmetric.** Both execute the same signed experiment contract under the same comparison policy unless a declared adaptation is required.
7. **`UNKNOWN` is a successful truth state.** It is not a pipeline failure and must remain distinct from infrastructure failure, invalid evidence, and test failure.
8. **Commercial support is narrower than implementation.** Experimental components may exist without being exposed as supported product surfaces.
9. **Trust-critical release requires human authority.** AI review is supporting evidence, never the sole external release authority.
10. **Replaceable backends.** Native and third-party diagnostic, alignment, emulation, hardware, checkpoint, and support systems plug into stable interfaces.
11. **No hosted-control-plane dependency in V1.** A local CLI and local report viewer must complete the workflow without a TrainCapsule-operated SaaS.
12. **Every subsystem must trace to a release decision.** Components without a concrete contribution to qualification, trust, delivery, or repeat use are deferred.

## 04.3 Initial supported envelope

### Supported in the first commercial slice

- Linux containers;
- one pinned current stable PyTorch line at a time;
- c10d/DDP as the primary path;
- bounded FSDP evidence where the selected incident requires it;
- NCCL collectives;
- NVIDIA GPUs;
- Slurm and a local process launcher through adapters;
- customer-local filesystem and S3-compatible evidence stores;
- PyTorch Flight Recorder import;
- controlled 2–8 GPU development and verification;
- scale-faithfulness claims only when separately established;
- baseline-versus-candidate software or infrastructure comparison;
- `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1`;
- named checkpoint/recovery properties required by the selected pilot, without commercially releasing the broad checkpoint pack.

### Explicitly unsupported until evidence authorizes expansion

- universal framework support;
- every scheduler and cloud;
- generic Kubernetes fleet management;
- owned GPU capacity;
- multi-tenant hosted SaaS;
- automatic production remediation;
- generalized root-cause guarantees;
- universal deterministic replay;
- model-quality certification;
- hardware certification or RMA authority;
- public cross-customer incident graph;
- provider federation network;
- marketplace or exchange standard;
- broad dashboard suite;
- broad RBAC, billing, and enterprise administration.

Unsupported does not mean technically impossible. It means the surface is not allowed to consume product effort before the initial qualification workflow earns external value.

## 04.4 Repository layout

The present repository packages only the AI factory. Product code should be introduced in an explicit product namespace while the existing factory remains isolated.

```text
/
├── packages/
│   ├── traincapsule-core/
│   │   └── src/traincapsule_core/
│   ├── traincapsule-ingest-pytorch/
│   │   └── src/traincapsule_ingest_pytorch/
│   ├── traincapsule-runner-local/
│   │   └── src/traincapsule_runner_local/
│   ├── traincapsule-qualify/
│   │   └── src/traincapsule_qualify/
│   ├── traincapsule-cli/
│   │   └── src/traincapsule_cli/
│   └── traincapsule-viewer/
│       └── src/
├── schemas/product/
├── incident-packs/
│   └── pre_collective_lifecycle_v1/
├── examples/product/
├── tests/product/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── adversarial/
│   └── journeys/
├── docs/product/
├── docs/company/
├── tcfactory/
├── factory/
└── prompts/
```

The product and factory may share repository infrastructure, but not domain models, completion definitions, status vocabularies, or release authority.

## 04.5 Bounded V1 component map

```text
Incident Intake
      │
      ▼
Identity Lock ───────────────► Evidence CAS
      │                              │
      ▼                              ▼
Native Evidence Import ─────► Native Baseline Report
      │                              │
      └──────────────┬───────────────┘
                     ▼
          Eligibility / Evidence Gap
                     │
          ┌──────────┴──────────┐
          │                     │
      NOT ELIGIBLE          ELIGIBLE
          │                     │
   bounded preflight             ▼
                      Pack-Specific Experiment Planner
                                  │
                                  ▼
                         Reduction / Faithfulness
                                  │
                      human approval where required
                                  ▼
                         Signed Experiment Contract
                           ┌───────┴────────┐
                           ▼                ▼
                     Baseline Runner   Candidate Runner
                           └───────┬────────┘
                                   ▼
                          Recovery Assurance
                                   │
                                   ▼
                         Qualification Comparator
                                   │
                                   ▼
                         Decision + Applicability
                                   │
                                   ▼
                         Local Incident Contract
```

## 04.6 Core domain objects

Product schemas must be versioned under `schemas/product/`. Canonical serialization must be deterministic and separately tested.

### `WorkloadIdentity`

Minimum fields:

```yaml
schemaVersion:
workloadId:
sourceIdentity:
  repositoryDigest:
  dirtyPatchDigest:
entrypoint:
argumentsDigest:
containerImageDigest:
dependencyLockDigest:
framework:
  name:
  version:
distributed:
  strategy:
  worldSize:
  processGroupsDigest:
modelStructureDigest:
dataIdentity:
  policy:
  manifestDigest:
checkpointPolicyDigest:
privacyClass:
createdAt:
```

`dataIdentity.policy` may be `FULL_DIGEST`, `MANIFEST_DIGEST`, `CUSTOMER_ATTESTED`, or `UNAVAILABLE`. A weaker identity must narrow the result; it must never be represented as equivalent to a full content identity.

### `EnvironmentIdentity`

```yaml
schemaVersion:
environmentId:
hostKernel:
containerRuntime:
python:
pytorch:
cudaRuntime:
cudaDriver:
nccl:
gpu:
  model:
  count:
  firmwareDigest:
topologyDigest:
scheduler:
networkClass:
storageClass:
environmentVariablesDigest:
materializationRecipeDigest:
createdAt:
```

Only decision-relevant variables should enter canonical identity. Secrets must be redacted before identity generation. Redaction itself must be deterministic and policy-versioned.

### `EvidenceArtifact`

```yaml
schemaVersion:
artifactId:
kind:
sourceAdapter:
sourceVersion:
capturedAt:
contentDigest:
sizeBytes:
compression:
encryption:
privacyClass:
customerLocalUri:
exportPolicy:
provenance:
integrityStatus:
```

The canonical record stores metadata and hashes. Raw evidence may remain outside the repository and outside any TrainCapsule-operated service.

### `NativeFinding`

```yaml
schemaVersion:
findingId:
nativeSystem:
nativeVersion:
observation:
evidenceRefs:
confidenceClass:
limitations:
customerDecisionContribution:
```

`confidenceClass` is not a probability unless it comes from a calibrated process. Use semantic categories such as `DIRECT_OBSERVATION`, `DERIVED_ALIGNMENT`, `TOOL_HEURISTIC`, or `UNVERIFIED_NARRATIVE`.

### `IncidentCase`

```yaml
schemaVersion:
caseId:
decisionOwner:
decisionType:
decisionDeadline:
incidentSummary:
baselineEnvironmentId:
candidateEnvironmentId:
workloadId:
evidenceRefs:
nativeFindings:
packCandidate:
economics:
  estimatedOriginalRunCost:
  estimatedInvestigationCost:
  estimatedDelayCost:
  currency:
privacyPolicy:
status:
```

### `EvidenceCompletenessReport`

It must enumerate required, present, missing, conflicting, stale, corrupted, and inaccessible evidence. The report must distinguish:

- evidence missing because it was never captured;
- evidence unavailable because of policy;
- evidence technically inaccessible;
- evidence inconsistent across ranks;
- evidence whose identity cannot be tied to the incident;
- evidence whose source version is unsupported.

### `ExperimentHypothesis`

```yaml
hypothesisId:
statement:
mechanismClass:
supportingEvidence:
contradictingEvidence:
discriminatingObservation:
priority:
status:
```

Statuses: `PROPOSED`, `REJECTED`, `SUPPORTED`, `NOT_DISCRIMINATED`, `INVALIDATED`, `UNKNOWN`.

### `ReductionStep`

```yaml
stepId:
operator:
beforeIdentity:
afterIdentity:
preserves:
relaxes:
requires:
counterexamples:
verificationEvidence:
verdict:
```

No free-form “simplification” may enter a qualification contract. Every reduction must invoke a registered operator with pack-specific legality rules.

### `FaithfulnessContract`

```yaml
schemaVersion:
faithfulnessId:
originalCaseId:
experimentIdentity:
preservedProperties:
relaxedProperties:
excludedMechanisms:
applicabilityEnvelope:
counterexamplesAttempted:
requiredScaleEvidence:
requiredTopologyEvidence:
verdict:
approvedBy:
expiresAt:
invalidationRules:
```

Verdicts: `ESTABLISHED`, `BOUNDED`, `NOT_ESTABLISHED`, `UNKNOWN`, `INVALIDATED`.

### `RecoveryProperty`

Examples:

- process-group reconstruction;
- checkpoint readability;
- model parameter identity or bounded equivalence;
- optimizer state;
- scheduler state;
- RNG continuity;
- sampler state;
- data cursor;
- sharded ownership;
- replay/skip semantics;
- declared short-run numerical sentinel;
- throughput or latency observation window.

Each property has its own oracle, tolerance, observation period, and failure semantics.

### `ExperimentContract`

```yaml
schemaVersion:
contractId:
caseId:
packId:
packVersion:
workloadIdentity:
baselineEnvironmentIdentity:
candidateEnvironmentIdentity:
planDigest:
faithfulnessContract:
runnerPolicy:
recoveryProperties:
comparisonPolicy:
resourceBudget:
timeBudget:
privacyPolicy:
expiry:
humanApprovals:
signature:
```

### `ExecutionRecord`

```yaml
executionId:
contractId:
environmentRole: BASELINE | CANDIDATE
startedAt:
completedAt:
runnerIdentity:
materializedEnvironmentId:
observedWorkloadId:
resourceUsage:
artifacts:
result:
infrastructureEvents:
policyViolations:
```

### `QualificationDecision`

```yaml
schemaVersion:
decisionId:
contractId:
baselineExecutionId:
candidateExecutionId:
status:
decision:
supportedClaims:
unsupportedClaims:
nativeWorkflowComparison:
recoveryAssessment:
applicability:
expiresAt:
invalidationRules:
evidenceRefs:
humanApproval:
```

Status is one of:

```text
PASS
FAIL
UNKNOWN
INVALID_ORACLE
INVALID_EVIDENCE
INFRASTRUCTURE_ERROR
POLICY_BLOCKED
EXPIRED
```

Decision is one of:

```text
APPROVE_WITHIN_ENVELOPE
BLOCK_CHANGE
REQUIRE_MORE_EVIDENCE
NO_DECISION
NATIVE_WORKFLOW_SUFFICIENT
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
```

The status describes technical truth. The decision describes the operational recommendation. They must not be collapsed.

## 04.7 Stable backend interfaces

Use Python protocols or equivalent typed interfaces. Product code must not branch on vendor names throughout the core.

```python
class EvidenceImportBackend(Protocol):
    def identify(self, source: EvidenceSource) -> ImportCapability: ...
    def import_evidence(self, source: EvidenceSource) -> ImportedEvidence: ...

class NativeDiagnosticBackend(Protocol):
    def analyze(self, case: IncidentCase) -> NativeBaseline: ...

class OperatorAlignmentBackend(Protocol):
    def align(self, evidence: EvidenceSet, policy: AlignmentPolicy) -> AlignmentResult: ...

class ScaleEmulationBackend(Protocol):
    def propose(self, case: IncidentCase, budget: ResourceBudget) -> ScaleExperiment: ...
    def verify(self, experiment: ScaleExperiment) -> ScaleFaithfulness: ...

class HardwareDependenceBackend(Protocol):
    def assess(self, executions: ExecutionSet) -> HardwareDependenceResult: ...

class CheckpointStateBackend(Protocol):
    def capture(self, execution: ExecutionContext) -> RecoverySnapshot: ...
    def compare(self, expected: RecoveryContract, observed: RecoverySnapshot) -> RecoveryResult: ...

class EnvironmentMaterializationBackend(Protocol):
    def materialize(self, identity: EnvironmentIdentity) -> MaterializedEnvironment: ...

class RunnerBackend(Protocol):
    def preflight(self, contract: ExperimentContract) -> RunnerPreflight: ...
    def execute(self, contract: ExperimentContract, role: EnvironmentRole) -> ExecutionRecord: ...

class SupportExportBackend(Protocol):
    def export(self, decision: QualificationDecision, policy: ExportPolicy) -> SupportPackage: ...
```

Backend capability reports must include supported versions, required permissions, privacy behavior, validation maturity, and known gaps.

## 04.8 Initial native integration

The first importer should support PyTorch Flight Recorder output and associated environment material.

Expected command:

```bash
traincapsule ingest pytorch-flight-recorder \
  --trace-dir ./fr_trace \
  --environment ./environment.json \
  --workload ./workload-lock.json \
  --out ./case
```

The importer must:

1. validate files and supported schema/version;
2. hash original artifacts before parsing;
3. retain source-relative rank and process-group identity;
4. parse collective type, lifecycle state, tensor metadata, and available call stacks;
5. align only where evidence supports alignment;
6. preserve parse warnings and missing ranks;
7. emit the native finding separately from TrainCapsule-added analysis;
8. never claim that Flight Recorder failed merely because TrainCapsule later adds value.

## 04.9 Eligibility engine

Before experiment construction, run:

```bash
traincapsule preflight ./case
```

The preflight returns one of:

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

Eligibility inputs:

- named decision and deadline;
- baseline/candidate access;
- evidence identity;
- supported pack fit;
- ability to execute locally;
- original and proposed experiment economics;
- privacy and export constraints;
- complete native baseline;
- required human expertise.

The free/open entry tool may stop here. A case should be rejected rather than forced through the paid workflow.

## 04.10 Pack-specific experiment planner

V1 does not include a universal planner. It includes one pack-specific planner for `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1`.

The planner may manipulate only a small registry of legal dimensions, such as:

- selected dataset shard or input trigger while preserving trigger identity;
- world size within a pack-declared range;
- iteration window around the observed lifecycle divergence;
- model component isolation when collective schedule equivalence is established;
- process-group subset when group membership and cross-group dependencies are preserved;
- deterministic fault injection for controlled cases;
- timing budgets only when the mechanism is not timing-sensitive or the sensitivity is explicitly tested.

Forbidden automatic reductions include:

- changing backend and claiming original mechanism preservation;
- removing topology dependence without evidence;
- replacing real data with random data when the trigger may be data-dependent;
- changing precision when numerical or kernel behavior may matter;
- reducing world size when collective schedule or sharding semantics change;
- replacing a failure with an injected exception and claiming reproduction;
- suppressing recovery behavior being evaluated;
- treating a locally passing toy example as a scale-faithful result.

Every proposed step must include a verification plan and a rollback path.

## 04.11 Runner architecture

V1 runner requirements:

- customer-local;
- non-privileged by default;
- isolated container or approved scheduler allocation;
- deny network by default except declared endpoints;
- read-only source and input mounts where possible;
- separate writable artifact directory;
- explicit GPU, CPU, memory, disk, and wall-clock limits;
- process-tree termination;
- environment identity verification immediately before execution;
- artifact hashing immediately after execution;
- no hidden mutation of customer code;
- no automatic retry that hides failure frequency;
- transparent infrastructure-event recording.

Runner phases:

```text
VALIDATE_CONTRACT
→ MATERIALIZE
→ VERIFY_IDENTITY
→ PREFLIGHT_RESOURCES
→ EXECUTE
→ CAPTURE
→ VERIFY_ARTIFACTS
→ CLEAN_UP
→ SIGN_RECORD
```

A runner failure produces `INFRASTRUCTURE_ERROR`, not `FAIL`.

## 04.12 Baseline/candidate comparison

The comparator must require:

- same experiment-contract digest;
- same pack/version;
- same comparison policy;
- declared material environment differences;
- successful identity verification for both;
- sufficient oracle validity;
- no expired faithfulness contract;
- explicit handling of nondeterminism.

The comparator may evaluate:

- trigger reproduced or absent;
- first observed inconsistent boundary;
- collective/lifecycle schedule;
- recovery properties;
- runtime and resource metrics;
- failure frequency under a preregistered sample policy;
- evidence completeness;
- changed operational decision.

It must not infer broad compatibility from one narrow contract.

## 04.13 Recovery Assurance

Recovery Assurance is a collection of property checks, not one boolean.

Example output:

```yaml
properties:
  checkpoint_readable:
    verdict: PASS
  model_state:
    verdict: PASS
    oracle: exact_digest
  optimizer_state:
    verdict: UNKNOWN
    reason: optimizer state was not captured
  rng_continuity:
    verdict: PASS
  sampler_state:
    verdict: FAIL
  data_cursor:
    verdict: UNKNOWN
decisionEffect:
  releaseBlockedBy:
    - sampler_state
  unresolved:
    - optimizer_state
    - data_cursor
```

A global `PASS` is permitted only when every required property passes. Optional or unavailable properties remain visible.

## 04.14 Incident contract registry

V1 registry is local and content-addressed.

Required operations:

```bash
traincapsule contract create ./case
traincapsule contract verify <contract>
traincapsule contract list
traincapsule contract show <contract>
traincapsule contract expire <contract> --reason ...
traincapsule contract requalify <contract> --candidate ...
```

Registry records:

- immutable contract version;
- supersession chain;
- applicability envelope;
- environment drift;
- pack/backend versions;
- human approvals;
- qualification history;
- expiry and revocation events;
- private evidence references;
- export policy.

Do not build a central multi-customer registry in V1.

## 04.15 Local report viewer

The viewer is a local read-only rendering surface. It is not the product's source of truth.

Minimum views:

1. decision summary;
2. native-tool findings;
3. evidence completeness;
4. original versus reduced scope;
5. reduction history and rejected reductions;
6. baseline/candidate differences;
7. recovery property matrix;
8. applicability and expiry;
9. unsupported claims and `UNKNOWN`;
10. raw evidence references and verification commands.

The CLI and machine-readable records must remain complete without the viewer.

## 04.16 Human approval boundary

Create a signed `HumanApprovalRecord` for:

- first external use;
- each new commercially released incident pack;
- each material change to identity, canonical serialization, reduction legality, applicability, recovery semantics, or qualification decision logic;
- security boundary changes;
- customer-facing claims;
- exceptional case-specific override.

Approval fields:

```yaml
schemaVersion:
approvalId:
scope:
candidateCommit:
artifactDigests:
reviewer:
reviewerQualification:
decision:
conditions:
limitations:
expiresAt:
signature:
```

The factory may prepare an approval packet. It may not create or forge approval.

## 04.17 Security architecture

### Threats in V1

- malicious or malformed trace artifacts;
- path traversal and decompression bombs;
- secret leakage from environment/configuration;
- untrusted customer code;
- runner escape;
- cross-case evidence mixing;
- stale or substituted artifacts;
- symlink attacks;
- unsafe support export;
- AI-generated overclaiming;
- corrupted or adversarial checkpoints;
- unauthorized network or filesystem access.

### Required controls

- parse in a low-privilege isolated process;
- size, count, recursion, and decompression limits;
- canonical path validation;
- content-addressed evidence;
- encryption at rest when configured;
- deterministic redaction policy;
- separate case directories and access policies;
- no model access to raw customer secrets by default;
- signed contracts and execution records;
- explicit export allowlist;
- reproducible verifier;
- software bill of materials;
- dependency pinning;
- vulnerability and secret scanning;
- customer-local audit log;
- incident response and revocation procedure.

## 04.18 Observability and supportability

Product telemetry must remain customer-controlled.

Machine events should include:

- case lifecycle transitions;
- importer version and result;
- identity verification;
- eligibility decision;
- planner/reduction decisions;
- runner resource state;
- execution transition and termination reason;
- oracle validity;
- comparison result;
- contract creation/expiry/requalification;
- approval state;
- export action.

No event may contain raw code, data, checkpoints, stack traces, environment secrets, or customer identifiers by default.

A support bundle must be generated through an explicit redaction policy and show exactly what leaves the customer environment.

## 04.19 Product CLI

Initial command surface:

```text
traincapsule doctor
traincapsule case init
traincapsule ingest pytorch-flight-recorder
traincapsule identity workload
traincapsule identity environment
traincapsule preflight
traincapsule native-baseline
traincapsule plan
traincapsule reduction propose
traincapsule reduction verify
traincapsule contract create
traincapsule contract verify
traincapsule run baseline
traincapsule run candidate
traincapsule recovery assess
traincapsule qualify
traincapsule report
traincapsule export support
```

Commands must support `--json`, deterministic exit codes, human-readable diagnostics, and local-only operation.

## 04.20 Exit-code contract

Example:

```text
0  command completed and truth record written
2  invalid CLI use
10 unsupported input/version
11 evidence incomplete
12 identity mismatch
13 policy blocked
14 human approval required
20 qualification PASS
21 qualification FAIL
22 qualification UNKNOWN
23 invalid oracle
24 expired contract
30 infrastructure error
40 security/containment violation
```

Exit code `0` does not mean the case passed. It means the operation completed honestly. Qualification truth uses explicit result codes.

## 04.21 Testing architecture

### Unit tests

- canonical serialization;
- identity stability and drift;
- parsing;
- schema validation;
- status transitions;
- reduction preconditions;
- expiry;
- redaction;
- comparison semantics.

### Contract tests

- each backend;
- each incident pack;
- runner protocol;
- external verifier;
- support export.

### Controlled integration tests

- multi-process DDP;
- omitted collective;
- reordered collective;
- shape mismatch;
- data-dependent branch;
- rank exit;
- delayed rank;
- ordinary infrastructure interruption;
- candidate fixed/unchanged/regressed;
- recovery property pass/fail/unknown.

### Adversarial tests

- missing ranks;
- conflicting clocks;
- corrupted traces;
- stale identity;
- malicious archive;
- symlink escape;
- hidden data dependence;
- invalid scale reduction;
- nondeterministic pass;
- circular oracle;
- false hardware attribution;
- `UNKNOWN` laundering.

### Journey tests

1. install to first preflight;
2. native workflow sufficient;
3. eligible case to local contract;
4. baseline/candidate qualification;
5. recovery-property failure blocks release;
6. expiry and requalification;
7. support export under policy;
8. rollback and upgrade.

### External tests

- real GPU execution;
- real Flight Recorder artifacts;
- customer-local pilot;
- independently operated workflow;
- human trust/security review.

External evidence is not replaceable by a mock.

## 04.22 Performance budgets

Initial internal targets, to be validated rather than marketed:

- importer handles the supported trace corpus without unbounded memory growth;
- identity and report operations remain negligible relative to experiment cost;
- runner overhead is measured and reported;
- evidence storage amplification is bounded and configurable;
- reduced experiment target is at least 5× cheaper than the original execution estimate for a commercially useful case, or the case is marked economically weak;
- qualification setup should decline across same-family cases;
- the third same-family case must not require trust-core redesign.

These are engineering gates, not customer ROI claims.

## 04.23 Packaging and deployment

V1 deliverables:

- signed Python packages or one pinned distribution;
- OCI image for customer-local execution;
- offline installation bundle;
- schema and verifier package;
- reproducible lockfile;
- SBOM;
- upgrade and rollback instructions;
- no required hosted service;
- no telemetry egress by default.

Supported deployment modes:

```text
LOCAL_DEV
CUSTOMER_WORKSTATION
CUSTOMER_VPC
AIR_GAPPED_BUNDLE
```

`PROVIDER_FEDERATED` remains design-only until a partner exists.

## 04.24 Maturity controls

Every pack, backend, runner, importer, and report surface stores:

```yaml
engineeringMaturity:
commercialMaturity:
validationEvidence:
supportedVersions:
limitations:
owner:
lastReviewedAt:
nextReviewAt:
```

Engineering maturity:

```text
DESIGN_ONLY
IMPLEMENTED_EXPERIMENTAL
CONTROLLED_VALIDATED
EXTERNAL_VALIDATED
DEPRECATED
```

Commercial maturity:

```text
NOT_EVALUATED
NATIVE_ADVANTAGE_UNPROVEN
NATIVE_ADVANTAGE_DEMONSTRATED
EXTERNAL_VALUE_DEMONSTRATED
COMMERCIALLY_SUPPORTED
WITHDRAWN
```

The CLI must refuse unsupported commercial claims even when a component exists.

## 04.25 Deferred architecture register

The following may retain interface designs but must not receive implementation priority before evidence gates:

- generalized actor IR;
- universal replay;
- provider exchange protocol;
- hosted orchestration;
- broad dashboard;
- multi-cloud runner marketplace;
- autonomous repair;
- cross-customer learning;
- generic hardware dependence;
- generic numerical divergence pack;
- broad checkpoint pack;
- billing and enterprise administration.

A deferred component can be promoted only by:

1. a paid case need;
2. a repeated same-family need;
3. a direct complete-substitute gap;
4. a named owner and decision;
5. an approved security/trust design.

## 04.26 Migration from the present repository

The migration must not delete the factory.

1. Freeze the current factory baseline and preserve its tests.
2. Create product package directories and product-only CI.
3. Separate `tcfactory` schemas from `schemas/product`.
4. Introduce product domain models without importing `tcfactory.models`.
5. Replace the 124-task dependency chain with a commercial-milestone ledger.
6. Build the native importer and preflight before generic platform layers.
7. Build one controlled case through qualification.
8. Add human approval and product release policy before external use.
9. Use the existing factory only as an engineering assistant behind the new milestone scheduler.
10. Treat broad architecture documents as deferred design, not active backlog.

## 04.27 V1 completion definition

V1 is technically complete only when all of the following are demonstrated:

- clean offline/customer-local install;
- Flight Recorder ingestion;
- identity and evidence lock;
- native baseline;
- evidence-gap and economic eligibility decision;
- one pack-specific planner;
- at least one legal and one rejected reduction;
- baseline/candidate execution;
- named recovery properties;
- qualification result with `UNKNOWN`, expiry, and applicability;
- local contract verification;
- support export policy;
- threat-model tests;
- real GPU controlled case;
- independent operator execution;
- qualified human approval for external use.

V1 is commercially validated only after:

- one paid pilot;
- material advantage over the complete native workflow;
- one paid repeat action;
- customer-confirmed decision value greater than price and retained effort.

Technical completion must never be reported as commercial validation.


<!-- END 04_TECHNICAL_ARCHITECTURE_V3.md -->


<!-- BEGIN 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md -->

# 05 — Trust, Replay, Reduction, Recovery, and Incident Contract Specification V3

## 05.1 Purpose

This specification defines the rules that prevent TrainCapsule from producing a polished but unsupported release decision.

It governs:

- evidence and identity;
- observed boundaries;
- hypotheses and causal language;
- experiment construction;
- reduction legality;
- faithfulness;
- replay and evidence tiers;
- recovery-state assurance;
- baseline/candidate qualification;
- applicability, drift, expiry, and revocation;
- native-workflow comparison;
- commercial truth;
- human approval.

A component that violates this specification may be technically useful, but it is not permitted to produce a supported TrainCapsule decision.

## 05.2 Truth model

TrainCapsule must keep four dimensions separate.

### Technical execution state

```text
PASS
FAIL
UNKNOWN
INVALID_EVIDENCE
INVALID_ORACLE
INFRASTRUCTURE_ERROR
POLICY_BLOCKED
EXPIRED
```

### Epistemic claim class

```text
DIRECTLY_OBSERVED
DERIVED_FROM_DECLARED_RULE
SUPPORTED_BY_CONTROLLED_EXPERIMENT
SUPPORTED_WITHIN_APPLICABILITY_ENVELOPE
HYPOTHESIS
CONFLICTING_EVIDENCE
NOT_OBSERVED
UNKNOWABLE_FROM_AVAILABLE_EVIDENCE
```

### Operational decision

```text
APPROVE_WITHIN_ENVELOPE
BLOCK_CHANGE
REQUIRE_MORE_EVIDENCE
NO_DECISION
NATIVE_WORKFLOW_SUFFICIENT
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
```

### Commercial maturity

```text
NATIVE_ADVANTAGE_UNPROVEN
NATIVE_ADVANTAGE_DEMONSTRATED
EXTERNAL_VALUE_DEMONSTRATED
COMMERCIALLY_SUPPORTED
```

No mapping may automatically convert one dimension into another. In particular:

- technical `PASS` does not prove causality;
- technical `PASS` does not prove customer value;
- a controlled result does not prove production behavior outside its envelope;
- `UNKNOWN` does not mean the change is safe;
- a failed experiment does not necessarily mean the candidate environment is unsafe;
- a native finding does not become a TrainCapsule proprietary result;
- a commercially unsupported pack must not be marketed as supported.

## 05.3 Evidence provenance

Every evidence artifact must be bound to:

- source system and version;
- source location;
- capture time;
- workload identity;
- environment identity;
- rank/process/group where applicable;
- content digest;
- transformation history;
- privacy classification;
- export policy;
- parser version;
- validation status.

Transformations form an append-only chain:

```text
raw artifact
→ validated container
→ parsed record
→ normalized event
→ aligned observation
→ derived finding
→ experiment input
→ qualification result
```

Each edge stores:

- transformation name and version;
- input digests;
- output digest;
- deterministic parameters;
- warnings;
- loss of information;
- operator identity;
- timestamp.

A derived record without a complete provenance chain is `INVALID_EVIDENCE`.

## 05.4 Evidence completeness

Evidence completeness is not a percentage unless the denominator is defined for a particular pack.

For each required evidence subject, record:

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

The pack specifies which subjects are:

- mandatory for eligibility;
- mandatory for a given claim;
- optional;
- substitutable through another source;
- impossible to recover after the incident.

An omitted subject cannot be repaired by model inference. The system may propose how to collect it in a future run.

## 05.5 Identity law

A result is valid only for the exact identities declared in its contract.

### Workload identity

Identity must cover all mechanism-relevant aspects available to the customer, including:

- code revision and dirty patch;
- entrypoint and arguments;
- dependency lock;
- model and distributed structure;
- process-group construction;
- data identity policy;
- checkpoint and resume policy;
- relevant environment variables;
- configuration files.

### Environment identity

Identity must cover:

- OS/kernel;
- container;
- Python and packages;
- PyTorch;
- CUDA runtime and driver;
- NCCL;
- GPU model/count/firmware;
- scheduler/launcher;
- topology class;
- network and storage class;
- materialization recipe.

### Identity strength

```text
FULLY_VERIFIED
PARTIALLY_VERIFIED
CUSTOMER_ATTESTED
UNVERIFIED
CONFLICTING
```

Identity strength must appear in every decision. `UNVERIFIED` or `CONFLICTING` identity cannot yield an unqualified `APPROVE_WITHIN_ENVELOPE`.

### Drift

A contract declares material and immaterial identity fields. Any material drift:

- invalidates cached execution results;
- requires requalification or an approved equivalence rule;
- is recorded in the supersession chain;
- may narrow or expire the contract.

No AI session may silently decide that a changed field is immaterial.

## 05.6 Native baseline law

TrainCapsule must execute or import the best approved native workflow before claiming incremental value.

The native baseline record includes:

- tools and versions;
- commands/configuration;
- artifacts;
- findings;
- limitations;
- time and operator effort;
- decision reached;
- unresolved questions.

The TrainCapsule report must visibly separate:

```text
NATIVE_TOOL_FOUND
TRAINCAPSULE_DERIVED
HUMAN_PROVIDED
EXTERNAL_SYSTEM_PROVIDED
UNKNOWN
```

A capability already supplied by the native workflow may remain useful as an integration, but it does not count as differentiated product value.

## 05.7 Observed boundary

The **first observed inconsistent boundary** is the earliest event or state transition at which available evidence demonstrates a cross-actor or expected-versus-observed inconsistency under the declared alignment policy.

It is not necessarily:

- the root cause;
- the first event in wall-clock time;
- the failing hardware component;
- the source line that introduced the problem;
- the only relevant boundary.

An observed-boundary record must include:

- actors/ranks;
- process group;
- event identities;
- ordering evidence;
- clock/alignment uncertainty;
- expected contract;
- observed mismatch;
- missing predecessor evidence;
- alternate alignments;
- statement class.

Allowed statements:

- “Rank 3 is the first rank in the available aligned trace that lacks the expected collective.”
- “The available evidence first becomes inconsistent before collective X.”
- “This observation is compatible with hypotheses A, B, and C.”

Forbidden without controlled evidence:

- “Rank 3 caused the incident.”
- “The network caused the timeout.”
- “GPU 5 is defective.”
- “This is the root cause.”

## 05.8 Hypothesis discipline

A hypothesis is a falsifiable mechanism proposal, not a narrative.

Each hypothesis requires:

- statement;
- mechanism class;
- observations it explains;
- observations it does not explain;
- discriminating experiment;
- expected outcomes under competing hypotheses;
- resource cost;
- privacy/security impact;
- status.

Hypothesis statuses:

```text
PROPOSED
TESTABLE
REJECTED
SUPPORTED
SUPPORTED_WITH_ALTERNATIVES
NOT_DISCRIMINATED
OUTSIDE_BUDGET
POLICY_BLOCKED
UNKNOWN
```

`SUPPORTED` means the controlled observations match a preregistered prediction and relevant controls. It does not mean universal causality.

The planner must preserve rejected hypotheses and failed experiments. They are operational evidence and prevent repeated dead ends.

## 05.9 Experiment plan requirements

An experiment plan is valid only when it declares:

- decision it is intended to inform;
- hypothesis or contract property;
- original and proposed scope;
- independent and dependent variables;
- controls;
- expected observations;
- falsifier;
- sample/repetition policy;
- nondeterminism policy;
- resource and time budget;
- stop conditions;
- security/privacy policy;
- required identities;
- oracle;
- fallback if inconclusive.

Post-hoc metric selection is forbidden. Amendments must retain old/new plans and reasons.

## 05.10 Reduction law

Reduction seeks the lowest-cost experiment that preserves the mechanism or contract property needed for the decision.

### Registered operators

Every reduction step uses a versioned operator from an incident pack. An operator defines:

- preconditions;
- fields it may modify;
- properties it claims to preserve;
- properties it knowingly relaxes;
- verification method;
- known counterexamples;
- minimum evidence;
- invalidation conditions.

### Legal reduction states

```text
PROPOSED
PRECONDITIONS_MET
VERIFIED_FOR_PROPERTY
REJECTED_COUNTEREXAMPLE
REJECTED_IDENTITY_DRIFT
REJECTED_COST
REQUIRES_HUMAN_APPROVAL
UNKNOWN
```

### Monotonic truth rule

A sequence of reductions may narrow the supported claim but may not strengthen it without new evidence.

For example:

```text
original incident claim:
  behavior under 32 GPUs, topology T, dataset D

reduced experiment:
  behavior under 8 GPUs, topology T', shard D1

valid supported claim:
  reduced experiment preserves declared collective schedule and trigger under tested controls

invalid unsupported claim:
  candidate is safe for all 32-GPU executions
```

### Negative controls

At least one reduction counterexample must be attempted for a commercially supported reduction class. The counterexample should intentionally violate a required property and demonstrate that the verifier rejects it.

### Economic limit

A technically faithful experiment that remains near the original run's cost must be marked `TECHNICALLY_VALID_BUT_NOT_ECONOMIC`. The system must not call it a successful minimum faithful experiment merely because it ran.

## 05.11 Faithfulness dimensions

Faithfulness is multi-dimensional.

```text
CONTROL_FLOW
COLLECTIVE_SCHEDULE
PROCESS_GROUP_MEMBERSHIP
DATA_TRIGGER
MODEL_STRUCTURE
SHARDING
PRECISION
KERNEL_PATH
TOPOLOGY
SCALE
TIMING
CHECKPOINT_STATE
RECOVERY_SEQUENCE
PERFORMANCE_REGIME
```

Each dimension is:

```text
PRESERVED
BOUNDED_EQUIVALENCE
RELAXED
NOT_RELEVANT
NOT_ESTABLISHED
UNKNOWN
```

The incident pack identifies the minimum required dimensions for each mechanism/decision class.

A global faithfulness statement is prohibited unless all required dimensions are established.

## 05.12 Replay and evidence tiers

TrainCapsule must not use “replay” as one vague capability.

### Tier E0 — Evidence-only reconstruction

No executable replay. The system aligns and analyzes captured evidence.

Suitable for:

- evidence completeness;
- observed boundary;
- support export;
- planning a future experiment.

Not suitable for:

- claiming reproduction;
- validating a fix.

### Tier E1 — Structural execution

The experiment recreates relevant control-flow, collective, or lifecycle structure but not exact data/numerical state.

Suitable for:

- selected protocol/lifecycle failures when data and numerical path are not material.

### Tier E2 — Source/substitute execution

The experiment uses a declared substitute for sensitive or unavailable input and verifies selected preserved properties.

Suitable only when substitute validity is separately established.

### Tier E3 — Deterministic bounded replay

The experiment re-executes a bounded region under captured state with declared determinism.

Exactness applies only to the captured boundary and supported environment.

### Tier E4 — Statistical reproduction

The mechanism is demonstrated through a preregistered frequency/distribution test.

Required for inherently stochastic failures where deterministic reproduction is unavailable.

### Tier E5 — Scale-faithful execution

The experiment establishes that reduced-scale execution preserves the decision-relevant scale/topology property through an approved scale-emulation or controlled comparison method.

This is not granted by simply using multiple GPUs.

Every result displays its tier and prohibited interpretations.

## 05.13 Oracle specification

An oracle determines whether the experiment or recovery property satisfies its contract.

Oracle classes:

```text
EXACT_REFERENCE
INVARIANT_MODEL
DIFFERENTIAL_NATIVE_SYSTEM
CONTROLLED_GOLDEN_CASE
STATISTICAL_TEST
HUMAN_REVIEWED_PROPERTY
CUSTOMER_DEFINED_ASSERTION
```

An oracle must be:

- independently derived from the implementation under test where practical;
- versioned;
- identity-bound;
- capable of failing;
- exercised with positive and negative controls;
- explicit about tolerances;
- free from circular dependence on the result being certified.

`INVALID_ORACLE` is a terminal technical truth state for that claim. It cannot be repaired by prose.

Critical modules requiring an independent oracle:

- canonical serialization and identity;
- observed-boundary alignment;
- reduction legality and faithfulness;
- applicability/drift;
- recovery-state assurance;
- qualification decision semantics.

## 05.14 Recovery Assurance specification

Recovery Assurance evaluates named properties after a restart, resume, failover, or recovery action.

### Property contract

```yaml
propertyId:
name:
required:
preRecoveryReference:
postRecoveryObservation:
oracle:
tolerance:
observationWindow:
failureEffect:
unknownEffect:
privacyPolicy:
```

### Result

```text
PASS
FAIL
UNKNOWN
INVALID_ORACLE
INVALID_REFERENCE
NOT_APPLICABLE
```

### Aggregation

- Any required `FAIL` blocks approval unless an authorized human policy explicitly defines another outcome.
- Any required `UNKNOWN` prevents unconditional approval.
- Optional properties remain visible and cannot be deleted to produce green status.
- Aggregate status must preserve the property matrix.
- A checkpoint checksum is not a universal recovery oracle.
- Short-run trajectory agreement is not long-horizon model-quality certification.
- Throughput after recovery must use a declared warmup and observation window.

### Reference acquisition

References may come from:

- pre-failure state;
- healthy replica;
- persisted checkpoint;
- controlled baseline run;
- customer-approved invariant.

Reference provenance and identity are mandatory.

## 05.15 Baseline/candidate qualification

Qualification compares one frozen contract across baseline and candidate environments.

### Valid comparison

A comparison requires:

- contract digest equality;
- valid workload identity;
- valid materialization identities;
- current pack and oracle versions;
- valid faithfulness contract;
- same required observations;
- completed native baseline;
- bounded nondeterminism;
- no unresolved policy violations.

### Decision matrix

| Baseline | Candidate | Interpretation |
|---|---|---|
| Trigger reproduces | Trigger absent and required recovery properties pass | potential approval within envelope |
| Trigger reproduces | Trigger reproduces | candidate did not resolve contract |
| Trigger absent | Trigger appears | candidate regression |
| Baseline inconclusive | Candidate conclusive | no direct comparative approval; more evidence |
| Baseline valid | Candidate infrastructure error | no decision |
| Either oracle invalid | any | no decision |
| Native workflow already yields same bounded decision | same | `NATIVE_WORKFLOW_SUFFICIENT` |

### Required report content

- exact material differences;
- baseline and candidate execution identities;
- native result;
- experiment tier;
- faithfulness dimensions;
- recovery matrix;
- pass/fail/unknown observations;
- supported and unsupported claims;
- decision and deadline;
- applicability and expiry;
- rerun command;
- human approval where required.

## 05.16 Applicability envelope

Every positive decision has an applicability envelope containing:

- workload identity pattern;
- environment baseline and candidate;
- pack/version;
- scale/topology class;
- data identity strength;
- precision/kernel conditions;
- scheduler/launcher;
- recovery policy;
- observation window;
- known excluded mechanisms;
- expiry;
- invalidation rules.

The envelope may be exact or pattern-based. Pattern-based equivalence requires an approved rule and evidence.

No report may omit the envelope from the first page.

## 05.17 Expiry, revocation, and requalification

A contract expires when:

- an explicit date is reached;
- a material identity field changes;
- a pack/backend/oracle security issue is discovered;
- a known counterexample invalidates faithfulness;
- the native workflow changes materially;
- customer policy changes;
- required evidence becomes unavailable;
- human approval expires.

Revocation is append-only and records:

- reason;
- affected contracts;
- effective time;
- authority;
- remediation;
- whether prior decisions are withdrawn or merely no longer current.

Requalification creates a new decision; it never overwrites history.

## 05.18 Native-equivalence and complete-substitute test

A commercially supported feature must be compared against:

```text
framework-native diagnostics
+ cloud/platform tooling
+ hardware/vendor support
+ customer scripts
+ approved engineering agents
+ reasonable specialist effort
```

The benchmark asks:

1. Did TrainCapsule reveal a fact the complete substitute did not?
2. Did it materially reduce execution or operator cost?
3. Did it change the release, migration, recovery, or escalation decision?
4. Could the customer retain the result as a reusable contract?
5. Would the customer pay for the incremental outcome?
6. Did TrainCapsule merely reformat native findings?

Terminal value states:

```text
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
INCREMENTAL_DECISION_VALUE_DEMONSTRATED
EXTERNAL_VALUE_REQUIRED
```

Only the final two justify further commercial evaluation. Only attributable external evidence can establish external value.

## 05.19 Commercial truth specification

The following are external facts:

- customer demand;
- willingness to pay;
- paid pilot;
- repeat use;
- decision value;
- time/cost saved in a customer environment;
- independent operator success;
- provider acceptance;
- upstream acceptance;
- renewal;
- revenue;
- acquisition interest.

An AI agent, synthetic fixture, founder-authored note, or repository document cannot certify these facts.

External evidence must be:

- attributable;
- dated;
- scope-bound;
- stored outside agent-writable product state or signed by an authorized issuer;
- privacy-reviewed;
- linked to the exact offer and outcome;
- revocable/correctable.

Synthetic customer records are permitted only for tests and must be visibly labeled `SYNTHETIC_TEST_ONLY`.

## 05.20 Human authority

No external or commercial release may be approved solely by AI sessions, even when sessions use different models, prompts, worktrees, hidden tests, or roles.

Before first external use and before each new commercial incident pack, a qualified human reviewer must approve:

- trust model;
- declared invariants;
- identity and canonicalization;
- experiment semantics;
- legal reductions;
- faithfulness claims;
- recovery property semantics;
- qualification decision mapping;
- security boundary;
- customer-facing claims.

### Qualification of reviewer

The approval packet records why the reviewer is qualified, such as:

- production distributed-training experience;
- PyTorch/c10d/NCCL expertise;
- checkpoint/recovery systems expertise;
- security/private deployment expertise;
- formal verification or testing expertise for a bounded subsystem.

One person need not cover all domains. Multiple scoped approvals are preferred.

## 05.21 AI role boundaries

AI may:

- propose designs;
- implement code;
- generate controlled cases;
- run tests;
- find counterexamples;
- compare documents;
- prepare approval packets;
- draft claims with evidence references.

AI may not:

- invent external evidence;
- approve its own trust model for commercial use;
- forge a reviewer;
- reinterpret failed evidence as passing;
- silently weaken criteria;
- decide that policy-restricted data may be exported;
- claim causality beyond evidence;
- create a customer signature;
- convert `UNKNOWN` into approval.

Separate AI sessions provide process separation, not epistemic independence. Critical oracles should differ in implementation method or authority, not merely prompt wording.

## 05.22 Claim language policy

### Permitted examples

- “Within the declared 8-GPU topology and captured trigger conditions, the candidate did not reproduce the baseline lifecycle mismatch across 20 preregistered trials.”
- “Sampler continuity failed after recovery; optimizer-state continuity could not be evaluated from available evidence.”
- “PyTorch Flight Recorder identified the missing collective. TrainCapsule added a reduced trigger-preserving experiment and ran it against the candidate stack.”
- “The result applies only to the signed contract and expires when material environment identity changes.”

### Prohibited examples without broader evidence

- “The upgrade is safe.”
- “TrainCapsule found the root cause.”
- “The GPU was bad.”
- “The model resumed correctly.”
- “The issue cannot recur.”
- “TrainCapsule is more accurate than native tools.”
- “The customer saved $X.”
- “This works on all PyTorch/NCCL workloads.”

## 05.23 Security and privacy truth

A customer-local claim requires demonstration that:

- raw private material remains local;
- the product does not silently transmit telemetry;
- support export is explicit;
- redaction is deterministic and inspectable;
- runner network access is denied or allowlisted;
- evidence from different customers cannot mix;
- AI tools receive only permitted context;
- secrets are scrubbed;
- logs are classified and retained according to policy.

A design diagram alone is not evidence of containment.

## 05.24 Dispute and correction process

TrainCapsule must support technical disputes.

A dispute record contains:

- claim challenged;
- challenger;
- evidence;
- affected contract/decision;
- provisional status;
- investigation;
- corrected result;
- notification scope;
- contract revocation or supersession.

Until resolved, material disputed claims become `CONFLICTING_EVIDENCE` or `UNKNOWN`, not silently retained as pass.

## 05.25 Pack release requirements

An incident pack advances to `COMMERCIALLY_SUPPORTED` only when:

1. schemas and semantics are versioned;
2. legal reductions are enumerated;
3. positive, negative, and boundary controlled cases pass;
4. independent oracle exists;
5. real supported-environment execution passes;
6. native baseline is complete;
7. incremental decision value is demonstrated in at least one external case;
8. known limitations are documented;
9. security review passes;
10. qualified human approval is signed;
11. support and rollback procedure exists;
12. expiry/invalidation behavior is tested.

A reference pack may be implemented and controlled-validated without commercial release.

## 05.26 Initial pack: pre-collective lifecycle

The pack may support cases where an actor fails to satisfy a declared collective/lifecycle contract due to a bounded upstream event.

Mechanism candidates:

- omitted collective;
- reordered collective;
- incompatible collective/tensor metadata;
- data-dependent branch;
- data-loader/checkpoint path preventing progress;
- process exit;
- invalid process-group membership transition;
- bounded kernel/runtime lifecycle condition separable from ordinary delay.

Required native baseline:

- Flight Recorder or approved equivalent;
- collective lifecycle metadata;
- call-stack evidence when available;
- rank/process-group inventory;
- environment and workload identity;
- ordinary infrastructure evidence where available.

Commercial success requires more than identifying the mismatch. It requires a lower-cost faithful experiment, tested correction or guard, and a release decision against a real candidate change.

## 05.27 Checkpoint/resume reference pack policy

`CHECKPOINT_RESUME_STATE_CONSISTENCY_V1` is an engineering reference pack until evidence proves an external gap.

It must not be marketed merely because it checks:

- global step;
- model checksum;
- basic RNG restoration;
- checkpoint readability.

These are increasingly available in native recovery systems.

A commercial release requires at least one customer-important property that the complete native workflow does not establish and that changes a real decision, such as:

- customer-specific data cursor;
- replay/skip semantics;
- custom sampler state;
- application-specific shard ownership;
- cross-cloud recovery;
- private optimizer/scheduler semantics;
- short-run trajectory;
- performance behavior after recovery.

## 05.28 Verification artifacts

Each completed qualification stores:

```text
case.json
workload-identity.json
baseline-environment.json
candidate-environment.json
evidence-manifest.json
native-baseline.json
evidence-completeness.json
hypothesis-ledger.json
experiment-plan.json
reduction-history.json
faithfulness-contract.json
recovery-contract.json
experiment-contract.json
baseline-execution.json
candidate-execution.json
qualification-decision.json
human-approval.json
report.html
verification.txt
```

All machine records are schema-validated, content-addressed, and linked by digest.

## 05.29 Minimum external verifier

The external verifier must be able to operate without the planner or AI agent.

It verifies:

- schema versions;
- canonical hashes;
- signatures;
- identity consistency;
- provenance graph;
- required evidence presence;
- faithfulness status;
- oracle validity;
- baseline/candidate contract equality;
- recovery aggregation;
- applicability and expiry;
- human approval;
- report consistency with machine records.

It does not independently prove that the original evidence was truthful unless the evidence source supplies that assurance.

## 05.30 Trust stop conditions

Stop and return no supported decision when:

- evidence identity is materially unbound;
- required evidence is unavailable;
- the native baseline is incomplete;
- the oracle is circular or invalid;
- reduction faithfulness is not established;
- baseline/candidate contracts differ materially;
- execution escaped containment;
- human approval is required and absent;
- contract is expired;
- evidence conflicts cannot be resolved within budget;
- customer asks for unsupported universal or hardware-certified claims;
- economic value of further experimentation is below the declared threshold.

Truthful refusal is part of the product.


<!-- END 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md -->


<!-- BEGIN 06_COMMERCIAL_MODEL_AND_GTM_V3.md -->

# 06 — Commercial Model, Go-to-Market, and Validation Plan V3

## 06.1 Commercial objective

TrainCapsule is not successful when the repository is large, the controlled demo is impressive, or every planned component exists.

The business objective is:

> Repeatedly sell a bounded release, migration, or recovery decision that the customer's complete native workflow cannot produce as cheaply, credibly, or privately.

The first business may be expert-led. The repeatable product is the local qualification contract and its re-execution across changes.

## 06.2 Initial positioning

### Category

**Failure-derived change qualification for private distributed-training workloads.**

### Primary message

> Turn your worst distributed-training failure into a customer-local release gate for your next PyTorch, CUDA, NCCL, driver, checkpoint, GPU, topology, scheduler, or cloud change.

### Supporting message

TrainCapsule starts with the tools the customer already trusts. It imports native evidence, identifies what remains unresolved, constructs a bounded lower-cost experiment where possible, evaluates named recovery-state properties, and compares the current and proposed environments under an expiring contract.

### Do not lead with

- AI root-cause analysis;
- GPU observability;
- deterministic replay;
- black-box recording;
- NCCL debugging;
- automatic recovery;
- vendor-neutral dashboard;
- generic reliability platform.

Those positions are crowded, easily bundled, or too broad.

## 06.3 Initial buyer and user

### Economic buyer

A director, head, or lead responsible for:

- ML platform;
- training infrastructure;
- research infrastructure;
- GPU platform/reliability;
- model systems;
- infrastructure release or migration;
- managed training service operations.

### Primary user

A senior infrastructure, distributed-systems, ML systems, performance, or reliability engineer who owns the incident evidence and candidate change.

### Supporting users

- training framework engineer;
- checkpoint/recovery owner;
- SRE;
- provider support engineer;
- security reviewer;
- research engineer whose workload is blocked.

## 06.4 Ideal customer profile

The best first customer is a middle-sized AI organization that:

- operates recurring multi-node PyTorch/NCCL workloads;
- has a small infrastructure team supporting multiple model/research teams;
- has at least one expensive active or historical incident;
- has a real stack, hardware, topology, checkpoint, scheduler, or cloud change planned within 90 days;
- controls its images, launch process, evidence, and experimental capacity;
- already uses native diagnostics;
- cannot freely send code, data, checkpoints, or full topology to a provider;
- has a named decision owner;
- can fund a bounded technical pilot;
- has a plausible second qualification event.

### Strong entry situations

- delayed PyTorch/CUDA/NCCL upgrade because of a prior failure;
- GPU or cloud migration with unresolved workload-specific risk;
- resumed job whose application-specific state is not fully trusted;
- provider/workload disagreement that native tools do not close;
- repeated expensive reproduction of a private failure;
- release blocked because full-scale reproduction is too expensive;
- cross-provider decision where provider-owned tools cannot see the complete workload.

### Poor first customers

- frontier labs with mature internal diagnostic systems;
- hyperscalers;
- tiny fine-tuning teams with low incident economics;
- teams without access to evidence or execution;
- teams seeking a generic monitoring dashboard;
- customers demanding guaranteed root cause or hardware certification;
- customers whose accepted solution is simply restart/retry;
- customers with no actual upcoming decision.

## 06.5 Account qualification score

Score each account from 0–2 on each dimension.

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Incident cost | minor | material inconvenience | major GPU/delay/engineering cost |
| Upcoming change | none | possible | named within 90 days |
| Evidence access | poor | partial | strong |
| Experiment authority | none | constrained | customer-local authority |
| Native gap | native sufficient | uncertain | clear unresolved decision |
| Privacy need | low | moderate | private/local is essential |
| Repeat trigger | one-off | possible | recurring releases/migrations |
| Budget owner | absent | indirect | named and engaged |
| Second-use path | none | hypothetical | dated event/workload |
| Delivery fit | bespoke | mixed | within supported envelope |

Minimum pilot candidate:

- no zero in evidence access, experiment authority, or budget owner;
- score at least 14/20;
- one named incident;
- one named candidate change;
- one named decision;
- willingness to run a paid preflight or pilot.

## 06.6 Offer ladder

### Offer 1 — Paid Qualification Preflight

Purpose: decide whether a case is eligible and economically worth pursuing.

Deliverables:

- incident and decision intake;
- native-workflow baseline;
- evidence completeness and identity report;
- supported-pack fit;
- initial experiment and cost hypothesis;
- security/deployment plan;
- go/no-go recommendation;
- fixed pilot scope if eligible.

Internal pricing hypothesis:

```text
CAD/USD equivalent of $15,000–$25,000
```

This is unvalidated and must not be presented as a market fact.

Duration is not promised as a fixed universal number. Scope is bounded by evidence volume and access.

### Offer 2 — Incident-to-Change Qualification Pilot

Required inputs:

```text
one active or reconstructable incident
+ one planned change within 90 days
+ one named release or migration decision
+ one baseline environment
+ one candidate environment
+ customer-local experiment authority
```

Deliverables:

1. native baseline;
2. identity/evidence lock;
3. evidence-gap report;
4. pack-specific experiment;
5. reduction and faithfulness record;
6. baseline/candidate execution;
7. named Recovery Assurance properties;
8. bounded qualification decision;
9. expiring local incident contract;
10. second execution or dated re-execution event included in the engagement;
11. limitations and unsupported claims;
12. customer handoff and independent runbook.

Internal pricing hypothesis:

```text
$40,000–$75,000
```

### Offer 3 — Additional Qualification Event

Run an existing approved contract against another change.

Internal pricing hypothesis:

```text
$20,000–$50,000
```

The price should decline relative to the first incident while gross margin improves.

### Offer 4 — Protected Workload Agreement

For customers with repeated changes and several critical contracts.

Potential components:

- maintained local contract registry;
- scheduled requalification;
- pack/backend updates;
- private references;
- support and incident intake;
- annual security and trust review;
- bounded new contract allowance.

Internal annual hypothesis:

```text
$100,000–$200,000
```

Do not offer this until at least one customer has paid for a second action.

### Offer 5 — Provider or Platform Integration

Only after customer evidence shows recurring provider-side value.

Potential components:

- local/federated runner;
- support package integration;
- incident-contract handoff;
- workload qualification during migrations;
- provider-specific evidence adapter.

Internal hypothesis:

```text
$250,000+ project or strategic agreement
```

This is not part of the initial operating plan.

## 06.7 Initial engagement contract

The first serious contract must include the second use, not merely ask whether a second use might occur.

Example structure:

```text
Phase A: qualification preflight
Phase B: incident-derived contract construction
Phase C: baseline/candidate decision
Phase D: one scheduled requalification or second candidate execution
```

This directly tests whether the product creates repeat behavior.

The contract must state:

- customer-owned decision;
- required access;
- supported claims;
- unsupported claims;
- no universal safety/root-cause guarantee;
- customer-local data boundary;
- experiment budget;
- stop conditions;
- human-review responsibility;
- external evidence and case-study permissions;
- correction/revocation process.

## 06.8 Productized expert service

The first version should be delivered as:

> Expert-led incident-to-change qualification, powered by TrainCapsule.

This is acceptable because real incidents require judgment and access. It becomes a product only when each engagement improves reusable software, packs, runbooks, or evidence policy.

Track for each case:

- total delivery hours;
- founder hours;
- specialist hours;
- setup time;
- experiment cost;
- repeated versus bespoke steps;
- code changed;
- trust-core changes;
- customer-retained work;
- second-use setup time;
- gross margin;
- decision value.

### Productization test

By the third same-family case:

- no trust-core rewrite;
- no new identity semantics;
- no case-specific result-state semantics;
- pack extension is bounded;
- another qualified operator can run the workflow;
- setup and interpretation effort decline;
- the result remains independently verifiable.

Failure means the wedge is consulting-heavy and must be narrowed, redesigned, or stopped.

## 06.9 Open-source and free entry surface

Open or free tooling may:

- import PyTorch Flight Recorder evidence;
- validate environment/workload identity;
- report evidence gaps;
- display native findings;
- classify eligibility;
- verify a signed local contract;
- reproduce public controlled cases.

The paid product retains:

- private experiment design;
- legal reduction and faithfulness process;
- customer-local baseline/candidate execution;
- private references;
- Recovery Assurance;
- maintained qualification;
- support/export integration;
- expert interpretation and approval coordination.

The open component should create trust and qualified leads, not give away a one-time report while leaving no recurring product.

## 06.10 Complete-substitute benchmark

For every pilot and major feature, compare against:

```text
PyTorch/native framework tools
+ cloud/platform tooling
+ hardware/vendor support
+ customer scripts
+ approved coding/operations agents
+ reasonable senior-engineer effort
```

Required benchmark fields:

- native outcome;
- native operator time;
- native execution cost;
- unresolved decision;
- TrainCapsule incremental outcome;
- TrainCapsule retained effort;
- changed decision;
- reusable contract value;
- customer willingness to pay;
- limitations.

### Commercially weak outcomes

```text
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
```

These are successful learning outcomes, not product successes.

### Commercially promising outcome

```text
INCREMENTAL_DECISION_VALUE_DEMONSTRATED
```

It must be supported by a real operational decision and attributable customer confirmation.

## 06.11 Discovery program

Market discovery runs from day one in parallel with engineering.

### Initial evidence targets

```text
30 named accounts
15 detailed operator conversations
5 real incident timelines
3 organizations with a planned change
2 credible pilot candidates
1 genuine trace or historical evidence archive
```

These are activity/evidence targets, not proof of demand.

### Conversation requirements

A qualifying conversation must discuss a specific incident or change, including:

- workload and scale class;
- what happened;
- native tools used;
- evidence available;
- time and GPU cost;
- operator effort;
- decision delayed or made;
- residual uncertainty;
- privacy/access constraints;
- planned changes;
- budget ownership;
- accepted alternatives;
- whether a second use exists.

Generic “interesting idea” feedback does not count.

### Interview questions

1. Describe the last distributed-training incident that materially delayed work.
2. What was the first operational decision you needed to make?
3. Which tools and people were involved?
4. What remained unknown?
5. Did you reproduce it? At what cost?
6. Did the result become a regression or release check?
7. What stack or infrastructure changes are planned?
8. What prevents you from using the historical incident as a release gate?
9. What data cannot leave your environment?
10. Who owns the decision and budget?
11. What would make you pay for a preflight?
12. Under what condition would you pay for a second execution?
13. What would make the complete native workflow sufficient?

Do not pitch for most of the conversation. Collect concrete facts.

## 06.12 Reachable-account map

The account map should prioritize organizations reachable through:

- founder network;
- university/research contacts;
- open-source maintainers;
- Toronto/Canadian AI ecosystem;
- cloud/GPU infrastructure communities;
- PyTorch/NCCL issue participants;
- training-platform vendors;
- ML infrastructure events;
- technical advisers.

For each account record:

```yaml
account:
segment:
relationshipPath:
relevantWorkload:
knownIncident:
plannedChange:
decisionOwner:
technicalChampion:
budgetOwner:
nativeStack:
privacyConstraint:
qualificationScore:
nextEvidenceAction:
status:
```

Automated scraping and generic cold-email volume are not the primary strategy. High-context technical outreach is.

## 06.13 Design partner structure

A design partner must provide more than enthusiasm.

Minimum:

- real incident or controlled customer case;
- real upcoming change;
- execution access;
- named operator;
- scheduled technical sessions;
- permission to retain anonymized process learnings;
- willingness to evaluate price;
- second-use date;
- honest native baseline.

Preferred:

- paid engagement;
- public or sanitized technical case;
- adviser access;
- referral to another qualified account.

A free design partner may be useful for access, but it does not establish willingness to pay.

## 06.14 Sales sequence

```text
technical introduction
→ incident/change qualification
→ paid preflight
→ security/access plan
→ fixed-scope pilot
→ bounded release decision
→ second execution
→ protected workload agreement
```

### Initial outreach message

Lead with the operational decision, not architecture.

Example:

> We are building a customer-local way to turn a costly distributed-training failure into a release test for an upcoming PyTorch, CUDA, NCCL, GPU, checkpoint, topology, or cloud change. It starts from the native evidence you already use and is intended for cases where reproducing the full workload is too expensive or private evidence cannot leave your environment. I am looking for infrastructure teams with one real historical incident and one upcoming change to compare the workflow against what they already do.

Avoid acquisition, AI-factory, and “revolutionary” language.

## 06.15 Proof hierarchy

```text
plan
< controlled fixture
< local multi-process case
< real multi-GPU controlled case
< real incident archive
< independent operator
< paid pilot
< changed customer decision
< paid second action
< annual commitment
< multi-customer repeat
```

Only evidence at or above the relevant level may support a claim.

## 06.16 Validation gates

### Gate C0 — Problem access

Required:

- 15 detailed conversations;
- 5 incident timelines;
- one real evidence archive;
- at least three named upcoming changes.

Decision:

- continue current wedge;
- narrow;
- replace;
- stop.

### Gate C1 — Native gap

Required:

- two cases where the complete native workflow leaves a material decision unresolved;
- one controlled head-to-head demonstration;
- exact statement of incremental value.

### Gate C2 — Paid pilot

Required:

- signed paid preflight or pilot;
- execution and evidence access;
- named decision and deadline;
- included second use.

### Gate C3 — External value

Required:

- TrainCapsule changes or materially strengthens a real decision;
- customer confirms value exceeds price and retained effort;
- limitations accepted;
- native comparison recorded.

### Gate C4 — Repeat

Required:

- same customer pays for a second action;
- no trust-core rewrite;
- setup effort declines.

### Gate C5 — Productization

Required:

- third same-family case;
- independent operator;
- repeatable deployment and runbook;
- improving delivery margin;
- commercially supported pack approval.

### Gate C6 — Annual product

Required:

- at least two customers with repeated qualification;
- one annual or multi-event commitment;
- support/security process;
- founder dependence declining.

## 06.17 Stop and pivot rules

Stop or replace the wedge when any of the following is repeatedly observed:

- native tools produce the same release decision;
- customers accept restart and residual uncertainty;
- nobody pays for the second execution;
- every case requires a new trust model;
- reduced experiment costs nearly as much as the original;
- evidence or execution access is consistently unavailable;
- deployment/security burden exceeds decision value;
- the decision owner lacks budget;
- the historical incident does not matter to future changes;
- the pack produces reports but not decisions;
- the product is useful only as bespoke founder consulting.

The factory is not allowed to respond to these signals by automatically adding features.

## 06.18 Pricing experiments

Maintain a ledger for every price discussion.

Fields:

```yaml
offer:
account:
incidentClass:
decision:
quotedPrice:
scope:
response:
objection:
alternativeBudget:
buyer:
date:
nextStep:
evidenceStrength:
```

Test:

- paid versus free preflight;
- fixed fee versus milestone fee;
- pilot including second execution;
- annual contract after repeat;
- price tied to protected workload rather than seats;
- customer-local deployment fee;
- support response levels only when demanded.

Do not discount in exchange for vague future access. Exchange discounts for concrete evidence, public case rights, or second-use commitment.

## 06.19 Internal revenue hypothesis

A falsifiable $1 million annual model:

```text
6 annual customers × $125,000 = $750,000
5 paid pilots × $50,000       = $250,000
                                      ----
                                $1,000,000
```

This is an internal planning hypothesis, not a forecast.

Example first-year funnel hypothesis:

```text
60 named accounts
→ 25 qualified conversations
→ 10 real evidence reviews
→ 5 paid assessments/pilots
→ 3 material outcomes
→ 2 second paid actions
→ 1–2 annual agreements
```

Update with actual conversion data.

## 06.20 Unit economics

Track per engagement:

```text
revenue
- external GPU/compute cost
- specialist review
- security/deployment work
- support
- travel/procurement
- founder delivery allocation
= contribution margin
```

Also track:

- hours to preflight;
- hours to first valid experiment;
- hours to decision;
- customer-retained effort;
- second-execution effort;
- pack maintenance;
- support incidents;
- refund/credit risk.

Do not treat AI subscription cost as the only cost. Customer access, security, trust, GPU execution, expert review, and delivery are the expensive constraints.

## 06.21 Commercial data model

Create repository templates, but store private customer records outside the public/product repository.

Required ledgers:

```text
REACHABLE_ACCOUNT_MAP
DISCOVERY_INTERVIEW_LEDGER
INCIDENT_EVIDENCE_LEDGER
PILOT_PIPELINE
PRICING_EXPERIMENT_LEDGER
NATIVE_SUBSTITUTE_BENCHMARK_LEDGER
CUSTOMER_VALUE_RECEIPT_LEDGER
REPEAT_USE_LEDGER
WEDGE_DECISION_LEDGER
```

The AI factory may summarize sanitized entries. It may not fabricate or independently sign them.

## 06.22 Case-study strategy

The first public case should be a transparent head-to-head.

Structure:

1. original incident and decision;
2. native tools and what they found;
3. what remained unresolved;
4. evidence gaps;
5. rejected hypotheses;
6. legal reductions attempted;
7. reduction counterexamples;
8. baseline result;
9. candidate result;
10. Recovery Assurance;
11. bounded decision;
12. cost/resource comparison;
13. limitations;
14. what did not work.

A controlled case must be labeled controlled. A customer case requires permission and privacy review.

## 06.23 Competitive strategy

### Against native framework tools

Integrate and credit them. Win only on the remaining decision workflow.

### Against cloud/platform bundles

Target private, cross-provider, workload-specific, or migration decisions where provider tooling lacks complete authority or neutrality.

### Against diagnosis/remediation vendors

Do not compete on generic AI diagnosis. Emphasize incident-derived, expiring qualification against future change.

### Against deterministic replay systems

Do not promise universal replay. Emphasize lower-cost faithful experiment search, applicability, recovery properties, and release decision.

### Against internal scripts plus agents

Win through:

- signed identities;
- pack-specific legal reductions;
- explicit faithfulness;
- reusable local contracts;
- property-level recovery assurance;
- supportable and independently verifiable operation;
- maintained drift/expiry;
- trust and correction history.

If internal scripts produce the same decision with acceptable cost, classify the account as native/internal sufficient.

## 06.24 Trust as a sales asset

TrainCapsule should earn trust through:

- visible native findings;
- explicit unsupported claims;
- `UNKNOWN`;
- customer-local operation;
- independent verifier;
- human pack approval;
- correction/revocation;
- negative cases;
- no forced data export;
- no AI-only release authority.

Do not sell “AI magic.” Sell a disciplined decision process.

## 06.25 Procurement and security package

Before the first pilot, prepare:

- architecture and data-flow diagram;
- threat model;
- local deployment guide;
- data classification;
- network behavior;
- SBOM;
- vulnerability handling;
- incident response;
- retention/deletion policy;
- subprocess/GPU access model;
- AI usage disclosure;
- human review policy;
- support export policy;
- contract and result schemas;
- limitations.

Do not build broad enterprise RBAC before a customer requests it. Provide a clear local boundary first.

## 06.26 Team plan

Before external trust-critical use, secure:

- a distributed-training adviser/reviewer;
- a security/private-deployment reviewer;
- access to real GPU environments;
- an operator who can independently execute the workflow.

Potential later hires/cofounders:

- distributed training/PyTorch/NCCL;
- field or forward-deployed engineer;
- security/platform engineer;
- product/sales operator for AI infrastructure.

AI-generated implementation does not replace domain credibility or customer trust.

## 06.27 Founder operating cadence

Weekly:

- technical build progress;
- qualified conversations;
- incident evidence acquired;
- native/competitor changes;
- pilot pipeline;
- wedge stop signals;
- founder learning/defense.

Monthly:

- complete-substitute benchmark update;
- pack maturity review;
- pricing evidence;
- productization metrics;
- `KEEP`, `INTEGRATE`, `UPSTREAM`, `NARROW`, `REPLACE`, `PAUSE`, or `STOP` decision;
- independent adviser review for material trust changes.

The meeting should not be dominated by task count.

## 06.28 Company dashboard

Primary metrics:

- qualified incidents with upcoming change;
- paid preflights/pilots;
- decisions completed;
- complete-substitute wins;
- second paid actions;
- time to first valid experiment;
- original-to-reduced cost ratio;
- customer-retained effort;
- independent operator success;
- same-family reuse;
- contribution margin;
- pack commercial maturity;
- active/expired contracts.

Secondary engineering metrics:

- product tests;
- security findings;
- escaped defects;
- CI reliability;
- factory retries;
- token/quota use.

Task count and repository size are not company KPIs.

## 06.29 Success definition

The company has a credible initial business when:

- one supported pack repeatedly produces decisions beyond the complete substitute;
- customers permit local execution;
- at least one customer pays twice;
- the workflow becomes less bespoke;
- another operator can run it;
- security and trust reviews pass;
- annual protection of important workloads becomes a rational purchase.

Until then, TrainCapsule is a strong technical and commercial experiment, not a proven business.


<!-- END 06_COMMERCIAL_MODEL_AND_GTM_V3.md -->


<!-- BEGIN FACTORY_LOOP_REDESIGN_SPEC.md -->

# TrainCapsule Autonomous Factory and Business Loop Redesign Specification

## 1. Objective

The present factory is optimized to keep producing and validating repository work until a large predefined product is complete. The replacement must optimize for a different objective:

> Advance the shortest evidence-backed path to one repeatable paid incident-to-change qualification decision, while preserving trust, security, and recoverability and stopping work that does not change customer outcomes.

The factory remains an engineering accelerator. It is not the company, the product authority, the customer, the human reviewer, or the source of commercial truth.

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
- no first-class human approval state;
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
│   ├── approvals/
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
  EXTERNAL_EVIDENCE | HUMAN_REVIEW | COMMERCIAL_EXPERIMENT |
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
ownerType: AI | FOUNDER | HUMAN_REVIEWER | CUSTOMER | EXTERNAL_PARTY
automatable:
packetPath:
evidenceRequired:
externalReceiptRequired:
humanApprovalRequired:
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
WAITING_HUMAN
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
humanApprovalRequired:
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

Engineering completion may be automated for M0–M2, but M3–M6 depend on external or human evidence and must never be fabricated.

## 7. Four-lane scheduler

### Lanes

#### PRODUCT

Build and validate the bounded product slice.

#### MARKET

Track founder/customer actions and external evidence. AI may research accounts, prepare interview packets, or summarize attributable notes. It may not mark conversations, interest, payment, or customer outcomes as complete without external receipts.

#### COMPETITOR

Continuously test the complete native/bundled/agent substitute and update the source register.

#### TRUST

Develop independent oracles, security evidence, human approval packets, and release policies.

A fifth `FACTORY` lane handles controller maintenance and may not dominate normal scheduling.

### Lane independence

A blocked customer conversation must not stop an unrelated controlled product task. A missing human approval must block external release, not internal testing. A competitor finding may stop a feature without stopping all product work.

### Initial WIP policy

```yaml
productMutating: 1
factoryMutating: 0 unless controller failure
readOnlyResearch: 1
externalTracking: unlimited records, no autonomous external action
humanReview: waiting state
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

Boolean factors may be 0/1; continuous factors use normalized values. The score is inspectable and overrideable through a signed founder decision.

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
- otherwise route to `WAITING_HUMAN` or `REJECTED_VALUE`;
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
humanApprovalForExpansion: true
```

Completion reviewers may propose work. They may not mutate the roadmap directly.

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
- human approval if externally exposed.

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
├── human_gate.py
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
  ownerClass: PRODUCT | FACTORY | EXTERNAL | HUMAN
  affectedCriterion:
  evidence:
  repairPaths:
```

- `PRODUCT`: return to product owner.
- `FACTORY`: preserve product candidate; run one bounded factory repair.
- `EXTERNAL`: wait; do not edit code to fabricate resolution.
- `HUMAN`: create approval packet.
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
- human approvals;
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
- human approvals.

### Review behavior

Three blind AI reviews are excessive for every milestone. Use:

- one deterministic verifier;
- one independent adversarial review for integration/trust milestones;
- one human approval for external release;
- optional second independent reviewer for disputed trust-core changes.

### Expansion behavior

Reviewers return proposals. The controller writes:

```text
factory/roadmap/proposals/<milestone>/<timestamp>.yaml
```

The founder or authorized product authority accepts/rejects each proposal. No automatic append to the authoritative ledger.

## 15. Human approval state

Add first-class records and status.

### Work-item state

```text
WAITING_HUMAN
```

### Approval scopes

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

- approval is signed or stored in a trusted external location;
- exact candidate SHA and artifact digests are included;
- expiry and conditions are enforced;
- AI cannot write to the trusted approval root;
- invalid or missing approval fails closed.

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
HUMAN_REVIEW
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
- approvals;
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
- human/external boundary.

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
prompts/human_approval_packet.md
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
- approval policy;
- external evidence;
- source precedence;
- private gates;
- broad dependency upgrades;
- network research unless specifically needed and read-only.

Policy:

```yaml
maxSelfRepairsPerIncident: 1
humanReviewAfterRepeat: true
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

The factory can squash a candidate and fast-forward `main`, then push directly.

### Replacement

Default to pull-request release.

```text
verified candidate
→ release branch
→ push
→ draft PR
→ required CI
→ human/authorized auto-merge policy
```

Modes:

```yaml
releaseMode: PULL_REQUEST
autoMergeAllowed:
  mechanical: true after CI
  standard: false initially
  integration: false
  trust_core: false
```

Required checks:

- factory unit/typing;
- product unit/contract;
- product controlled journey;
- secret/security;
- schema compatibility;
- source-of-truth integrity;
- human approval where applicable.

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
- show external/human blockers separately;
- display product versus factory CI.

## 29. Configuration V3

### `config/factory.yaml`

Required changes:

```yaml
version: 3
executionMode: backend_protocol
releaseMode: pull_request
maxConcurrentMutatingSessions: 1
maxConcurrentReadOnlySessions: 1
workUntilDone: false
milestoneCompletion: true
directMainPush: false
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
roadmapExpansionRequiresHumanApproval: true
maxSelfRepairsPerIncident: 1
maxControllerRestarts: 3
```

No value uses zero to mean unlimited.

### New configuration

```text
config/scheduler.yaml
config/milestones.yaml
config/human_approval.yaml
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
- completion expansion requires approval;
- controller restart budget stops loop;
- candidate preserved.

### External truth

- AI-writable receipt rejected;
- invalid signature rejected;
- synthetic receipt cannot advance commercial maturity;
- missing payment/second-use receipt remains external required.

### Human approval

- exact SHA binding;
- expired approval rejected;
- wrong scope rejected;
- AI-generated local file rejected when trusted root required.

### Release

- no direct main push;
- PR created from verified candidate;
- integration/trust cannot auto-merge;
- CI identity bound to candidate SHA.

### Context

- acquisition/career docs excluded from routine build;
- stale current-fact snapshot blocks affected task;
- task context stays within configured budget.

### Completion

- M2 can complete without M4 external evidence;
- M4 cannot complete from synthetic fixtures;
- reviewer proposals do not mutate roadmap.

## 32. Migration execution order

### Step 0 — Pause

- stop scheduled/autopilot process;
- create clean baseline tag/branch;
- export current queue, ledger, checkpoints, and logs;
- verify CI.

### Step 1 — Install V3 authority

- add V3 documents;
- update source precedence;
- keep old bundle immutable as archive;
- generate manifest and hashes.

### Step 2 — Add V3 schemas/models

- work items;
- milestones;
- maturity;
- approvals;
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
- create gate-based V3 work items;
- preserve history;
- do not resume T002 as company-critical work.

### Step 7 — Controlled validation

- run factory tests;
- run migration dry-run;
- run scheduler simulation;
- run one mechanical task;
- run one standard product task;
- simulate quota, failure, external wait, human wait, and rollback.

### Step 8 — Human review and re-enable

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
- the founder can understand the active decision;
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
- human approval turnaround;
- external evidence freshness;
- quota efficiency;
- escaped gate defects.

“Tasks completed” is not the primary metric.


<!-- END FACTORY_LOOP_REDESIGN_SPEC.md -->


<!-- BEGIN 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md -->

# 12 — Gate-Based Roadmap and Backlog V3

## 12.1 Roadmap principle

The roadmap is not a promise to build every designed capability. It is a sequence of evidence gates.

Four lanes run in parallel:

```text
PRODUCT      — build the bounded qualification workflow
MARKET       — acquire real incident, buyer, price, and repeat evidence
COMPETITOR   — establish the complete native/bundled/agent baseline
TRUST        — create independent oracles, security evidence, and human authority
```

`FACTORY` is a temporary migration/maintenance lane, not a fifth product strategy.

The next milestone may begin only when its entry criteria are satisfied. Independent work in other lanes may continue when a particular external item is waiting.

## 12.2 Milestone map

```text
M0  Factory and authority migration
 │
 ├─────────────┬─────────────┬─────────────┐
 ▼             ▼             ▼             ▼
M1-PRODUCT   M1-MARKET    M1-COMP       M1-TRUST
 Native       problem      native         trust
 preflight    access       baseline       foundations
 └─────────────┴─────────────┴─────────────┘
                         │
                         ▼
              M2 Controlled qualification
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
        M3 External preflight   continued controlled proof
               │
               ▼
           M4 Paid pilot
               │
               ▼
           M5 Paid repeat
               │
               ▼
   M6 Commercially supported pack
```

## 12.3 M0 — Factory and source-of-truth migration

### Exit criteria

- V3 source authority installed and integrity-checked;
- old bundle archived, not silently edited;
- lane/work-item/milestone schemas active;
- finite retry and restart budgets enforced;
- human and external evidence states implemented;
- completion expansion is proposal-only;
- release uses pull requests;
- factory and product CI separated;
- current queue safely migrated;
- one mechanical and one standard simulated work item complete;
- rollback tested;
- human approval of source migration recorded.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-MIG-001` | FACTORY | Pause autopilot and snapshot repository/runtime state | — | baseline SHA, clean status, queue/checkpoint export |
| `V3-MIG-002` | FACTORY | Create immutable migration branch and rollback tag/instructions | 001 | branch/tag refs, rollback drill |
| `V3-MIG-003` | TRUST | Install V3 documents without mutating old bundle | 001 | source tree, authority diff |
| `V3-MIG-004` | TRUST | Replace source-precedence and context-index policy | 003 | integrity tests, normative/current-fact separation |
| `V3-MIG-005` | FACTORY | Add V3 work-item, milestone, maturity, disposition models | 003 | schemas, model tests |
| `V3-MIG-006` | FACTORY | Add lane-aware scheduler and deterministic score | 005 | scheduler simulation and unit tests |
| `V3-MIG-007` | FACTORY | Enforce finite planning, repair, redesign, expansion, and restart budgets | 005 | retry tests, no-zero-unlimited test |
| `V3-MIG-008` | TRUST | Add signed human-approval model and trusted-root verification | 005 | positive/negative/expiry/SHA tests |
| `V3-MIG-009` | MARKET | Generalize signed external-evidence receipts | 005 | invalid/synthetic/issuer tests |
| `V3-MIG-010` | FACTORY | Convert completion audit to milestone proposal-only behavior | 005,007 | proposal artifact; no ledger mutation |
| `V3-MIG-011` | FACTORY | Add backend-neutral executor interface and Claude adapter | 005 | protocol tests; current Claude flow preserved |
| `V3-MIG-012` | FACTORY | Change release path from direct main to draft PR | 005 | PR dry run, exact-SHA checks |
| `V3-MIG-013` | FACTORY | Split factory, product, security, and source-integrity CI | 012 | workflows and local equivalents |
| `V3-MIG-014` | FACTORY | Make Windows/WSL controls configurable; add restart budget | 007 | non-hardcoded config tests |
| `V3-MIG-015` | FACTORY | Migrate legacy ledger/queue/checkpoints without resuming obsolete work | 005,006,007 | migration report and hashes |
| `V3-MIG-016` | TRUST | Human review of authority, release, and rollback | 003–015 | signed source-migration approval |
| `V3-MIG-017` | FACTORY | Run controlled migration rehearsal and rollback | 006–015 | full transcript and restored SHA |
| `V3-MIG-018` | FACTORY | Enable V3 controller in observation mode | 016,017 | scheduler decisions with no mutation |
| `V3-MIG-019` | FACTORY | Execute one mechanical and one standard V3 task | 018 | candidate manifests, PRs, CI |
| `V3-MIG-020` | FACTORY | Close M0 and archive legacy active queue | 019 | milestone completion record |

### M0 stop conditions

- migration cannot preserve current evidence/history;
- approval root can be written by AI roles;
- release can still bypass PR/human policy;
- rollback cannot restore baseline;
- V3 scheduler still serializes all lanes behind one item.

## 12.4 M1 — Native preflight and problem access

M1 deliberately combines product, market, competitor, and trust evidence. Engineering may progress while market items are waiting, but M2 commercial claims remain blocked.

### M1 product exit criteria

- product packages exist separately from `tcfactory`;
- product schemas exist;
- Flight Recorder importer works on controlled and real-format fixtures;
- identity/evidence lock works;
- native baseline and evidence-completeness report work;
- eligibility engine can return native sufficient, uneconomic, unsupported, policy blocked, and unknown;
- local CLI completes install-to-preflight journey.

### M1 market exit criteria

- 30 named accounts;
- 15 detailed conversations;
- 5 incident timelines;
- 3 upcoming changes;
- 2 credible pilot candidates;
- 1 real trace/archive under lawful access.

These are targets. Failure triggers a wedge decision, not fabricated completion.

### M1 competitor exit criteria

- current capability matrix for PyTorch, NVIDIA, AWS, CoreWeave, Chamber, Teyon, Harbor, Caladrius, TrainCheck, TrainVerify, TTrace, and relevant internal-scale research;
- reproducible native baseline for initial controlled case;
- exact remaining decision gap.

### M1 trust exit criteria

- product threat model;
- canonical identity oracle;
- parser adversarial tests;
- data/AI boundary;
- initial human-reviewer/adviser plan.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PROD-001` | PRODUCT | Create product monorepo/package skeleton | M0 | clean install, package import |
| `V3-PROD-002` | PRODUCT | Define product result, identity, evidence, and case schemas | 001 | schema round-trip/compatibility |
| `V3-TRUST-001` | TRUST | Build independent canonical serialization/identity oracle | PROD-002 | independent implementation, negative cases |
| `V3-PROD-003` | PRODUCT | Implement content-addressed local evidence manifest | PROD-002 | tamper/mixing tests |
| `V3-PROD-004` | PRODUCT | Implement workload identity | PROD-002,TRUST-001 | drift and weak-identity tests |
| `V3-PROD-005` | PRODUCT | Implement environment identity | PROD-002,TRUST-001 | material/immaterial drift tests |
| `V3-PROD-006` | PRODUCT | Implement PyTorch Flight Recorder importer | PROD-003–005 | official-format fixtures, malformed inputs |
| `V3-COMP-001` | COMPETITOR | Freeze current PyTorch Flight Recorder capability baseline | M0 | official sources, commands, findings |
| `V3-PROD-007` | PRODUCT | Emit native findings without attribution laundering | PROD-006,COMP-001 | source labels and tests |
| `V3-PROD-008` | PRODUCT | Implement evidence-completeness report for initial pack | PROD-006 | full missing/conflicting state matrix |
| `V3-PROD-009` | PRODUCT | Implement eligibility and economic preflight | PROD-007,008 | all terminal outcomes |
| `V3-PROD-010` | PRODUCT | Implement local CLI through `preflight` | PROD-003–009 | install-to-preflight journey |
| `V3-TRUST-002` | TRUST | Threat model importer, CAS, identity, CLI, and local storage | PROD-010 | security review and tests |
| `V3-TRUST-003` | TRUST | Implement deterministic redaction and export policy | PROD-003 | secret and policy tests |
| `V3-COMP-002` | COMPETITOR | Build complete native/bundled/agent capability matrix | COMP-001 | dated source register |
| `V3-COMP-003` | COMPETITOR | Reproduce native baseline on initial controlled case | PROD-006,COMP-001 | commands, artifacts, operator effort |
| `V3-COMP-004` | COMPETITOR | Define the exact unowned decision gap | COMP-002,003 | decision-level differential |
| `V3-MKT-001` | MARKET | Build 30-account reachable map | M0 | attributable account records |
| `V3-MKT-002` | MARKET | Prepare interview guide and evidence policy | M0 | review-ready packet |
| `V3-MKT-003` | MARKET | Record 15 qualified conversations | MKT-001,002 | external receipts/notes |
| `V3-MKT-004` | MARKET | Record 5 incident timelines | MKT-003 | sanitized timelines |
| `V3-MKT-005` | MARKET | Identify 3 real upcoming changes | MKT-003 | named decision/deadline |
| `V3-MKT-006` | MARKET | Qualify 2 pilot candidates | MKT-004,005 | ICP score and next action |
| `V3-MKT-007` | MARKET | Secure lawful access to one real trace/archive | MKT-004 | access/rights receipt |
| `V3-DEC-001` | TRUST | Conduct M1 wedge review | all M1 critical items | `KEEP/NARROW/REPLACE/STOP` decision |

### M1 decision

Continue the initial pack only when:

- at least two concrete incidents fit the pack;
- a future change creates a real decision;
- the native workflow leaves a meaningful gap;
- evidence and local execution are feasible.

Otherwise narrow or replace before M2 broad implementation.

## 12.5 M2 — Controlled end-to-end qualification

### Exit criteria

- one controlled failure goes from native evidence to bounded qualification;
- one candidate fixes or guards the contract;
- one candidate regresses or remains failing;
- at least one legal reduction is verified;
- at least one illegal reduction is rejected;
- Recovery Assurance evaluates named properties;
- contract is locally verifiable, expiring, and requalifiable;
- result viewer is thin and read-only;
- real 2–8 GPU execution occurs;
- independent operator runs the journey;
- qualified human approves only controlled external demonstration, not commercial support.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PROD-011` | PRODUCT | Define initial pack schema and mechanism boundaries | M1 decision | pack spec and negative boundaries |
| `V3-TRUST-004` | TRUST | Build independent observed-boundary oracle | PROD-011 | positive/ambiguous/missing-rank cases |
| `V3-PROD-012` | PRODUCT | Implement rank/process-group lifecycle alignment | PROD-011,TRUST-004 | controlled traces |
| `V3-PROD-013` | PRODUCT | Implement hypothesis ledger and plan schema | PROD-011 | falsifier and status tests |
| `V3-PROD-014` | PRODUCT | Implement registered reduction operators for initial pack | PROD-011 | precondition and rollback tests |
| `V3-TRUST-005` | TRUST | Build reduction-faithfulness oracle | PROD-014 | independent negative controls |
| `V3-PROD-015` | PRODUCT | Implement pack-specific experiment planner | PROD-012–014,TRUST-005 | bounded plans, no universal planner |
| `V3-PROD-016` | PRODUCT | Implement signed faithfulness contract | PROD-014,015 | tamper, drift, expiry tests |
| `V3-PROD-017` | PRODUCT | Implement customer-local runner preflight/materialization | PROD-002,016 | containment/resource tests |
| `V3-TRUST-006` | TRUST | Complete runner threat model and containment tests | PROD-017 | escape/network/path tests |
| `V3-PROD-018` | PRODUCT | Implement execution records and artifact capture | PROD-017 | identity/tamper tests |
| `V3-PROD-019` | PRODUCT | Implement Recovery Property contracts | PROD-002 | per-property oracle schema |
| `V3-TRUST-007` | TRUST | Implement independent recovery aggregation oracle | PROD-019 | fail/unknown/optional tests |
| `V3-PROD-020` | PRODUCT | Implement baseline/candidate comparator | PROD-016,018,019,TRUST-007 | decision matrix tests |
| `V3-TRUST-008` | TRUST | Build independent qualification semantics oracle | PROD-020 | invalid-oracle and unknown tests |
| `V3-PROD-021` | PRODUCT | Implement local incident-contract registry | PROD-020 | create/verify/expire/supersede |
| `V3-PROD-022` | PRODUCT | Implement external verifier | PROD-021,TRUST-001,005,007,008 | independent verification |
| `V3-PROD-023` | PRODUCT | Implement thin local report viewer | PROD-020–022 | report/machine-record consistency |
| `V3-PROD-024` | PRODUCT | Build controlled omitted/reordered/data-branch/rank-exit cases | PROD-011 | labeled controlled corpus |
| `V3-PROD-025` | PRODUCT | Execute CPU/local multi-process journeys | PROD-012–024 | end-to-end evidence |
| `V3-PROD-026` | PRODUCT | Execute real 2–8 GPU controlled journey | PROD-025,TRUST-006 | real GPU artifacts |
| `V3-COMP-005` | COMPETITOR | Run head-to-head native versus TrainCapsule case | PROD-026 | decision differential |
| `V3-PROD-027` | PRODUCT | Add upgrade/rollback and offline bundle | PROD-022,026 | install/rollback evidence |
| `V3-TRUST-009` | TRUST | Independent operator executes controlled journey | PROD-027 | signed operator receipt |
| `V3-TRUST-010` | TRUST | Human review of controlled demonstration | all M2 trust/product | scoped approval |
| `V3-DEC-002` | TRUST | M2 product/native/value disposition | COMP-005,TRUST-010 | continue/narrow/stop |

### M2 stop conditions

- no material decision beyond native workflow;
- legal reduction cannot be established;
- cost reduction is not meaningful;
- independent operator cannot run the workflow;
- runner security cannot be bounded;
- controlled success depends on hidden manual intervention.

## 12.6 M3 — External paid-preflight readiness

### Exit criteria

- real evidence can be imported locally under policy;
- one customer-specific decision is in supported envelope;
- paid preflight packet, contract, security package, and pricing hypothesis are ready;
- adviser/reviewer availability confirmed;
- no customer/payment claim is made yet.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-MKT-008` | MARKET | Finalize paid preflight offer and scope | M2 | offer document |
| `V3-MKT-009` | MARKET | Finalize pricing experiment and commercial terms | M2 | pricing ledger |
| `V3-TRUST-011` | TRUST | Complete customer security/procurement packet | M2 | security documents |
| `V3-TRUST-012` | TRUST | Contract qualified distributed-training adviser | M2 | external receipt |
| `V3-TRUST-013` | TRUST | Contract security reviewer | M2 | external receipt |
| `V3-PROD-028` | PRODUCT | Run real-archive preflight without unsupported execution claims | MKT-007,M2 | local evidence report |
| `V3-COMP-006` | COMPETITOR | Run customer-case native baseline | PROD-028 | exact native result |
| `V3-MKT-010` | MARKET | Secure customer approval for paid preflight proposal | MKT-006,008–009,TRUST-011 | signed/external receipt |
| `V3-DEC-003` | TRUST | Authorize paid preflight | PROD-028,COMP-006,TRUST-012–013,MKT-010 | founder/human decision |

## 12.7 M4 — Paid Incident-to-Change Qualification Pilot

M4 is external. It cannot be completed by repository fixtures.

### Entry criteria

- paid contract or invoice/payment evidence;
- named incident;
- named upcoming change;
- named decision owner and deadline;
- baseline/candidate access;
- local execution authority;
- privacy/security approval;
- second execution included.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PILOT-001` | MARKET | Record paid engagement and exact scope | M3 | signed paid receipt |
| `V3-PILOT-002` | PRODUCT | Import and lock customer-local case | 001 | customer-local manifest |
| `V3-PILOT-003` | COMPETITOR | Complete native workflow baseline | 002 | commands/findings/decision |
| `V3-PILOT-004` | PRODUCT | Produce evidence/eligibility decision | 002,003 | preflight |
| `V3-PILOT-005` | TRUST | Human approve case-specific experiment/reduction plan | 004 | signed approval |
| `V3-PILOT-006` | PRODUCT | Construct and verify faithful experiment | 005 | faithfulness record |
| `V3-PILOT-007` | PRODUCT | Execute baseline and candidate locally | 006 | execution records |
| `V3-PILOT-008` | PRODUCT | Evaluate Recovery Assurance | 007 | property matrix |
| `V3-PILOT-009` | PRODUCT | Issue bounded qualification decision | 007,008 | signed result |
| `V3-PILOT-010` | TRUST | Human approve customer-facing claims | 009 | signed approval |
| `V3-PILOT-011` | MARKET | Obtain customer decision/value feedback | 009,010 | attributable receipt |
| `V3-PILOT-012` | PRODUCT | Install reusable local contract and runbook | 009 | independent verification |
| `V3-PILOT-013` | MARKET | Schedule and contract the included second execution | 001,012 | dated commitment |
| `V3-DEC-004` | TRUST | Pilot disposition | 011–013 | continue/narrow/stop |

### M4 successful outcome

- real decision changed or materially strengthened;
- complete substitute did not produce the same bounded result at acceptable cost;
- customer confirms value exceeds price and retained effort;
- reusable contract installed;
- second action scheduled.

A technically valid but commercially weak result completes the pilot honestly and may stop the wedge.

## 12.8 M5 — Paid repeat

### Exit criteria

- same customer pays for or contractually consumes a second qualification;
- no trust-core rewrite;
- setup and delivery effort decline;
- contract drift/expiry works;
- another qualified operator participates;
- margin trajectory is improving.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-REPEAT-001` | MARKET | Record second paid/contracted action | M4 | signed receipt |
| `V3-REPEAT-002` | PRODUCT | Detect candidate/environment drift | 001 | drift report |
| `V3-REPEAT-003` | PRODUCT | Requalify existing contract | 002 | new decision |
| `V3-REPEAT-004` | TRUST | Independent operator completes workflow | 003 | operator receipt |
| `V3-REPEAT-005` | MARKET | Measure retained effort and value | 003 | customer receipt |
| `V3-REPEAT-006` | MARKET | Measure delivery economics | 003 | internal cost record |
| `V3-DEC-005` | TRUST | Repeat/productization disposition | 004–006 | continue/narrow/stop |

## 12.9 M6 — Commercially supported initial pack

### Exit criteria

- at least one external-value demonstration;
- paid repeat;
- third same-family case or equivalent reusable proof;
- no trust-core rewrite;
- qualified human pack approval;
- security/support/rollback;
- native advantage remains current;
- commercially supportable scope and version policy.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PACK-001` | PRODUCT | Consolidate pack from repeated cases | M5 | versioned pack |
| `V3-PACK-002` | PRODUCT | Demonstrate third same-family case without core rewrite | 001 | case evidence |
| `V3-COMP-007` | COMPETITOR | Refresh complete-substitute benchmark | 001 | current sources/run |
| `V3-TRUST-014` | TRUST | Final pack oracle/security review | 001–003 | independent reports |
| `V3-TRUST-015` | TRUST | Qualified human commercial-pack approval | 014 | signed approval |
| `V3-PROD-029` | PRODUCT | Publish support/upgrade/deprecation policy | 015 | operator docs |
| `V3-MKT-011` | MARKET | Offer protected-workload agreement | M5 | customer response |
| `V3-DEC-006` | TRUST | Mark pack commercially supported or refuse | all M6 | maturity decision |

## 12.10 Checkpoint pack roadmap

The checkpoint/resume pack is not on the initial commercial critical path.

Allowed before M5:

- schema design;
- controlled reference implementation;
- comparison against AWS/NVIDIA/native recovery;
- customer-property discovery.

Commercial promotion requires a specific external gap.

Potential work items remain `DEFERRED`:

```text
V3-REF-CKPT-001  reference property schema
V3-REF-CKPT-002  controlled model/optimizer/RNG/sampler/data-cursor cases
V3-REF-CKPT-003  native recovery capability benchmark
V3-REF-CKPT-004  customer-specific property evidence
V3-REF-CKPT-005  commercial-release decision
```

Do not implement universal checkpoint certification.

## 12.11 Deferred platform backlog

Keep as design-only until M5/M6 evidence:

- generalized actor IR;
- broad FSDP/parallelism abstraction;
- arbitrary scale-emulation backend;
- provider federation;
- hosted control plane;
- multi-tenant service;
- dashboard suite;
- automatic repair;
- cross-customer knowledge graph;
- hardware-dependence pack;
- numerical divergence pack;
- fail-slow pack;
- provider marketplace;
- billing/RBAC.

Each requires a promotion record with:

- paid or repeated need;
- complete-substitute gap;
- security burden;
- expected decision value;
- owner;
- stop criteria.

## 12.12 Legacy 124-task ledger disposition

The current ledger is preserved as historical design input, not active company completion.

Migration policy:

- T001/T002 and existing factory work become legacy `FACTORY` history.
- Broad P0–P9 product tasks become `DEFERRED_DESIGN` unless explicitly represented in V3.
- Concepts required by V3 are reintroduced as new work items with bounded acceptance.
- No V3 task depends on all earlier numerical IDs.
- Passing a legacy task does not advance commercial maturity.
- Legacy packets are not automatically resumed.
- Old artifacts remain attributable to their original SHA and policy.

The migration must produce a machine-readable mapping:

```yaml
legacyTaskId:
legacyOutcome:
v3Disposition:
v3WorkItems:
reason:
preservedEvidence:
```

## 12.13 Operating cadence

### Daily automated

- scheduler selects critical path;
- deterministic health/CI;
- current candidate/retry budget;
- external/human wait visibility;
- no autonomous external contact.

### Weekly founder review

- active milestone;
- market evidence;
- native changes;
- candidate pilot;
- stop signals;
- product/factory code ratio;
- next human action.

### Monthly wedge review

For every active pack/backend/surface choose:

```text
KEEP
INTEGRATE_EXISTING_BACKEND
UPSTREAM
NARROW
REPLACE
PAUSE
STOP
```

The decision and evidence are versioned.

## 12.14 Roadmap success criteria

This roadmap succeeds when it reduces uncertainty in this order:

1. Can the customer and decision be identified?
2. Does the complete native workflow leave a meaningful gap?
3. Can one bounded workflow close that gap?
4. Can it run safely in the customer environment?
5. Will someone pay?
6. Does the customer use it again?
7. Does delivery compound into product?
8. Is a supported pack economically defensible?

It fails when it optimizes for finishing architecture before answering those questions.


<!-- END 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md -->


<!-- BEGIN SOURCE_OF_TRUTH_MIGRATION_PLAN.md -->

# Source-of-Truth and Repository Migration Plan

## 1. Purpose

This plan installs the V3 product and factory strategy without destroying the historical 9 August 2026 bundle or resuming an obsolete build graph.

The migration must be reversible, reviewable, and tied to an exact repository SHA.

## 2. Baseline

Audited baseline:

```text
repository: TasfiqJ/TrainCapsule
branch: main
commit: c31caefaeed7e605f6ef304fae6fcfe708a163b9
date reviewed: 11 August 2026
```

Before implementation, Codex must verify the current `main` SHA. When it differs, it must:

1. fetch the new commits;
2. summarize relevant changes;
3. re-run affected integrity and controller tests;
4. record the actual migration base SHA;
5. avoid assuming this audit is still exact.

## 3. Migration safety rules

- Pause the scheduled/autonomous controller before editing.
- Do not delete runtime evidence, queue records, checkpoints, or logs.
- Do not edit the old final bundle in place.
- Do not force-push.
- Do not merge directly to `main`.
- Work on a dedicated branch and open a draft PR.
- Preserve a rollback branch/tag or exact base SHA.
- Store a migration manifest containing old/new hashes.
- No AI-created human approval.
- No synthetic external evidence may advance commercial milestones.
- No old active task automatically resumes after schema migration.

## 4. New document bundle

Create:

```text
docs/source-of-truth/v3-2026-08-11/
├── README.md
├── 00_EXECUTIVE_BUILD_DECISION_V3.md
├── 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md
├── 04_TECHNICAL_ARCHITECTURE_V3.md
├── 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md
├── 06_COMMERCIAL_MODEL_AND_GTM_V3.md
├── 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md
├── 13_SOURCE_REGISTER_V3.md
├── 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md
├── FACTORY_LOOP_REDESIGN_SPEC.md
├── REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md
└── FINAL_MANIFEST_V3.json
```

The historical bundle remains:

```text
docs/source-of-truth/final-2026-08-09/
```

Add a clear archival marker inside a new adjacent README or index. Do not rewrite historical documents merely to remove conflicts.

## 5. New authority model

Replace one mixed hierarchy with two.

### 5.1 Normative product authority

```text
1. signed human approvals for their exact scope
2. 00_EXECUTIVE_BUILD_DECISION_V3.md
3. 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md
4. 04_TECHNICAL_ARCHITECTURE_V3.md
5. 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md
6. 06_COMMERCIAL_MODEL_AND_GTM_V3.md
7. 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md
8. FACTORY_LOOP_REDESIGN_SPEC.md
9. 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md
10. approved ADRs, pack specifications, security policies, and work-item packets
```

### 5.2 Current factual authority

```text
1. current official primary source or exact upstream code/version
2. dated source-register entry
3. current capability/claim register
4. affected internal narrative
```

A current source may mark a normative assumption stale. It may not silently change product policy. That requires an ADR or wedge decision.

### 5.3 Advisory documents

Acquisition and career documents remain advisory and must not be injected into routine product tasks.

## 6. `SOURCE_PRECEDENCE.md` replacement

The file should:

- identify V3 as controlling;
- name the historical bundle;
- separate normative and factual authority;
- define conflict handling;
- define signed human approval scope;
- prohibit source-monitor agents from rewriting policy;
- prohibit old duplicate filenames from active globs;
- state that product and commercial maturity are separate;
- define the baseline manifest.

## 7. `docs/CONTEXT_INDEX.yaml` replacement

Create role/task-specific groups.

```yaml
version: 3
groups:
  product_normative:
  technical_architecture:
  trust_core:
  commercial:
  roadmap:
  current_facts:
  factory_control:
  advisory_acquisition:
  advisory_career:
```

Rules:

- routine product tasks receive no acquisition/career context;
- factory repair receives factory-control context, not customer strategy;
- market research receives commercial/current-fact context, not product implementation;
- trust review receives trust/technical/current facts;
- each context entry includes digest and authority class;
- stale factual sources trigger a current-fact refresh, not automatic policy edits.

## 8. Duplicate and manifest cleanup

The old bundle includes byte-identical duplicate logical documents with `(1)` suffixes.

Migration actions:

1. leave the old physical files untouched for historical integrity;
2. exclude duplicates from active V3 authority;
3. include one canonical logical document in V3;
4. define aliases only in a historical mapping file;
5. ensure no active script uses broad globs that include both copies.

## 9. Canonical hashing

Do not embed an ordinary self-hash inside the file being hashed.

`FINAL_MANIFEST_V3.json` contains:

```json
{
  "manifestVersion": 3,
  "bundleVersion": "v3-2026-08-11",
  "generatedAt": "...",
  "migrationBaseSha": "...",
  "hashAlgorithm": "sha256",
  "canonicalization": {
    "textEncoding": "utf-8",
    "lineEndings": "lf",
    "trailingNewline": true
  },
  "files": [
    {
      "path": "...",
      "sha256": "...",
      "bytes": 0,
      "authorityClass": "normative"
    }
  ]
}
```

The manifest may omit its own hash or use an external detached digest. It must not create an impossible self-referential hash requirement.

## 10. Integrity gate

Create `scripts/gates/source_of_truth_integrity.py`.

It verifies:

- every active V3 file exists;
- hashes match manifest;
- no unlisted normative file enters the active bundle;
- old archive is not treated as active;
- authority order is valid;
- current-fact and normative classes are distinct;
- no duplicate logical IDs;
- no self-hash contradiction;
- no absolute local paths;
- no active references to `(1)` duplicates;
- V3 context index resolves;
- required human-approval policy exists;
- no external/commercial milestone is marked complete from synthetic evidence.

Run locally and in GitHub Actions.

## 11. Product/factory package separation

Change `pyproject.toml` from a factory-only package arrangement to a workspace or explicit multi-package setup.

At minimum:

- retain `tcfactory`;
- add product package paths;
- add product dependency groups;
- add product CLI entrypoint separately;
- configure Ruff/Pyright/Pytest for product and factory;
- do not exclude the active V3 bundle from all integrity checking;
- avoid importing factory domain types into product packages.

## 12. Legacy roadmap migration

Create:

```text
factory/roadmap/migrations/v2_to_v3.yaml
```

For every legacy task:

```yaml
legacyTaskId:
legacyStatus:
legacyPacket:
v3Disposition:
mappedWorkItems:
reason:
evidencePreserved:
```

Rules:

- legacy tasks remain historical;
- broad architecture work defaults to deferred;
- no chain from T001 through T124 controls V3 scheduling;
- current T002 is not automatically re-run;
- only concepts represented by explicit V3 work items become active;
- old task artifacts retain original policy and SHA.

## 13. Queue and checkpoint migration

Procedure:

1. export queue listing and hashes;
2. checkpoint any live candidate;
3. stop controller;
4. move active V2 queue entries into an archive namespace;
5. do not alter candidate Git commits;
6. create V3 queue directories;
7. add a salvage command for relevant candidate work;
8. record all moves in migration manifest;
9. require human decision before salvaging obsolete task work.

## 14. Configuration migration

Do not mutate V2 config in place without version handling.

- introduce config version 3;
- reject mixed V2/V3 runtime;
- provide a migration command;
- remove zero/unlimited semantics;
- set PR release mode;
- add scheduler, milestone, approval, evidence, executor files;
- validate before controller starts;
- preserve V2 files in Git history.

## 15. Runtime state migration

New state records must have explicit schemas and versions.

Do not load arbitrary old JSON into new models.

For each state file:

- parse using old model;
- emit normalized migration record;
- write V3 state to a new path;
- preserve old file read-only;
- hash source and destination;
- test rollback.

## 16. GitHub migration

- create migration branch;
- push branch;
- open draft PR;
- run GitHub-hosted CPU checks;
- run optional self-hosted checks;
- require human review for source authority and trust/release changes;
- do not enable auto-merge during migration;
- do not alter branch protection automatically unless explicitly authorized.

## 17. CI migration

Keep current factory workflow temporarily but rename/clarify it.

Add:

- source-of-truth integrity;
- factory quality;
- product unit;
- product contract;
- security;
- controlled journey.

The migration PR must show which checks are required and which depend on local GPU infrastructure.

## 18. Prompt migration

Update prompts only after V3 authority exists.

Every prompt must reference the V3 context resolver and new work-item model.

Remove:

- work-until-done language;
- universal completion language;
- automatic roadmap expansion;
- implicit AI commercial authority;
- broad source injection.

Add:

- bounded outcome;
- finite limits;
- native-equivalence;
- external/human states;
- value rejection;
- no scope expansion.

## 19. Verification plan

### Static

- schemas;
- typing;
- lint;
- manifest;
- path rules;
- no duplicate authority;
- no direct-main release code path in active mode.

### Dynamic

- scheduler simulation;
- finite retry exhaustion;
- candidate preservation;
- external wait;
- human wait;
- rejected-value stop;
- milestone completion;
- proposal-only expansion;
- PR creation dry-run;
- launcher restart budget;
- V2 rollback.

### Adversarial

- forged human approval;
- synthetic payment;
- stale source;
- modified old bundle;
- direct main push;
- zero retry limit;
- cross-lane global block;
- completion reviewer attempting ledger mutation.

## 20. Rollback

Rollback conditions:

- migration corrupts queue or evidence;
- V3 controller makes unauthorized changes;
- candidate preservation fails;
- source integrity is ambiguous;
- approval root is writable by AI;
- release bypasses PR policy.

Rollback steps:

1. stop V3 controller;
2. preserve V3 artifacts/logs;
3. checkout exact migration base SHA or rollback branch;
4. restore archived runtime state to a separate copy;
5. run V2 deterministic verification;
6. do not automatically restart obsolete queued work;
7. document cause before retrying migration.

## 21. Final migration acceptance

Migration is accepted only when:

- old and new source bundles are distinguishable;
- hashes and authority pass;
- V3 scheduler runs in observation mode correctly;
- no unlimited loops remain;
- no direct main promotion remains active;
- human/external evidence is unforgeable by AI roles;
- legacy task chain no longer defines company completion;
- product package can begin independently;
- rollback is demonstrated;
- qualified human approves the source/release migration.


<!-- END SOURCE_OF_TRUTH_MIGRATION_PLAN.md -->


<!-- BEGIN 13_SOURCE_REGISTER_V3.md -->

# 13 — Current Source and Competitive Register V3

- **Register date:** 11 August 2026
- **Review rule:** current product and upstream claims must be rechecked before a customer-facing comparison
- **Evidence rule:** product-page statements are public vendor claims, not independent validation
- **Technical rule:** prefer official documentation, source code, standards, and primary research
- **Commercial rule:** public sources can establish positioning and capabilities; they cannot prove TrainCapsule demand

## 13.1 Source classes

```text
P0  official upstream documentation or source
P1  peer-reviewed or primary research paper
P2  official vendor product/documentation claim
P3  official company announcement
P4  secondary analysis
```

Use P0/P1 for technical design. P2/P3 are acceptable for competitor positioning, but claims must remain attributed.

## 13.2 Current native and platform baselines

### S-PYTORCH-FR — PyTorch Flight Recorder

- Class: P0
- URL: https://pytorch.org/blog/flight-recorder-a-new-lens-for-understanding-nccl-watchdog-timeouts/
- Current public capability:
  - per-rank CPU-side ring buffer;
  - collective type and lifecycle state;
  - tensor dtype and size;
  - call stacks where configured;
  - timeout-triggered trace dumping;
  - cross-rank analysis of missing or mismatched collectives.
- TrainCapsule consequence:
  - Flight Recorder is the mandatory initial evidence/native baseline.
  - TrainCapsule gets no differentiation credit for locating a missing rank, collective, shape mismatch, or source stack already visible natively.
  - The importer should preserve native findings and state the remaining decision gap.

### S-NVIDIA-AJR — NVIDIA Mission Control / Autonomous Job Recovery

- Class: P0/P2
- URL: https://docs.nvidia.com/mission-control/docs/systems-quick-start-guide/2.2.0/are-release-notes.html
- Current public capability:
  - FACT attribution service;
  - slow-signal attribution;
  - automatic resume;
  - temporary/sticky node exclusion;
  - Shoreline diagnosis/repair integration;
  - node-centric data and lifecycle events.
- TrainCapsule consequence:
  - do not build a general restart, anomaly-attribution, or node-exclusion product;
  - target workload-specific qualification and private/cross-environment decisions that remain after recovery;
  - checkpoint/reference pack must show an application-specific gap.

### S-AWS-HYPERPOD-RECOVERY — SageMaker HyperPod checkpointless in-process recovery

- Class: P0
- URL: https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-eks-checkpointless-in-process-recovery.html
- Current public capability:
  - recovery feasibility;
  - global-step consistency;
  - sufficient healthy replicas;
  - optional model checksum;
  - Python/NumPy/PyTorch/Megatron RNG capture and restoration;
  - in-memory checkpoint transfer.
- TrainCapsule consequence:
  - global step, checksum, and generic RNG restoration are not enough to justify a commercial checkpoint pack;
  - require customer-specific data cursor, sampler, ownership, replay/skip, trajectory, performance, or cross-environment properties.

### S-COREWEAVE-MISSION-CONTROL — CoreWeave Mission Control

- Class: P2/P3
- URL: https://www.coreweave.com/mission-control
- Current public capability/positioning:
  - fleet/node lifecycle and observability;
  - GPU straggler detection;
  - Mission Control Agent;
  - expert operations;
  - cluster security/telemetry;
  - included as part of CoreWeave Cloud.
- TrainCapsule consequence:
  - the competitor is “good enough, installed, approved, and included”;
  - do not sell generic cloud observability;
  - target private workload contracts, provider migration, and decisions spanning boundaries.

## 13.3 Direct and adjacent commercial competitors

### S-CHAMBER — Chamber

- Class: P2
- URLs:
  - https://www.usechamber.io/
  - https://www.usechamber.io/features
  - https://docs.usechamber.io/introduction
- Current public positioning:
  - GPU workload visibility;
  - AI root-cause summaries;
  - autonomous diagnosis/remediation;
  - checkpoint rerun;
  - Slack/CLI/console;
  - cross-cloud orchestration;
  - customer-infrastructure agent.
- Threat:
  - broad diagnosis/remediation and orchestration can make incident pain small enough that TrainCapsule is unnecessary.
- Required differentiation:
  - failure-derived, expiring baseline/candidate qualification with explicit faithfulness and application-state properties.

### S-TEYON — Teyon

- Class: P2
- URL: https://teyon.ai/
- Current public positioning:
  - always-on recording;
  - deterministic replay;
  - replay-driven recovery or diagnosis;
  - automatic handling of transient faults;
  - causal chain for persistent bugs;
  - publicly presented as an early/beta product.
- Threat:
  - closest public competitor to TrainCapsule's historical Close/replay loop.
- Required differentiation:
  - lower-cost faithful experiment search;
  - explicit reduction contracts;
  - applicability and expiry;
  - candidate-stack qualification;
  - recovery-property contracts;
  - honest `UNKNOWN`.

### S-HARBOR — Harbor

- Class: P2
- URL: https://www.harborops.ai/
- Current public positioning:
  - self-hosted, zero-egress diagnosis;
  - compute/network/storage/workload evidence;
  - causal chain or explicit unconfirmed status;
  - recommended operator-gated fix;
  - verification that the fix held;
  - Kubernetes and Slurm.
- Threat:
  - overlaps privacy, cross-layer diagnosis, evidence, and verified remediation.
- Required differentiation:
  - incident-derived future release contract rather than continuous fleet diagnosis.

### S-CALADRIUS — Caladrius

- Class: P2
- URL: https://www.caladrius.ai/platform
- Current public positioning:
  - cross-layer root-cause analysis;
  - model/GPU/fabric/storage attribution;
  - approved remediation;
  - verification and rollback;
  - fleet map and fail-slow coverage.
- Threat:
  - broad incident closure and verified fix.
- Required differentiation:
  - workload-specific lower-cost experiment and future change qualification, not another closed-loop remediation platform.

## 13.4 Research and open systems that absorb technical primitives

### S-TRAINCHECK — TrainCheck

- Class: P1/P0 project documentation
- URLs:
  - https://orderlab.io/TrainCheck/
  - https://orderlab.io/TrainCheck/technical-doc/
  - https://orderlab.io/TrainCheck/ae-eval-s5.3-transferability/
- Current capability:
  - collect traces from a healthy reference;
  - infer semantic invariants;
  - check target runs online/offline;
  - apply invariants across changed pipelines/library versions;
  - report violations.
- Threat:
  - directly overlaps recurring reference-versus-changed-run contracts.
- Required differentiation:
  - incident-derived rather than healthy-reference-only;
  - private decision context;
  - legal reduction and faithfulness;
  - baseline/candidate execution;
  - recovery-state assurance;
  - contract drift/expiry;
  - operational release decision.
- Mandatory benchmark:
  - determine when TrainCheck alone is sufficient.

### S-TRAINVERIFY — TrainVerify

- Class: P1
- URL: https://arxiv.org/abs/2506.15961
- Capability:
  - verifies mathematical equivalence of a distributed parallel execution plan to a logical model specification;
  - uses shape reduction and stage-wise verification.
- Threat:
  - absorbs distributed-plan correctness and formal reduction primitives.
- Boundary:
  - TrainCapsule should not duplicate general parallel-plan verification;
  - use or integrate such verification where it strengthens an incident contract.

### S-TTRACE — TTrace

- Class: P1
- URL: https://arxiv.org/abs/2506.09280
- Capability:
  - fine-grained intermediate tensor collection;
  - comparison to a trusted single-device reference;
  - threshold guidance for floating-point differences;
  - silent bug detection/localization.
- Threat:
  - absorbs numerical silent-error checking and localization.
- Boundary:
  - numerical divergence should remain a future backend/pack, not initial V1 scope.

### S-OPGUARD — OpGuard

- Class: P1
- URLs:
  - https://www.usenix.org/conference/osdi26/presentation/zhou-ziming
  - https://orderlab.io/OpGuard/
- Capability:
  - semantic-stable operator boundaries;
  - bitwise tensor fingerprints;
  - schedule-tolerant alignment;
  - first divergent operator;
  - reported production deployment at ByteDance.
- Threat:
  - strong operator-level first-divergence primitive.
- Boundary:
  - operator alignment is a replaceable backend;
  - do not build a weaker generic version as a primary differentiator.

### S-PRISMLLM — PrismLLM

- Class: P1
- URL: https://arxiv.org/abs/2605.15617
- Capability:
  - slice-based execution graph;
  - hybrid emulation with real selected ranks and virtual participants;
  - large-scale behavior using few GPUs;
  - reported performance/memory fidelity in evaluated workloads.
- Threat:
  - absorbs scale-emulation and reduced-resource reproduction.
- Boundary:
  - scale emulation is a backend requiring workload-specific validation;
  - TrainCapsule must not claim generic downscaling as proprietary defensibility.

### S-ARGUS — ARGUS

- Class: P1
- URL: https://arxiv.org/abs/2606.20374
- Capability:
  - always-on CPU/framework/kernel tracing;
  - low-overhead production-scale analysis;
  - progressive fail-slow localization;
  - reported deployment above 10,000 GPUs.
- Threat:
  - demonstrates advanced private/internal systems at large operators.
- Boundary:
  - frontier labs/hyperscalers are poor initial customers;
  - general fleet tracing is not the wedge.

### S-PERFTRACKER — PerfTracker

- Class: P1
- URL: https://arxiv.org/abs/2506.08528
- Capability:
  - online fine-grained profiling;
  - differential observability;
  - hardware/software performance diagnosis;
  - reported production deployment at O(10,000) GPUs.
- Threat:
  - broad performance diagnosis is crowded.
- Boundary:
  - fail-slow/performance pack remains deferred without a release-decision gap.

### S-XPUTIMER — XPUTimer

- Class: P1
- URL: https://arxiv.org/abs/2502.05413
- Capability:
  - lightweight tracing;
  - intra-kernel tracing and aggregate metrics;
  - large-cluster training anomaly diagnosis.
- Threat:
  - further reduces value of generic performance anomaly tooling.

### S-MEGASCALE — MegaScale

- Class: P1
- URL: https://arxiv.org/abs/2402.15627
- Capability:
  - full-stack production training system at more than 10,000 GPUs;
  - observability, diagnosis, fault tolerance, and straggler mitigation.
- Consequence:
  - the largest operators already possess substantial internal capability.

## 13.5 Engineering-factory sources

### S-ANTHROPIC-MAX — Claude Code with Pro/Max

- Class: P0/P2 official help
- URL: https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-max-plan
- Relevant fact:
  - Claude and Claude Code share subscription limits;
  - usage depends on workload and parallel instances.
- Factory consequence:
  - retain quota checkpoint/resume;
  - add explicit role allocation and concurrency limits;
  - do not assume parallel sessions are free.

### S-ANTHROPIC-CLAUDE-CODE — Claude Code documentation

- Class: P0
- URL: https://docs.anthropic.com/en/docs/claude-code/
- Factory consequence:
  - Claude-specific features belong in the backend adapter;
  - durable roadmap, release, evidence, and approval state remain tool-neutral.

### S-GITHUB-ACTIONS — GitHub Actions documentation

- Class: P0
- URL: https://docs.github.com/en/actions
- Factory consequence:
  - use least permissions, pinned actions, explicit required checks, timeouts, concurrency, and artifact retention;
  - use PR workflow rather than direct main promotion.

## 13.6 Capability matrix

| Capability | Strong current source/competitor | TrainCapsule V1 policy |
|---|---|---|
| collective mismatch and rank/call-stack evidence | PyTorch Flight Recorder | import and credit |
| node attribution/exclusion/restart | NVIDIA Mission Control | do not duplicate broadly |
| checkpointless recovery, step/checksum/RNG | AWS HyperPod | require application-specific gap |
| bundled fleet observability/support | CoreWeave Mission Control | avoid broad cloud reliability |
| AI diagnosis/remediation/rerun | Chamber | do not compete on generic agent |
| deterministic recording/replay | Teyon | do not claim replay novelty |
| self-hosted cross-layer diagnosis | Harbor | focus on future qualification |
| cross-layer fix/verification | Caladrius | focus on incident contract |
| healthy-run invariants across change | TrainCheck | mandatory differential benchmark |
| distributed-plan equivalence | TrainVerify | integrate/avoid duplicate |
| numerical silent-error localization | TTrace/OpGuard | future backend |
| few-GPU scale emulation | PrismLLM | replaceable backend |
| production fleet tracing/fail-slow | ARGUS/PerfTracker/XPUTimer | not V1 wedge |

## 13.7 Remaining public gap

As of the register date, no reviewed public source clearly documents one coherent commercial product that does all of the following:

1. ingests one private historical distributed-training failure;
2. records what is known and unknowable;
3. searches for a materially lower-cost faithful experiment;
4. records preserved and relaxed properties;
5. evaluates named recovery-state properties;
6. runs the same contract against a future stack/infrastructure change;
7. expires it on assumption drift;
8. operates customer-locally;
9. returns explicit `UNKNOWN`;
10. ties the outcome to a release/migration decision.

This is not proof that no private or stealth system exists. It is a bounded public-landscape conclusion.

## 13.8 Monthly update procedure

For each source:

```yaml
sourceId:
retrievedAt:
sourceVersionOrDate:
claimChanged:
impact:
affectedPackOrBackend:
requiredAction:
disposition:
reviewer:
```

A material change triggers:

- capability matrix update;
- native benchmark update;
- affected commercial maturity downgrade if needed;
- ADR or wedge decision;
- customer notification when a supported contract is affected.

## 13.9 Claim rules

Permitted:

- “Public documentation currently describes X.”
- “In the reviewed controlled case, native workflow Y produced decision Z.”
- “TrainCapsule added A within envelope B.”

Not permitted:

- “No competitor has this.”
- “The vendor cannot build it.”
- “TrainCapsule is more accurate.”
- “The market needs this.”
- “The product saves a stated amount.”

Those require stronger evidence than this register provides.


<!-- END 13_SOURCE_REGISTER_V3.md -->


<!-- BEGIN 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md -->

# 14 — Claude Code Master Build Prompt V3

## Mission

You are an engineering executor inside the TrainCapsule V3 factory.

Your mission is not to finish a large repository. Your mission is to deliver one bounded, trustworthy work item on the shortest evidence-backed path to a repeatable paid incident-to-change qualification decision.

TrainCapsule V3 is:

> A customer-local system that turns one costly distributed-training failure into an expiring release gate for one real upcoming PyTorch, CUDA, NCCL, driver, checkpoint, GPU, topology, scheduler, or cloud change.

The first commercial product is the **Incident-to-Change Qualification Pilot**.

## Authority

Read only the context manifest supplied for the work item. Within it, apply this order:

1. signed human approval for its exact scope;
2. V3 executive decision;
3. V3 product strategy;
4. V3 technical architecture;
5. V3 trust/reduction/recovery specification;
6. V3 commercial model;
7. V3 gate-based roadmap;
8. V3 factory redesign;
9. approved ADRs, pack specs, security policies, and the current work-item packet;
10. current official upstream facts for factual claims.

The 9 August 2026 bundle is historical design input when explicitly supplied. It does not override V3.

Acquisition and career documents are advisory and must not influence routine product implementation unless the work item explicitly concerns them.

## Product boundary

### Build now

- product package skeleton;
- product schemas;
- workload/environment/evidence identity;
- content-addressed local evidence;
- PyTorch Flight Recorder importer;
- native baseline;
- evidence completeness;
- eligibility/economic preflight;
- one pre-collective lifecycle incident pack;
- a small registered set of legal reductions;
- faithfulness contract;
- customer-local runner;
- named recovery properties;
- baseline/candidate comparator;
- expiring local incident contract;
- independent verifier;
- local CLI and thin viewer;
- controlled cases;
- security, offline install, upgrade, and rollback.

### Do not build without a promoted work item

- broad hosted SaaS;
- multi-tenancy, billing, or broad RBAC;
- owned GPU fleet;
- universal replay;
- universal actor IR;
- every scheduler/cloud/framework/accelerator;
- automatic production repair;
- provider federation;
- marketplace;
- cross-customer incident graph;
- broad dashboard;
- generic numerical, hardware, fail-slow, or checkpoint product;
- customer-specific integration without a committed user.

Do not create speculative scaffolding for deferred systems merely because it may be useful later.

## Native-first rule

Before adding proprietary functionality, identify what the latest approved native or existing system provides.

For the initial pack, PyTorch Flight Recorder is a mandatory input and baseline. Do not claim differentiation for a missing collective, rank mismatch, tensor mismatch, or call stack already produced natively.

Every major feature must answer:

1. What does the complete native/bundled/agent workflow already provide?
2. What exact additional capability is being implemented?
3. Does it alter a release, migration, recovery, or escalation decision?
4. Could an approved engineer plus current agents produce the same result?
5. What evidence would make this work `NATIVE_WORKFLOW_SUFFICIENT` or `NO_INCREMENTAL_DECISION_VALUE`?

## Truth rules

Keep separate:

- technical result;
- epistemic claim;
- operational decision;
- commercial maturity.

Use these technical states exactly where applicable:

```text
PASS
FAIL
UNKNOWN
INVALID_EVIDENCE
INVALID_ORACLE
INFRASTRUCTURE_ERROR
POLICY_BLOCKED
EXPIRED
```

`UNKNOWN` is a valid outcome. Never hide, rewrite, or upgrade it.

Do not claim:

- root cause from an observed boundary;
- hardware fault without appropriate evidence;
- universal safety;
- full recovery from a subset of state checks;
- customer value from a controlled fixture;
- payment, adoption, demand, or repeat use without a trusted external receipt.

Synthetic records must be labeled `SYNTHETIC_TEST_ONLY`.

## Human authority

No external or commercial release is approved solely by you or another AI session.

When human approval is required:

1. prepare an approval packet;
2. bind it to the exact candidate SHA and artifact digests;
3. list evidence, limitations, and required reviewer qualifications;
4. stop in `WAITING_HUMAN`;
5. do not create the approval yourself.

## Work-item protocol

You receive one typed work item and packet.

Before modifying files:

1. read the packet and context manifest;
2. inspect existing implementation and tests;
3. restate the bounded outcome privately in your work notes;
4. verify dependencies and base SHA;
5. identify native/substitute impact;
6. identify the oracle;
7. identify explicit non-goals;
8. stop if the packet asks for external evidence, customer action, or human approval that you cannot provide.

Do not expand scope. If the packet is invalid, return a structured blocking finding rather than rewriting the company plan.

## Planning

A plan must be finite and implementation-oriented.

Required fields:

```yaml
outcome:
decisionContribution:
filesExpected:
acceptanceCriteria:
nonGoals:
oracle:
gates:
risks:
rollback:
stopConditions:
```

Limits:

- no more than 12 acceptance criteria unless an approved exception exists;
- no more than 8 declared outputs;
- no broad restatement of source documents;
- no criterion requiring unrelated milestones;
- no output outside allowed paths;
- no generic “production ready” or “commercial value” criterion.

## Implementation

Implement the smallest complete behavior that satisfies the packet.

Required practices:

- typed interfaces;
- explicit error classes;
- deterministic serialization;
- versioned schemas;
- no silent fallback;
- no broad exception swallowing;
- no hidden network activity;
- no secrets in code/logs/tests;
- no test weakening;
- no disabling type/lint/security checks;
- no unrelated refactor;
- no placeholder presented as complete;
- no fake integration;
- no generated benchmark result without execution evidence.

Use comments for non-obvious invariants and security/trust boundaries, not for narrating trivial code.

## Testing

Testing must challenge the behavior, not merely execute lines.

At minimum, where relevant:

- positive case;
- negative case;
- boundary case;
- malformed input;
- identity/tamper case;
- `UNKNOWN` case;
- failure path;
- regression for the specific change.

Trust-critical work requires an independent oracle or differential method specified by the packet.

Do not let implementation and oracle share one circular assertion.

Mocks may prove local control flow. They do not prove GPU behavior, security containment, customer value, or external integration.

## Product-specific implementation rules

### Identity

- canonical serialization is deterministic;
- weak identity narrows claims;
- material drift invalidates results;
- secrets are redacted through a versioned policy.

### Evidence

- hash raw artifacts before parsing;
- preserve source/version/rank/process-group identity;
- retain warnings and missing evidence;
- never merge evidence across cases without explicit identity.

### Native findings

- label native findings separately;
- preserve what the native tool already established;
- state what remains unresolved.

### Observed boundary

- report first observed inconsistency within available evidence;
- include alignment uncertainty;
- do not call it root cause.

### Reduction

- invoke registered pack operators only;
- record preserved/relaxed properties;
- attempt counterexamples;
- reject illegal downscaling or substitution;
- mark economically weak reductions.

### Runner

- customer-local;
- least privilege;
- explicit resource/time/network policy;
- identity verification before run;
- artifact verification after run;
- infrastructure errors distinct from qualification failure.

### Recovery Assurance

- property-level matrix;
- required `UNKNOWN` blocks unconditional approval;
- checksum/global step/RNG do not imply complete state correctness.

### Qualification

- same signed contract for baseline and candidate;
- explicit material differences;
- valid oracle and faithfulness;
- applicability and expiry on first page;
- no universal compatibility claim.

## Factory-specific implementation rules

When the work item concerns the factory:

- preserve product candidate before controller repair;
- repair only the causal factory defect;
- do not change product authority, value thresholds, approval policy, or private evidence;
- finite retries only;
- no zero/unlimited semantics;
- no direct main promotion;
- completion reviewers propose work but cannot mutate the roadmap;
- factory code must not dominate product milestones after M0.

## Finding format

Every blocking finding must be concrete.

```yaml
findingId:
severity:
blocking:
criterion:
fingerprint:
evidence:
reproduction:
expected:
observed:
ownerClass: PRODUCT | FACTORY | EXTERNAL | HUMAN
minimalRepair:
```

Do not mark future enhancement, style preference, or speculative risk as blocking.

If the same finding fingerprint has already repeated to its configured limit, stop and escalate. Do not issue it again as if new.

## Research rules

Use current official/primary sources for current technical facts.

Record:

- source;
- retrieval date;
- version/date;
- exact capability;
- limitation;
- product implication.

Vendor pages establish what vendors publicly claim, not independent performance.

Web research cannot prove customer demand.

Do not turn a stable repository fact into an elaborate research experiment.

## Security rules

Treat traces, archives, code, checkpoints, environment files, and generated bundles as untrusted.

Defend against:

- path traversal;
- symlink escape;
- decompression bombs;
- malformed schemas;
- resource exhaustion;
- secret leakage;
- unsafe subprocess invocation;
- network egress;
- case mixing;
- artifact substitution;
- stale approval;
- forged external receipt.

Never use shell composition or unreviewed executable input in gates.

## Git rules

- work only in the assigned worktree/branch;
- do not alter `main`;
- do not force-push;
- do not rewrite unrelated history;
- commit only task changes;
- preserve candidate SHA;
- release through draft PR under current policy;
- do not merge integration/trust changes yourself.

## Completion output

Return a structured handoff:

```yaml
workItemId:
status:
baseSha:
candidateSha:
outcome:
filesChanged:
acceptanceEvidence:
gates:
oracleEvidence:
nativeComparison:
truthStates:
limitations:
blockingFindings:
advisoryFindings:
externalEvidenceRequired:
humanApprovalRequired:
rollback:
nextRecommendedAction:
```

The next action must remain within the roadmap. Do not create new work automatically.

## Stop conditions

Stop and return a blocking state when:

- source authority conflicts;
- required context is stale or missing;
- work item asks for external truth;
- human approval is required;
- allowed paths cannot satisfy output;
- oracle is circular or unavailable;
- security boundary is unclear;
- repeated-finding limit is reached;
- task would duplicate a native system without decision-level gap;
- implementation would require deferred platform breadth;
- evidence cannot support the requested claim.

A truthful bounded stop is better than an unsupported completion.

## Current build order after V3 migration

Unless the scheduler supplies another approved item, the product critical path is:

```text
product packages
→ product schemas
→ independent identity oracle
→ evidence CAS
→ workload/environment identity
→ Flight Recorder importer
→ native findings
→ evidence completeness
→ eligibility/economic preflight
→ local CLI preflight journey
```

Do not jump to universal replay, dashboards, provider exchange, or the broad checkpoint pack.

## Final operating principle

Build everything necessary to make one important decision trustworthy and repeatable. Do not build everything that can be imagined around GPU reliability.


<!-- END 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md -->
