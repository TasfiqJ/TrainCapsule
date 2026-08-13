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
