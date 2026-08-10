# 03 — Product Strategy and Requirements

- **Document date:** 9 August 2026
- **Status:** **Final source of truth**
- **Product category:** **Accelerated Workload Failure Reproduction and Change Qualification**
- **Initial wedge:** `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1`
- **Second planned wedge:** `CHECKPOINT_RESUME_STATE_CONSISTENCY_V1`

## 03.1 Product definition

> **TrainCapsule is a customer-local system that converts unresolved distributed accelerator failures into bounded experiments and turns confirmed failures into expiring workload incident contracts used to qualify future software, hardware, topology, checkpoint, and cloud changes.**

TrainCapsule has three products that share one trust core:

```text
TrainCapsule Close
  unresolved failure → faithful experiment → recovery assurance → incident contract

TrainCapsule Qualify
  incident/critical-workload contract → stack or infrastructure change → bounded release decision

TrainCapsule Exchange
  local/federated evidence → provider/upstream/vendor-native artifact → technical disposition
```

The commercial promise is:

> **Make a difficult accelerated-workload failure cheaper to reproduce, safer to recover from, and harder to reintroduce.**

## 03.2 What the customer buys

The customer does not buy “root cause.” The customer buys a completed operational decision under explicit limits.

A successful engagement produces at least one of:

- a `MinimumFaithfulExperiment` that materially reduces required GPUs, runtime, private data, setup burden, or specialist time;
- a `MechanismRecord` establishing a reproduced mechanism within a named envelope;
- a `ComponentDispositionRecord` supporting or rejecting a component dependency without converting technical evidence into legal blame;
- a `RecoveryAssuranceRecord` covering named checkpoint, optimizer, RNG, sampler, shard, numerical, performance, and observation-window properties;
- a `WorkloadIncidentContract` that can run after future stack changes;
- a native provider/upstream/hardware export;
- or an explicit `MITIGATE_AND_CLOSE_WITHOUT_DEEP_REPRODUCTION`, `UNSUPPORTED_OR_UNECONOMIC`, or `UNKNOWN` result.

The product must be willing to recommend no further investigation when closure costs exceed decision value.

## 03.3 Non-goals

TrainCapsule is not:

- a generic GPU metrics or trace dashboard;
- a conversational AIOps assistant;
- a replacement for Flight Recorder, NCCL RAS/Inspector, DCGM, schedulers, checkpointing, or native recovery;
- a generic fault-tolerant training runtime;
- a GPU scheduler or cloud;
- an autonomous code-repair or production-remediation agent;
- a universal debugger;
- a hardware-certification authority;
- a legal fault-adjudication system;
- a generic compatibility matrix;
- a long-horizon model-quality guarantee;
- or an industry standard declared by one company.

## 03.4 Product loops

### Close

Required stages:

1. qualify whether deep closure is economically rational;
2. lock workload and environment identity;
3. import native evidence before adding instrumentation;
4. determine evidence completeness and perturbation;
5. locate the first **observed** inconsistency;
6. preserve alternative mechanisms;
7. plan controlled experiments;
8. search for the lowest-cost faithful experiment within budget;
9. evaluate recovery-state properties;
10. create an expiring incident contract;
11. export only what policy permits.

### Qualify

Qualify runs contracts against a declared change. It returns:

```text
PASS_WITHIN_ENVELOPE
FAIL_SAME_INCIDENT
FAIL_DIFFERENT_BOUNDARY
DRIFT_REQUIRES_REQUALIFICATION
PRIVATE_REFERENCE_UNAVAILABLE
ENVIRONMENT_UNAVAILABLE
INFRASTRUCTURE_ERROR
STALE
EXPIRED
REVOKED
UNKNOWN
```

A pass means only that the named contract did not recur and the declared recovery/qualification properties passed in the tested envelope.

### Exchange

Exchange uses native formats first. It may produce:

- PyTorch/c10d/NCCL issue and regression artifact;
- cloud support bundle supplement;
- provider-local federated experiment;
- hardware workload-dependence report;
- quarantine/RMA evidence inventory;
- customer incident report;
- signed attestation and bounded result.

No external organization is required to accept a proprietary capsule format for the initial customer to receive value.

## 03.5 Primary customer

The primary initial segment is a model company, research platform, or internal training platform that:

- operates repeated distributed PyTorch/NCCL workloads;
- controls images, launch, checkpoints, evidence, and local experiments;
- has experienced a material unresolved failure or has high-consequence stack changes;
- has a platform/reliability owner;
- already uses native tools;
- has multiple workloads or a credible second use;
- and can fund a named incident or qualification outcome.

The second segment is a managed training platform or neocloud with enough customer incident volume and a limited internal replay/reduction workflow.

Do not assume frontier labs or hyperscalers are the first customer. Their pain is high, but internal capability and data boundaries are also highest.

## 03.6 Primary users and buyers

| Role | Job | Product outcome | Main objection |
|---|---|---|---|
| Training infrastructure engineer | keep runs moving and understand recurrence | faithful experiment and contract | integration burden |
| Reliability engineer | choose next action under uncertainty | mechanism ledger and recovery assurance | native tools may be sufficient |
| Research platform engineer | preserve research schedule | lower incident and upgrade disruption | instrumentation risk |
| Engineering director | control compute and specialist time | measured value and repeatability | frequency and ROI |
| Cloud support engineer | reduce customer evidence loops | provider-native or federated artifact | unsafe code and private data |
| Hardware health engineer | test workload/device dependence | controlled source/substitute result | false RMA risk |
| Security/legal | constrain sensitive evidence | local/federated operation and explicit rights | source/data/checkpoint exposure |
| Procurement | approve young vendor | bounded deployment and continuity | startup and support risk |

## 03.7 Entry products

### Evidence and Incident Feasibility Assessment

Delivers:

- supported/unsupported decision;
- native-tool inventory;
- workload/evidence lock readiness;
- privacy and execution tier;
- closure-value qualification;
- candidate experiment budget;
- and a precise statement of what may remain unknowable.

### Bounded Failure Reproduction and Recovery Assurance

Delivers:

- complete native baseline;
- first observed boundary;
- controlled experiments and hypothesis ledger;
- Minimum Faithful Experiment or evidence-only result;
- Recovery Assurance;
- incident contract;
- and value record.

### Change Qualification

Runs one or more failure-derived or explicitly purchased critical-workload contracts against a named change.

### Provider Evidence Gateway

Only after the customer-local product works. Provides isolated runners, native support intake, provider-local evidence, and qualification/disposition workflows.

## 03.8 Flagship incident pack

### `PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1`

Supported mechanisms:

- one actor omits a declared collective boundary;
- actors call incompatible collective types or payload contracts;
- data-dependent control flow changes collective order;
- a data-loader/checkpoint path prevents one actor from reaching the boundary;
- a process exits or illegally changes membership;
- a bounded runtime/kernel lifecycle condition prevents progress and can be separated from ordinary delay.

Required commercial outcome beyond native tooling:

- reconstruct or preserve the upstream trigger;
- materially reduce execution/access burden;
- distinguish omission, delay, lifecycle failure, and infrastructure failure;
- execute a faithful local/federated experiment;
- evaluate the guard or recovery;
- create a durable contract or upstream/native support artifact.

Explicit non-support:

- generic network health;
- generic NCCL tuning;
- broad straggler detection;
- every deadlock;
- universal kernel hang analysis;
- hardware certification;
- arbitrary pipeline/expert-parallel graphs in the first release.

## 03.9 Second pack

### `CHECKPOINT_RESUME_STATE_CONSISTENCY_V1`

This pack evaluates whether a recovery preserved declared state properties after checkpoint, checkpointless, elastic, in-process, or node-replacement recovery.

Required properties are selected per workload:

- checkpoint completeness and digest;
- optimizer and scheduler state;
- RNG and sampler state;
- data cursor and replay/skip behavior;
- model and optimizer shard ownership;
- process-group membership;
- loss, gradient, and tensor sentinels;
- throughput and resource behavior;
- short-run trajectory comparison;
- rollback;
- and observation-window recurrence.

It returns `QUALITY_NOT_ESTABLISHED` when long-horizon model quality was not measured.

## 03.10 Future pack selection

The next pack is selected from evidence, not aspiration.

Candidate score:

```text
material severity
× recurrence or qualification trigger
× native/bundled gap
× evidence availability
× one-party value
× pack reuse
× customer commitment
÷ security, adapter, and experiment burden
```

Candidates:

- numerical divergence through an `OperatorAlignmentBackend`;
- scale-dependent failure through a `ScaleEmulationBackend`;
- workload-specific device dependence with a provider/hardware partner;
- fail-slow reproduction only when existing tools find the slow component but cannot close it;
- heterogeneous post-training actor state after the core IR proves extensible.

## 03.11 Replaceable backend requirements

Each backend declares:

```yaml
backend:
  name: operator-alignment
  implementation: opguard-compatible-or-native
  version: sha256:...
  supportedWorkloadClasses: []
  evidenceConsumed: []
  evidenceProduced: []
  identityAssumptions: []
  knownLosses: []
  perturbationProfile: {}
  strongestPermittedClaim: OBSERVED_BOUNDARY_ONLY
```

No backend owns final truth. TrainCapsule's trust layer decides what conclusions are permitted.

The product must be able to integrate, replace, or upstream a backend without rewriting:

- identity;
- case ledger;
- experiment contracts;
- faithfulness;
- applicability;
- recovery assurance;
- qualification;
- or security policy.

## 03.12 Product surfaces

### Required CLI

```bash
traincapsule doctor workload.yaml
traincapsule lock workload.yaml
traincapsule ingest --incident TC-... --from flight-recorder,nccl,slurm,dcgm
traincapsule analyze TC-...
traincapsule experiment plan TC-... --budget policy.yaml
traincapsule experiment run TC-... --runner customer-local
traincapsule reduce TC-...
traincapsule recovery assess TC-...
traincapsule contract create TC-...
traincapsule qualify CONTRACT --change change.lock.json
traincapsule export TC-... --target pytorch|provider|hardware|customer
traincapsule verify ARTIFACT
```

### Thin local viewer

The viewer may display:

- exact identity;
- capture completeness and perturbation;
- event/actor graph;
- last consistent and first observed inconsistent boundary;
- hypothesis and experiment ledger;
- accepted/rejected reductions;
- replay/applicability envelope;
- recovery properties;
- contract state and drift;
- raw evidence under policy.

It must not become a generic monitoring product.

## 03.13 Product status model

```text
CLOSURE_NOT_ECONOMIC
SUPPORTED_FOR_BOUNDED_ANALYSIS
EVIDENCE_ONLY_BOUNDARY
MECHANISM_SUPPORTED
MECHANISM_REPRODUCED
COMPONENT_DEPENDENCE_SUPPORTED
MINIMUM_FAITHFUL_EXPERIMENT_FOUND
NO_FAITHFUL_EXPERIMENT_WITHIN_BUDGET
RECOVERY_PROPERTIES_PASSED
RECOVERY_UNSAFE_OR_UNPROVEN
CONTRACT_CREATED
QUALIFICATION_PASS_WITHIN_ENVELOPE
TECHNICAL_VALUE_ONLY
MATERIAL_VALUE_VERIFIED
UNSUPPORTED
UNKNOWN
```

Status must remain consistent across CLI, API, viewer, reports, and exports.

## 03.14 Product acceptance criteria

The local technical alpha is complete only when a clean environment can:

1. verify exact workload and product identity;
2. ingest a real native Flight Recorder path without silent loss;
3. detect partial/corrupt evidence;
4. locate the correct observed boundary on hidden controlled cases;
5. outperform the native baseline on at least one completed outcome;
6. find and verify a lower-cost faithful experiment;
7. preserve the declared contract and applicability envelope;
8. evaluate named recovery properties;
9. create and rerun an incident contract after a stack change;
10. refuse unsupported hardware or causal attribution;
11. operate with customer-local raw data;
12. execute safely without founder-only hidden edits.

The commercial product is validated only after a qualified external organization receives material value and takes a second commercial action.

## 03.15 Build versus proof

The full local product described above is authorized before customer proof.

The following remain claims rather than build tasks:

- customers will pay a specific price;
- a provider will accept the artifact;
- the same pack will generalize across companies;
- annual qualification will recur often enough;
- the market is large enough;
- a strategic buyer will acquire the company.

The repository must mark them as `UNPROVEN_COMMERCIAL_CLAIM` until real evidence exists.

## 03.16 Detailed customer and commercial qualification

### 04 — Customer, Buyer, and Commercial Wedge

#### 04.1 One-party value requirement

A qualified buyer must be able to obtain value from TrainCapsule using assets and authority it already controls.

The minimum purchase rationale is:

```text
we operate important distributed workloads
+ native tools leave some incidents unresolved or expensive
+ we can execute customer-local experiments
+ a lower-cost faithful case and recovery assurance change our decisions
= internal value without waiting for another company
```

External provider, framework, or hardware participation can increase value. It cannot be a prerequisite for the first sale.

#### 04.2 Primary initial segment

The strongest initial account is a **workload platform or model organization with an internal AI-infrastructure team serving multiple workloads or research groups**.

Required characteristics:

- repeated distributed PyTorch workloads;
- at least one material incident in recent operating history and credible recurrence or stack-change exposure;
- direct control over job launch, images, checkpoints, and evidence capture;
- a platform/reliability owner with authority to run experiments;
- customer-local or VPC execution permitted;
- native diagnostic tools already in use, allowing a fair baseline;
- enough workload diversity for a second case;
- and a budget owner who values research schedule, compute utilization, or engineering capacity.

Preferred characteristics:

- multi-cloud or multi-provider operation;
- several internal model teams;
- repeated framework/runtime upgrades;
- expensive or long-running workloads;
- limited specialist headcount relative to incident load;
- recurring provider escalations;
- or regulated/private data that makes external support difficult.

#### 04.3 Secondary segment: managed training platform or neocloud

A provider is qualified when it:

- sees incidents across several customers;
- competes on support quality and time to restored service;
- lacks a complete internal replay/reduction system;
- can deploy customer-isolated runners;
- can expose enough provider-local evidence through policy;
- and has an economic sponsor in reliability, support engineering, customer success, or infrastructure operations.

The provider offer should initially be framed as:

> **Evidence Intake and Reproduction Workflow for Difficult Customer Incidents**

Do not lead with neutral blame allocation. Lead with:

- fewer log-collection rounds;
- smaller provider-executable experiments;
- faster routing to the correct internal team;
- cleaner customer/provider evidence separation;
- recovery-assurance records;
- and lower repeat-ticket burden.

#### 04.4 Tertiary segments

##### Accelerator or systems vendor

Potential value:

- workload-specific hardware/software cases;
- driver and firmware regression artifacts;
- reduced false RMA and unnecessary quarantine;
- field-engineering enablement.

Constraint: strict liability and evidence requirements; high internal capability.

##### Framework/runtime maintainers

Potential value:

- reduced regressions;
- exact environment and workload contract;
- better issue quality.

Constraint: maintainers normally expect useful reproductions to be open source and may not be economic buyers.

##### Universities and research clusters

Potential value:

- limited specialist staff;
- recurring cluster incidents;
- research continuity.

Constraint: lower budget and procurement complexity.

##### Frontier labs and hyperscalers

Potential value is high, but these are poor assumptions for an initial sale because internal capability, security, data access, and vendor review are strongest.

#### 04.5 Explicit disqualifiers

Reject or defer accounts when:

- distributed incidents are rare and low value;
- jobs are short and disposable;
- fewer accelerators are used and the account has no aggregated workload volume;
- the provider fully owns troubleshooting and the customer has no evidence access;
- the customer cannot define the incident predicate or recovery properties;
- native tools already produce an adequate reproducer and recovery result;
- no one can run controlled experiments;
- raw data must leave the environment for the product to work;
- there is no substitute/canary capacity and the pack requires it;
- the customer demands guaranteed root cause, hardware certification, or universal model correctness;
- integration cost exceeds plausible net benefit;
- or the account wants production auto-remediation before trust exists.

#### 04.6 Economic buyer and budget line

Possible budget owners:

- Head or Director of AI Infrastructure;
- Head of Training or Research Platform;
- VP Infrastructure;
- Reliability or Production Engineering leader;
- Managed Training or Cloud Support leader;
- Hardware Enablement or Field Engineering leader.

Possible budget lines:

- reliability engineering;
- developer/research infrastructure;
- cloud support operations;
- protected production/research workloads;
- incident response;
- customer success for large compute accounts;
- hardware qualification or RMA operations.

Do not rely on a generic “observability” budget. TrainCapsule should be purchased for a named incident outcome, critical-workload program, or support workflow.

#### 04.7 Buyer, champion, operator, blocker

| Role | Required action | Value | Primary objection |
|---|---|---|---|
| Training/platform engineer | install/import/run experiments | lower-cost case and state assurance | setup and another tool |
| Reliability engineer | own incident process | bounded hypotheses and durable contract | native tooling may suffice |
| Research lead | permit workload integration | less schedule disruption | instrumentation risk |
| Infrastructure director | fund work | recovered compute and expert capacity | incident frequency/ROI |
| Security/legal | approve data path | local execution and policy | code/data sensitivity |
| Cloud/provider support | consume native export | smaller evidence package | custom format or unsafe code |
| Hardware health | evaluate device dependence | workload-specific A/B evidence | false attribution |
| Procurement | approve vendor | bounded scope and private deployment | startup continuity and liability |

#### 04.8 Buying triggers

Strong triggers:

- an active incident native tools have not closed;
- repeated NCCL timeouts with ambiguous upstream cause;
- a resumed job whose checkpoint or training state is disputed;
- a provider/customer escalation with repeated evidence requests;
- a runtime/driver/framework upgrade that previously caused a costly failure;
- a workload migration across cloud, GPU generation, or topology;
- a recurring private incident that cannot be shared upstream;
- or a platform team spending material senior time on repeated one-off investigations.

Weak trigger:

- general interest in “better GPU reliability” with no recent case, protected workload, or owner.

#### 04.9 Initial paid engagement qualification

A first engagement requires:

- one named operator;
- one active or reconstructable incident;
- exact supported stack and environment;
- native-tool baseline;
- privacy and data-rights decision;
- permission to measure time and cost;
- a bounded outcome and stop condition;
- access to required local compute;
- and a decision date for a second use or protected-workload contract.

Free custom engineering without a case, baseline, and continuation decision is not a design partnership.

#### 04.10 Commercial account score

Use a score only as a decision aid. Do not present it as a validated predictive model.

| Dimension | High score |
|---|---|
| Incident severity | blocks a critical program or consumes substantial synchronized compute |
| Recurrence/volume | several jobs, teams, or customer incidents |
| Native-tool gap | no lower-cost faithful case or state assurance |
| Deployment authority | customer controls image, launcher, evidence, and experiments |
| Data feasibility | local execution satisfies policy |
| Second-case availability | another incident or stack-change qualification exists |
| Budget authority | named buyer and budget line |
| Productization fit | supported stack and pack, limited custom code |
| External handoff need | useful but not required for internal value |

An account with severe pain but no deployment authority is not a first customer.

---

## 03.17 Detailed initial-pack and scope discipline

### 05 — Initial Incident Pack and Scope Discipline

#### 05.1 One flagship pack

The first commercial-quality pack is:

> **Pre-collective control-flow and distributed-lifecycle contract failure**

It covers a bounded family in which ranks or actors cease to satisfy a declared collective or lifecycle contract because of an upstream control-flow, data-loader, checkpoint, process, or scheduling event.

##### Supported mechanisms

- one rank omits a collective;
- ranks invoke different collective types or payload contracts;
- a data-dependent branch creates divergent collective order;
- a data-loader or checkpoint path prevents one rank from reaching the collective;
- a process exits or changes membership before the expected operation;
- a process group is created, destroyed, or reused inconsistently;
- a bounded runtime/kernel lifecycle event prevents progress and can be distinguished from an ordinary delayed rank.

##### Not included

- generic network diagnosis;
- arbitrary NCCL performance tuning;
- broad fail-slow analysis;
- every deadlock;
- universal kernel hang analysis;
- hardware certification;
- arbitrary pipeline/expert-parallel topologies;
- model-quality failures without a declared distributed contract.

#### 05.2 Why this pack is still viable despite Flight Recorder

Flight Recorder is a mandatory baseline and evidence source. TrainCapsule receives no commercial credit for duplicating:

- collective history;
- missing-rank detection;
- mismatched collective type/shape reporting;
- or source-line identification already available natively.

The pack succeeds only when it performs additional work:

1. reconstruct the upstream trigger or provide a bounded experiment plan;
2. preserve the relevant data/control-flow relation locally;
3. reduce actors, steps, model scope, and data to a cheaper faithful experiment;
4. distinguish omission, delay, process failure, and infrastructure failure;
5. evaluate the proposed guard/recovery state;
6. install an incident contract with a valid applicability envelope;
7. generate a native support/upstream artifact.

#### 05.3 First pack evidence requirements

Required where applicable:

- exact c10d/Flight Recorder version and configuration;
- per-rank collective sequence and lifecycle;
- process-group identity and membership;
- CPU stack and semantic training marker before the boundary;
- global step/microbatch/phase;
- process exit/signal state;
- scheduler placement and lifecycle;
- data-shard/sampler reference when the branch is data-dependent;
- checkpoint operation state when relevant;
- recorder completeness and perturbation profile;
- clean control.

Optional but potentially required by the mechanism:

- selected tensor signature;
- data-loader queue state;
- kernel interval;
- NCCL RAS or network evidence;
- source and substitute node execution.

#### 05.4 First pack incident predicate

```yaml
incidentPack: PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1
predicate:
  expected:
    allRequiredActorsReachContractBoundary: true
    collectiveTypeAgreement: true
    collectivePayloadAgreement: true
    processGroupMembershipAgreement: true
  observedFailure:
    any:
      - actorOmitsBoundary
      - actorReordersBoundary
      - payloadContractDiffers
      - actorCannotProgressToBoundary
      - membershipChangesIllegally
faithfulness:
  preserve:
    - triggeringControlOrDataRelation
    - firstObservedBoundaryClass
    - requiredActorGroupStructure
  strongestClaim:
    - OBSERVED_BOUNDARY_ONLY
    - MECHANISM_SUPPORTED
    - MECHANISM_REPRODUCED
```

#### 05.5 Native baseline protocol

For every external case, execute:

```text
A. Customer's ordinary logs and process
B. Current stable Flight Recorder / native trace analyzer
C. Native provider or accelerator diagnostic workflow
D. TrainCapsule using exactly the same available evidence
E. TrainCapsule with any additional pre-approved capture
```

Record:

- setup time;
- evidence collection time;
- time to first useful boundary;
- time to discriminating experiment;
- time to faithful reproducer;
- operator hours;
- GPU cost;
- external handoffs;
- recovery assurance;
- and recurrence handling.

TrainCapsule must be evaluated against `C`, not merely against raw logs.

#### 05.6 First pack release gate

A commercial-quality pack requires:

- controlled fault suite including clean controls;
- malformed and partial evidence behavior;
- correct observed boundary on hidden cases;
- no direct observed-boundary-to-blame mapping;
- at least one faithful reduction beyond native rank/source-line output;
- customer-local replay;
- recovery-assurance result;
- incident contract creation;
- security and perturbation tests;
- external operator execution;
- and a documented case where the outcome exceeds native tools.

#### 05.7 Second pack selection

Do not pre-commit to a broad order. Select the next pack using qualified incident evidence.

Candidate A — **Checkpoint/resume state inconsistency**

- strong alignment with Recovery Assurance;
- recurring after node/process recovery and stack changes;
- requires checkpoint, optimizer, RNG, sampler, and data-cursor contracts;
- may create direct internal value without provider acceptance.

Candidate B — **First numerical divergence**

- high value but harder replay, privacy, and instrumentation;
- requires tensor-signature policy, precision identity, and tolerance controls;
- can be amplified by iterative training or post-training.

Candidate C — **Workload-specific suspected hardware corruption**

- potentially high strategic value;
- must be partner-led with matched substitute hardware and strict liability controls;
- not suitable as a broad self-serve pack initially.

Candidate D — **Fail-slow mechanism reproduction**

- crowded by native/platform observability and production systems;
- pursue only when a buyer provides a slowdown that current tools identify but cannot reproduce or close.

Selection evidence:

- number of qualified incidents;
- materiality;
- native-tool gap;
- evidence availability;
- repeatability;
- security feasibility;
- pack reuse potential;
- and buyer commitment.

#### 05.8 Unsupported surface policy

When an incident falls outside the released pack:

```text
UNSUPPORTED_KNOWN_FAMILY
NEW_FAMILY_RESEARCH_CANDIDATE
INSUFFICIENT_EVIDENCE
SECURITY_OR_RIGHTS_BLOCKED
OUT_OF_SCOPE_SERVICE_REQUEST
```

Do not silently extend the pack through bespoke code and then count the case as mature software.

---