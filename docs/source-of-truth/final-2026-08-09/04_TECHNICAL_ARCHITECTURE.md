# 04 — Technical Architecture

- **Document date:** 9 August 2026
- **Status:** **Final source of truth**
- **Architecture style:** local-first, import-first, federated-by-default for sensitive execution
- **Stable company boundary:** identity, evidence integrity, experiments, faithfulness, recovery assurance, incident contracts, qualification, and policy
- **Replaceable primitives:** capture, trace analysis, operator alignment, scale emulation, health diagnostics, and provider execution
- **Product relationship:** Close produces bounded evidence and contracts; Qualify reruns them against change; Exchange transports only policy-approved results.

## 04.1 Architectural decision

TrainCapsule is a **customer-local failure reproduction and change-qualification system**.

The first product runs inside the workload owner's or provider's trust boundary. Raw source, data, checkpoints, tensors, topology, and detailed incident evidence remain local unless explicit policy permits export.

The first product is not:

- a hosted multi-tenant observability service;
- an always-on cloud telemetry collector;
- a new GPU scheduler;
- a managed GPU fleet;
- or an autonomous production-control plane.

## 04.2 Logical architecture

```text
WORKLOAD READINESS + IDENTITY
  workload graph · source/image/component locks · evidence capability · policy
                               │
                               ▼
NATIVE EVIDENCE GATEWAY
  Flight Recorder · NCCL · scheduler · device · checkpoint · app markers
                               │
                               ▼
INCIDENT INTERMEDIATE REPRESENTATION
  actors · resources · phases · state channels · causal constraints · gaps
                               │
                               ▼
BACKEND ADAPTER LAYER
  collective trace · operator alignment · scale emulation · HW dependence
                               │
                               ▼
MECHANISM + EXPERIMENT PLANNER
  observed boundary · hypotheses · controlled tests · information/cost budget
                               │
                               ▼
MINIMUM FAITHFUL EXPERIMENT COMPILER
  actors · steps · data · model · topology · versions · hardware · services
                               │
                               ▼
LOCAL / FEDERATED EXPERIMENT RUNNER
  source · substitute · structural · statistical · customer/provider boundary
                               │
                               ▼
DISPOSITION + RECOVERY ASSURANCE
  mechanism · alternatives · state properties · canary · rollback · UNKNOWN
                               │
                               ▼
INCIDENT CONTRACT + QUALIFICATION ENGINE
  applicability · drift · expiry · stack-change runs · recurrence · revocation
                               │
                               ▼
OPTIONAL EXCHANGE
  upstream/provider/vendor native exports · signed bounded attestations
```

## 04.3 Four-layer productization model

### Layer A — stable trust core

The trust core owns:

- canonical serialization and content identity;
- workload, environment, change, evidence, experiment, and contract schemas;
- capture completeness and evidence provenance;
- incident IR;
- hypotheses and experiment ledger;
- faithfulness and applicability validation;
- result-state semantics;
- Recovery Assurance;
- contract drift, expiry, and revocation;
- policy, audit, and value records.

Ordinary upstream version changes may not require this layer to change.

### Layer B — replaceable adapters and backends

Adapters and backends consume or execute external systems:

- PyTorch Flight Recorder/c10d traces;
- NCCL RAS/Inspector and provider communication telemetry;
- DCGM/NVML/XID/ECC/device evidence;
- Slurm first, Kubernetes later;
- checkpoint implementations;
- OpGuard-compatible operator alignment;
- PrismLLM-compatible scale emulation;
- provider-specific execution or support APIs;
- hardware/fleet health systems.

Each declares exact versions, fields, assumptions, losses, security boundaries, and permitted claims.

### Layer C — declarative incident and qualification packs

A pack defines:

- symptom and economic qualification;
- required/optional evidence;
- incident predicate;
- invariants and mechanism classes;
- experiment templates;
- legal reductions;
- faithfulness contract;
- recovery properties;
- applicability and expiry;
- native exports;
- hidden controlled faults.

Released packs cannot contain customer-specific executable code in the trust path.

### Layer D — customer policy and private references

Customer-controlled configuration includes:

- workload manifest;
- local source/data/checkpoint references;
- evidence access;
- privacy and retention;
- experiment budgets;
- qualification triggers;
- recovery properties;
- permitted actions and exports;
- legal/data-rights terms.

## 04.4 Core backend interfaces

```python
class EvidenceBackend(Protocol):
    def capabilities(self, lock: WorkloadLock) -> CapabilityReport: ...
    def ingest(self, request: IngestRequest) -> EvidenceBundle: ...

class BoundaryBackend(Protocol):
    def locate(self, ir: IncidentIR, policy: BoundaryPolicy) -> BoundaryResult: ...

class ExperimentBackend(Protocol):
    def plan(self, case: CaseState, budget: ExperimentBudget) -> list[ExperimentPlan]: ...
    def execute(self, plan: ExperimentPlan, runner: RunnerRef) -> ExperimentResult: ...

class EmulationBackend(Protocol):
    def materialize(self, plan: ScaleEmulationPlan) -> EmulatedEnvironment: ...

class RecoveryBackend(Protocol):
    def assess(self, request: RecoveryAssessmentRequest) -> RecoveryAssuranceRecord: ...

class ExportBackend(Protocol):
    def render(self, case: CaseState, target: ExportTarget) -> ExportArtifact: ...
```

No backend may directly emit `ROOT_CAUSE_CONFIRMED`, `HARDWARE_DEFECT`, or `SAFE_RECOVERY`. It emits observations and experiment results. The trust core maps those results to bounded states.

## 04.5 Domain model

Required entities:

| Entity | Purpose |
|---|---|
| `WorkloadManifest` | intended workload and policy |
| `WorkloadLock` | immutable execution identity |
| `ChangeLock` | exact candidate stack/infrastructure change |
| `EvidenceCapabilityReport` | what can and cannot be observed |
| `EvidenceArtifact` | immutable raw or derived evidence |
| `IncidentIR` | normalized actor/resource/state representation |
| `ObservedDivergenceRecord` | first observed inconsistency and gaps |
| `HypothesisRecord` | candidate mechanism and current evidence |
| `ExperimentPlan` | controlled intervention and permitted inference |
| `ExperimentResult` | immutable execution outcome |
| `ReductionTrial` | accepted/rejected simplification |
| `MinimumFaithfulExperiment` | best valid experiment found within budget |
| `ApplicabilityEnvelope` | exact limits of the result |
| `ComponentDispositionRecord` | bounded component/mechanism conclusion |
| `RecoveryAssuranceRecord` | named state properties and outcomes |
| `WorkloadIncidentContract` | failure-derived executable/federated contract |
| `QualificationRun` | contract execution against a change |
| `ExportArtifact` | native or portable handoff |
| `ValueRecord` | measured technical and economic result |
| `CaseLedgerEntry` | denominator-preserving case history |

## 04.6 Incident IR

The IR must not assume every workload is one flat set of symmetric DDP ranks.

```text
IncidentIR {
  workload_lock
  actor_groups[]
  actors[]
  resources[]
  phases[]
  state_channels[]
  events[]
  causal_constraints[]
  time_intervals[]
  evidence_gaps[]
  incident_predicate
  observed_divergences[]
  hypotheses[]
  experiment_history[]
}
```

Actor examples:

- DDP/FSDP rank;
- tensor/pipeline/context/expert-parallel rank;
- data-loader worker;
- checkpoint writer;
- rollout worker;
- trainer actor;
- reward or inference service;
- scheduler task;
- GPU, NIC, node, storage path.

The initial adapter implements c10d collective actors. Future actor classes must be added through adapters without changing result semantics.

## 04.7 Content-addressed evidence

```text
store/
├── objects/sha256/<prefix>/<digest>
├── refs/workloads/
├── refs/incidents/
├── refs/contracts/
├── refs/qualifications/
├── quarantine/
└── tmp/
```

Rules:

- objects are immutable and atomically written;
- references use digests, not untrusted host paths;
- every transformation records parent digests and tool versions;
- private raw artifacts never automatically enter exports;
- incomplete or corrupted artifacts remain explicit;
- repeated execution appends results and never overwrites history;
- deletion, expiry, and revocation propagate through provenance.

## 04.8 Local/federated deployment

### Local single-organization deployment

```text
training cluster
  ├── native evidence sources
  ├── optional bounded TrainCapsule markers
  ├── local evidence store
  └── local runner
          │ immutable refs
          ▼
local TrainCapsule control service
  ├── case state
  ├── experiment planner
  ├── reduction compiler
  ├── recovery assurance
  └── contract registry
```

### Federated experiment

```text
TrainCapsule signs experiment request
        ↓
remote policy engine verifies signer, scope, and resources
        ↓
remote runner resolves approved private references
        ↓
sandbox executes under exact environment identity
        ↓
runner signs bounded result and evidence digests
        ↓
origin verifier checks identity, policy, and result
```

This is the default when source, data, weights, device telemetry, or provider evidence cannot leave their owning boundary.

## 04.9 Environment availability

Every execution lane declares:

```text
SOURCE_EXACT
SOURCE_EQUIVALENT_WITH_DECLARED_DIFFERENCES
SOURCE_ADJACENT
TOPOLOGY_PRESERVING_EMULATION
STRUCTURAL_SUBSTITUTE
CUSTOMER_LOCAL_ONLY
PROVIDER_LOCAL_ONLY
UNAVAILABLE
```

The planner must abort when expected experiment cost, elapsed time, security risk, or capacity conflict exceeds the customer's decision value.

TrainCapsule does not purchase a broad historical GPU fleet before recurring utilization is demonstrated.

## 04.10 Minimum Faithful Experiment compiler

The compiler searches across:

- actors/ranks and process groups;
- node/topology class;
- step/event window;
- microbatches and data records;
- checkpoint delta;
- model layers/experts/operator subgraph;
- tensor shapes and relevant values;
- versions and configuration;
- hardware placement;
- concurrency/background load;
- external services.

Optimization is multi-objective:

```text
GPU count
+ wall-clock duration
+ setup complexity
+ private-data volume
+ hardware specificity
+ operator effort
+ receiver access burden
```

Every candidate has:

- transformation;
- preconditions;
- must-preserve set;
- validator identity;
- experiment results;
- reject reason or accepted status.

Global minimality is never claimed unless the bounded search space proves it.

## 04.11 Experiment scheduler

Every task has:

- immutable inputs;
- exact runner and privacy zone;
- GPU/CPU/memory/storage/network budget;
- retry class;
- infrastructure versus semantic status;
- cancellation and timeout;
- permitted conclusion;
- output digests.

Task classes:

```text
EVIDENCE_FETCH
ENVIRONMENT_MATERIALIZATION
SOURCE_EXPERIMENT
SUBSTITUTE_EXPERIMENT
SCALE_EMULATION
REDUCTION_TRIAL
VERSION_BISECTION
RECOVERY_CANARY
QUALIFICATION_RUN
FEDERATED_HANDOFF
```

Infrastructure retries cannot turn non-reproduction into a pass or hide an invalid environment.

## 04.12 Recovery and qualification

Recovery Assurance and Qualify share one execution engine but different policies.

Recovery evaluates:

- state integrity;
- continuity;
- numerical sentinels;
- throughput/resource behavior;
- canary;
- rollback;
- observation window.

Qualify evaluates:

- whether the old incident recurs;
- whether a different boundary fails;
- whether environment drift invalidates the contract;
- whether private references remain available;
- whether the result remains within the applicability envelope.

A passing reduced test alone cannot authorize production release when the mechanism requires topology- or scale-preserving evidence.

## 04.13 Security architecture

Minimum controls:

- non-root sandbox;
- no arbitrary host mounts;
- network disabled by default;
- resource and expansion limits;
- trusted launch templates;
- customer code treated as untrusted;
- archive traversal/symlink/device-file rejection;
- dependency, license, secret, and vulnerability scans;
- pinned dependencies and OCI digests;
- SBOM and signed provenance;
- no AI model access to private evidence without explicit policy;
- recovery actions disabled by default;
- complete audit.

## 04.14 Initial technology choices

| Layer | Initial choice | Rule |
|---|---|---|
| Core | Python 3.12 | optimize for PyTorch integration and correctness |
| Schema | Pydantic v2 + JSON Schema | one canonical contract |
| CLI | Typer/Rich | primary operator surface |
| API | FastAPI | only for long-running local jobs |
| Metadata | SQLite WAL | zero-ops local deployment |
| Artifacts | content-addressed filesystem | S3 abstraction later |
| Workers | Docker/Podman | customer-local isolation |
| Cluster | Slurm first | Kubernetes only after demand |
| Hot path | C++/CUDA only after profiling | no premature native rewrite |
| High-volume core | Rust only after measured need | not an architectural identity |
| Tests | pytest, Hypothesis, mutation, hidden faults | deterministic gates before model review |
| Provenance | OCI artifacts, SBOM, Sigstore/in-toto/SLSA-compatible attestations | use standards, do not invent crypto |

## 04.15 Repository structure

```text
traincapsule/
├── README.md
├── SECURITY.md
├── docs/
│   ├── source-of-truth/
│   ├── architecture/
│   ├── adr/
│   ├── operations/
│   ├── product/
│   ├── evidence/
│   └── commercial/
├── schemas/
├── packages/
│   ├── domain/
│   ├── identity/
│   ├── evidence/
│   ├── incident_ir/
│   ├── trust/
│   ├── planner/
│   ├── reducer/
│   ├── runner/
│   ├── recovery/
│   ├── contracts/
│   ├── qualify/
│   ├── exchange/
│   ├── cli/
│   └── api/
├── backends/
│   ├── flight_recorder/
│   ├── nccl/
│   ├── dcgm/
│   ├── slurm/
│   ├── checkpoint/
│   ├── operator_alignment/
│   └── scale_emulation/
├── incident-packs/
│   ├── pre_collective_lifecycle_v1/
│   └── checkpoint_resume_state_v1/
├── policies/
├── examples/
├── apps/local-viewer/
├── tests/
│   ├── unit/
│   ├── property/
│   ├── mutation/
│   ├── fault-injection/
│   ├── replay/
│   ├── qualification/
│   ├── security/
│   └── e2e/
├── private-gates-reference/
└── containers/
```

Private gates used by the autonomous factory remain outside builder-visible repository paths.

## 04.16 Performance and reliability budgets

Initial internal gates, not industry facts:

| Operation | Target |
|---|---:|
| Import-only production overhead | effectively zero beyond native sources |
| Optional healthy capture mean overhead | ≤1% target |
| Optional healthy capture hard stop | >2% on supported path |
| Required evidence capture in controlled cases | ≥99% |
| Trigger-to-minimum-freeze | <30 seconds where infrastructure survives |
| 64-actor graph construction | <5 minutes |
| Small deterministic structural experiment | <5 minutes where workload permits |
| Cancellation of local worker | <10 seconds |
| False confirmed hardware attribution | zero |
| Public deterministic example | all declared repetitions pass |
| Qualification state consistency | identical across CLI/API/viewer/artifacts |

Mean overhead alone is insufficient. Tail latency, collective waits, incident rate, memory, CPU, storage, network, and output sentinels must be compared.

## 04.17 Architecture success test

The architecture succeeds when an independent clean or authorized local environment can:

1. verify workload, change, backend, pack, and product identities;
2. inspect exactly what evidence is present and missing;
3. reproduce or execute the declared experiment tier;
4. validate the faithfulness and applicability records;
5. inspect the observed boundary, alternatives, and experiment ledger;
6. evaluate the named recovery properties;
7. create and rerun an expiring incident contract;
8. run a qualification against a changed stack;
9. export a bounded native/federated artifact;
10. explain every `UNKNOWN`, omission, drift, and unsupported conclusion.

Anything less is a report generator or test harness, not the intended product.

## 04.18 Detailed product-plane architecture

### 03 — Final Product Architecture

#### 03.1 Product planes

```text
READINESS AND IDENTITY
  workload graph · component lock · evidence capability · privacy policy
                            │
                            ▼
NATIVE EVIDENCE GATEWAY
  Flight Recorder · NCCL · scheduler · device · checkpoint · application markers
                            │
                            ▼
INCIDENT INTERMEDIATE REPRESENTATION
  actors · resources · phases · state channels · causal constraints · gaps
                            │
                            ▼
MECHANISM AND EXPERIMENT PLANNER
  observed divergence · hypotheses · discriminating experiments · budget
                            │
                            ▼
MINIMUM FAITHFUL EXPERIMENT COMPILER
  rank/actor · step · data · model · topology · version · hardware reductions
                            │
                            ▼
FEDERATED REPLAY AND CONTROL RUNNER
  customer-local · provider-local · source/substitute · attested where supported
                            │
                            ▼
DISPOSITION AND RECOVERY ASSURANCE
  supported mechanism · alternatives · next owner · state checks · canary
                            │
                            ▼
INCIDENT CONTRACT REGISTRY
  applicability envelope · stack-change runs · drift · expiry · recurrence
                            │
                            ▼
OPTIONAL EXTERNAL EXCHANGE
  provider-native bundle · upstream test · signed disposition · RMA evidence
```

#### 03.2 Readiness and identity

##### Purpose

Determine what can be investigated before an incident and prevent the product from claiming evidence that the workload never captured.

##### Required outputs

- immutable repository and source-tree identity;
- container and package digests;
- framework, compiler, CUDA, NCCL, driver, firmware, and scheduler identity;
- accelerator and topology identity;
- distributed/parallelism graph;
- checkpoint, optimizer, RNG, sampler, and data-reference availability;
- evidence-source capability matrix;
- recorder perturbation profile;
- privacy and export policy;
- recovery-assurance property list;
- unsupported and unobservable boundaries.

##### Readiness states

```text
READY_FOR_DECLARED_PACK
READY_WITH_GAPS
IMPORT_ONLY
RECOVERY_ASSURANCE_PARTIAL
NOT_READY
UNSUPPORTED
```

Readiness means the declared incident pack has enough expected evidence. It is not certification that the workload is correct or failure-free.

#### 03.3 Native Evidence Gateway

The gateway imports rather than replaces first-party systems.

Initial sources:

- PyTorch Flight Recorder trace and dump configuration;
- NCCL RAS/Inspector or available collective telemetry;
- Slurm or Kubernetes process, node, and job events;
- DCGM/NVML/XID/ECC/thermal/power signals;
- checkpoint metadata and sharded-state identities;
- training-loop semantic markers;
- RNG, sampler, and data-shard references;
- optional tensor signatures;
- customer incident markers.

Every adapter declares:

```yaml
adapter:
  source: pytorch-flight-recorder
  upstreamVersionRange: ">=2.x,<3"
  adapterVersion: sha256:...
  fieldsConsumed: []
  fieldsDropped: []
  orderingGuarantees: []
  identityAssumptions: []
  knownLosses: []
  malformedInputPolicy: REJECT
  semanticAuthority: NONE
```

An adapter supplies observations. It does not establish causality.

#### 03.4 Incident Intermediate Representation

The IR must support current c10d traces and future heterogeneous actor systems without pretending to model every internal event.

```text
IncidentIR {
  workload_lock
  actor_groups[]
  actors[]
  resources[]
  phases[]
  state_channels[]
  events[]
  causal_constraints[]
  synchronized_time_intervals[]
  evidence_gaps[]
  incident_predicate
  observed_divergences[]
  hypotheses[]
  experiment_history[]
}
```

##### Core actor examples

- DDP/FSDP rank;
- tensor/pipeline/context/expert parallel rank;
- data-loader worker;
- checkpoint writer;
- rollout worker;
- trainer actor;
- reward/model service;
- scheduler task;
- GPU, host, NIC, storage path.

##### Core edge examples

- same-actor program order;
- collective membership;
- producer/consumer tensor relation;
- checkpoint/restore relation;
- sampler/data ownership;
- actor placement;
- weight synchronization;
- scheduler/process lifecycle;
- resource-path relation;
- explicitly instrumented control-flow relation.

Wall-clock order alone does not establish causality.

#### 03.5 Mechanism and experiment planner

The planner maintains a hypothesis ledger and chooses the next experiment by expected information gain, cost, safety, and disclosure risk.

```python
experiment_utility = (
    expected_hypothesis_separation
    * decision_value
    * execution_feasibility
) / (
    gpu_cost
    + engineer_time
    + privacy_risk
    + perturbation_risk
    + elapsed_time
)
```

This formula is a planning heuristic, not a claim that uncertainty or privacy can be measured perfectly.

Every experiment declares:

- target hypotheses;
- held-constant variables;
- changed variable;
- incident predicate;
- expected outcomes;
- failure and infrastructure states;
- statistical policy;
- resource budget;
- data policy;
- and what conclusion is permitted.

#### 03.6 Minimum Faithful Experiment Compiler

The compiler searches across:

- actor/rank set;
- node and topology class;
- step or event window;
- microbatches and data records;
- checkpoint delta;
- model layers, experts, and operator subgraph;
- tensor shapes and values;
- process groups and communication payloads;
- runtime/driver/framework versions;
- hardware placement;
- concurrency and background load;
- and external service dependencies.

A candidate is accepted only when it preserves the declared faithfulness contract.

```yaml
faithfulness:
  incidentPredicate: COLLECTIVE_CONTRACT_VIOLATION
  observedBoundaryClass: PRE_COLLECTIVE_CONTROL_FLOW_DIVERGENCE
  requiredCausalPreconditions:
    - data-dependent-branch-trigger
    - process-group-membership
  requiredTopologyProperties:
    - cross-node: false
  requiredReplayTier: STRUCTURAL
  allowedNumericalVariation: declared
  privacyPolicy: CUSTOMER_LOCAL_DATA_REFERENCE
  applicabilityEnvelope: sha256:...
```

##### Optimization objective

The compiler minimizes a weighted vector, not one scalar:

```text
GPU count
wall-clock duration
setup complexity
private-data volume
hardware specificity
receiver access burden
operator effort
```

The output records the best candidate found, all rejected candidates, the search budget, and why search stopped.

#### 03.7 Federated Replay and Control Runner

##### Default execution modes

1. **Customer-local runner:** raw workload and evidence remain in the owning environment.
2. **Provider-local runner:** provider-only telemetry and hardware controls remain with the provider.
3. **Sanitized portable runner:** only after replay-preserving sanitization.
4. **Attested confidential runner:** optional on supported confidential-computing hardware and deployment modes.
5. **Public runner:** only for fully public or legally sanitized cases.

##### Required terminal states

```text
REPRODUCED_WITHIN_ENVELOPE
NOT_REPRODUCED_WITHIN_ENVELOPE
INVALID_EXPERIMENT
ENVIRONMENT_MISMATCH
INFRASTRUCTURE_ERROR
POLICY_DENIED
PRIVATE_REFERENCE_UNAVAILABLE
UNKNOWN
```

`NOT_REPRODUCED_WITHIN_ENVELOPE` never means the incident is absent outside the tested envelope.

#### 03.8 Causal and component disposition

TrainCapsule may emit:

```text
OBSERVED_BOUNDARY_ONLY
MECHANISM_SUPPORTED
MECHANISM_REPRODUCED
COMPONENT_DEPENDENCE_SUPPORTED
MULTI_COMPONENT_INTERACTION
ALTERNATIVES_REMAIN
UNATTRIBUTED
UNKNOWN
```

Component classes include:

- application control flow;
- data/sampler;
- checkpoint/restore;
- numerical/precision;
- framework/distributed runtime;
- compiler/generated kernel;
- communication library;
- GPU kernel or device;
- host CPU/memory;
- network/fabric;
- storage;
- scheduler/co-tenancy;
- external service;
- multi-component interaction.

The customer or receiving organization retains authority for warranty, service credit, or final ownership decisions.

#### 03.9 Recovery Assurance

Recovery Assurance evaluates selected properties rather than declaring universal safety.

##### Property groups

- artifact integrity;
- checkpoint completeness;
- optimizer and scheduler state;
- RNG and sampler continuity;
- data cursor correctness;
- model/shard ownership;
- process-group membership;
- numerical sentinels;
- loss and gradient envelopes;
- throughput and latency;
- clean controls;
- rollback;
- and recurrence during the observation window.

##### Result states

```text
RECOVERY_NOT_EVALUATED
RECOVERY_PATH_EXECUTED
STATE_PROPERTIES_PASSED
REDUCED_CANARY_PASSED
PRODUCTION_LIKE_CANARY_PASSED
OBSERVATION_WINDOW_PASSED
QUALITY_NOT_ESTABLISHED
PERFORMANCE_REGRESSION
RECURRENCE_OBSERVED
UNSAFE_OR_UNPROVEN
UNKNOWN
```

#### 03.10 Incident Contract Registry

A confirmed incident may become a failure-derived contract.

Each contract contains:

- incident predicate;
- mechanism or bounded observed boundary;
- faithfulness evidence;
- applicability envelope;
- required private references;
- execution policy;
- expected outcomes;
- recovery properties;
- current validity state;
- drift and expiry rules;
- last execution record;
- and revocation history.

##### Trigger events

- framework, compiler, CUDA, NCCL, driver, firmware, or container change;
- accelerator or cloud migration;
- workload revision;
- checkpoint policy change;
- scheduler/orchestrator change;
- quarterly or release-bound revalidation when economically justified;
- known signature recurrence.

##### Contract states

```text
PASS_WITHIN_ENVELOPE
FAIL_SAME_INCIDENT
FAIL_DIFFERENT_BOUNDARY
DRIFT_REQUIRES_REQUALIFICATION
STALE
EXPIRED
PRIVATE_REFERENCE_UNAVAILABLE
INFRASTRUCTURE_ERROR
REVOKED
UNKNOWN
```

A pass states only that the named incident contract did not recur in the declared test.

#### 03.11 Optional External Disposition Exchange

The exchange produces provider-native or upstream-native artifacts first:

- PyTorch/NCCL issue and test;
- NVIDIA support/NVDebug references;
- AWS or cloud support bundle references;
- hardware reproduction record;
- service-credit evidence inventory;
- customer postmortem;
- signed experiment attestation.

A generic `DispositionRecord` may include:

```text
RECEIVED
INTEGRITY_VERIFIED
EXECUTED
EVIDENCE_ACCEPTED_WITHIN_SCOPE
MORE_EVIDENCE_REQUESTED
DISPUTED_WITH_COUNTEREVIDENCE
FIX_ACCEPTED
UPSTREAMED
QUARANTINE_OR_RMA_DECISION
CLOSED_UNKNOWN
REVOKED
```

The record reports what the receiver did. It does not establish objective truth by signature alone.

---

## 04.19 Observational validity and capture safety

### 07 — Observational Validity and Capture Safety

#### 07.1 Import-first law

The first product should work from existing artifacts whenever possible. Custom instrumentation is introduced only when:

- native evidence cannot support the pack;
- the missing field has a defined decision purpose;
- overhead and perturbation are measured;
- and the customer explicitly approves it.

This improves adoption and reduces the chance that TrainCapsule creates or hides the incident.

#### 07.2 Capture levels

##### C0 — Post-incident native import

- no TrainCapsule runtime agent;
- Flight Recorder, NCCL, scheduler, device, and support artifacts only;
- lowest integration burden;
- limited replay/state reconstruction.

##### C1 — Semantic markers and identity

- workload lock;
- step/microbatch/phase markers;
- checkpoint/RNG/sampler references;
- bounded metadata only.

##### C2 — Selected signatures and local ring buffers

- selected tensor or state signatures;
- application control markers;
- bounded per-actor buffers;
- trigger-based freeze.

##### C3 — Incident-triggered deep capture

- selected kernel/compiler/data-loader/network/storage evidence;
- activated only under a bounded window or reproduction lane.

Do not arm C3 continuously without measured need.

#### 07.3 Perturbation validation

For each capture level, compare capture-on and capture-off using representative workloads.

Measure:

- median, p95, and p99 step time;
- throughput;
- CPU utilization and scheduling;
- GPU utilization and kernel timing;
- memory and pinned-memory usage;
- storage and network rate;
- collective wait distribution;
- timeout and error frequency;
- evidence loss;
- recorder failures;
- and workload output sentinels.

##### Decision states

```text
PERTURBATION_WITHIN_POLICY
PERTURBATION_MATERIAL_BUT_ACCEPTED
PERTURBATION_CHANGES_INCIDENT
PERTURBATION_UNDERPOWERED
UNSAFE
UNKNOWN
```

A low average overhead does not establish observational validity for a timing-sensitive failure.

#### 07.4 Freeze architecture

The freeze path must not depend solely on the failed communication group.

Requirements:

- separate controller or shared-store path;
- minimum diagnostic state written first;
- explicit missing actors;
- bounded timeout;
- no indefinite wait;
- immutable artifact writes;
- optional larger artifacts only after minimum freeze;
- and recorder-health status.

#### 07.5 Tensor and data policy

Raw tensors and training records stay local by default.

Configurable signatures may include:

- shape and dtype;
- non-finite count;
- min/max/mean/variance;
- norms;
- deterministic hash where appropriate;
- quantized or distribution sketches;
- selected masked samples.

Each signature policy declares collision, privacy, sensitivity, and nondeterminism limitations.

#### 07.6 Recorder failure policy

Per workload, choose:

```text
FAIL_OPEN_AND_ALERT
DEGRADE_TO_LOWER_CAPTURE
FAIL_JOB_FOR_HIGH_ASSURANCE
DISABLE_CAPTURE_AND_PRESERVE_EXISTING
```

Recorder failure may not silently alter training state or be hidden in the final report.

---

## 04.20 Detailed implementation architecture

### 15 — Technical Implementation Architecture

#### 15.1 Local-first deployment

First release topology:

```text
customer cluster or test environment
  ├── native evidence sources
  ├── optional TrainCapsule semantic markers/ring buffer
  ├── local evidence store
  └── local experiment runner
               │ immutable local references
               ▼
TrainCapsule control service
  ├── identity and policy
  ├── incident IR compiler
  ├── experiment planner
  ├── reduction compiler
  ├── disposition engine
  ├── recovery assurance
  └── incident contract registry
               │ signed bounded plans
               ▼
customer/provider execution lanes
  ├── CPU/local structural lane
  ├── source GPU lane
  ├── substitute GPU/node lane
  ├── version A/B lane
  ├── topology-preserving canary
  └── optional confidential/attested lane
```

The first release does not require a hosted multi-tenant control plane.

#### 15.2 Initial technology choices

| Layer | Initial choice | Constraint |
|---|---|---|
| Core orchestration | Python 3.12+ | ecosystem fit and speed |
| Schemas | Pydantic + JSON Schema | versioned and language-neutral artifacts |
| CLI | Typer or equivalent | local operator first |
| API | FastAPI or equivalent | only for long-running local jobs |
| Metadata | SQLite WAL | zero-operations first deployment |
| Evidence | content-addressed filesystem | immutable, local, exportable |
| Containers | OCI with Docker/Podman/containerd-compatible path | exact identity and sandbox |
| Cluster runner | select Slurm **or** Kubernetes from first partner | do not build both before evidence |
| Hot-path hooks | C++/CUDA only after profiling | no premature native complexity |
| High-volume processor | Rust only after measured need | memory safety is useful, not a reason to rewrite |
| Tests | pytest/property/mutation/fault/security/E2E | hidden trust gates |
| Provenance | SBOM + OCI + Cosign/in-toto where available | do not invent crypto |
| Viewer | thin local web UI only after CLI workflow | evidence inspection, not dashboard |

#### 15.3 Repository structure

```text
traincapsule/
├── README.md
├── SECURITY.md
├── docs/
│   ├── master-plan/
│   ├── architecture/
│   ├── adr/
│   ├── trust/
│   ├── operations/
│   └── commercial-boundary/
├── specs/
│   ├── normative/
│   ├── packs/
│   └── policies/
├── schemas/
├── packages/
│   ├── domain/
│   ├── identity/
│   ├── evidence/
│   ├── ingest/
│   ├── incident-ir/
│   ├── analysis/
│   ├── experiments/
│   ├── reducer/
│   ├── runner/
│   ├── disposition/
│   ├── recovery-assurance/
│   ├── contracts/
│   ├── export/
│   ├── security/
│   ├── cli/
│   └── api/
├── adapters/
│   ├── pytorch-flight-recorder/
│   ├── nccl/
│   ├── dcgm/
│   ├── scheduler-selected/
│   ├── checkpoint/
│   └── support-exports/
├── incident-packs/
│   └── pre-collective-lifecycle/
├── native/
│   └── optional-measured-hooks/
├── runners/
│   ├── local/
│   ├── container/
│   ├── scheduler-selected/
│   └── federated/
├── tests/
│   ├── unit/
│   ├── property/
│   ├── mutation/
│   ├── fault-injection/
│   ├── perturbation/
│   ├── replay/
│   ├── full-canary/
│   ├── security/
│   ├── hidden/
│   └── e2e/
├── examples/
└── factory/
```

#### 15.4 Domain entities

| Entity | Identity | Purpose |
|---|---|---|
| `WorkloadManifest` | mutable ID/version | intended workload declaration |
| `WorkloadLock` | content digest | exact execution identity |
| `EvidenceCapability` | versioned record | what can be observed |
| `CaptureProfile` | digest | recorder and perturbation state |
| `IncidentTrigger` | event ID | why investigation began |
| `EvidenceArtifact` | digest/media type | immutable observation |
| `ActorGraph` | digest | workload actors/resources/state channels |
| `IncidentIR` | digest | normalized bounded incident model |
| `ObservedDivergence` | digest | first recorded inconsistency |
| `HypothesisRecord` | digest | mechanism candidate and tests |
| `ExperimentPlan` | digest | bounded discriminating experiment |
| `ExperimentRun` | run ID | one execution and result |
| `FaithfulnessContract` | digest | required properties for reduction |
| `ReductionCandidate` | digest | accepted/rejected smaller case |
| `ApplicabilityEnvelope` | digest | where a result can be used |
| `DispositionRecord` | digest | evidence-backed mechanism/component status |
| `RecoveryAssurance` | digest | tested recovery properties |
| `IncidentContract` | digest | recurring failure-derived test |
| `ExportBundle` | digest | native provider/upstream artifact |
| `ValueRecord` | digest | measured economic/operational effect |
| `AuditEvent` | append-only ID | actor, action, input/output |

#### 15.5 Content-addressed evidence store

```text
store/
├── objects/sha256/<prefix>/<digest>
├── refs/
│   ├── workloads/
│   ├── incidents/
│   ├── experiments/
│   ├── contracts/
│   └── exports/
├── quarantine/
├── temporary/
└── tombstones/
```

Rules:

- atomic immutable writes;
- verify on read and before execution;
- metadata references digests, never arbitrary host paths;
- raw/private and exportable derived artifacts are separate;
- every transformation records parent digests and tool versions;
- retention/deletion policy is enforceable;
- quarantine malformed or untrusted artifacts.

#### 15.6 Workload lock

Required fields, as applicable:

- repository commit and source-tree digest;
- dirty state;
- container digest and SBOM;
- package lock and compiler identity;
- PyTorch build and distributed backend;
- CUDA, NCCL, driver, firmware;
- accelerator UUID/model and topology;
- scheduler/launcher and environment variables;
- model and parallelism configuration;
- checkpoint and sharded-state digests;
- optimizer/scheduler state identity;
- RNG, sampler, data-shard references;
- capture/adapter versions;
- incident pack and policy;
- privacy, rights, and export tier.

Mutable image tags, unknown builds, or missing required references lower the strongest permitted replay/assurance tier.

#### 15.7 Workload graph

```yaml
workloadGraph:
  actors:
    - id: rank-0
      role: trainer
      placement: node-a/gpu-0
    - id: rank-1
      role: trainer
      placement: node-a/gpu-1
  groups:
    - id: dp-group-0
      type: collective
      members: [rank-0, rank-1]
  stateChannels:
    - id: gradient-allreduce
      producerConsumers: [rank-0, rank-1]
  phases:
    - forward
    - backward
    - optimizer-step
  privateReferences:
    - sampler-state://local/...
```

The graph can express one initial DDP/FSDP workload and extend later without changing the core truth model.

#### 15.8 Job states

```text
CREATED
→ VALIDATING_IDENTITY
→ CHECKING_READINESS
→ INGESTING
→ VALIDATING_OBSERVATION
→ BUILDING_IR
→ LOCATING_OBSERVED_BOUNDARY
→ PLANNING_EXPERIMENTS
→ REDUCING
→ EXECUTING
→ EVALUATING_FAITHFULNESS
→ DISPOSITIONING
→ EVALUATING_RECOVERY
→ CREATING_CONTRACT
→ EXPORTING
→ COMPLETED
```

Terminal or paused states:

```text
UNSUPPORTED
INVALID_IDENTITY
INVALID_CAPTURE
PERTURBATION_UNSAFE
POLICY_DENIED
PRIVATE_REFERENCE_UNAVAILABLE
INFRASTRUCTURE_ERROR
UNSAFE_OR_UNPROVEN
UNKNOWN
CANCELLED
EXPIRED
REVOKED
```

Infrastructure failure cannot become a workload verdict.

#### 15.9 Experiment scheduler contract

Every task has:

- immutable inputs;
- executor identity;
- privacy zone;
- resource budget;
- expected duration;
- retry class;
- statistical policy;
- cancellation path;
- output schema;
- and terminal evidence status.

Retries retain the original failed attempt. No retry-until-green behavior.

#### 15.10 Cache identity

A cache key includes, where relevant:

- workload lock;
- evidence digests;
- adapter versions;
- incident pack;
- faithfulness contract;
- reducer version;
- runner image;
- driver/runtime/hardware identity;
- comparator and statistical policy;
- private-reference version;
- capture profile.

Any omitted identity that can affect the verdict invalidates the cache design.

#### 15.11 CLI surface

```bash
traincapsule workload init
traincapsule workload lock
traincapsule readiness check
traincapsule ingest --from flight-recorder,nccl,dcgm,scheduler
traincapsule incident create
traincapsule incident analyze
traincapsule hypotheses show
traincapsule experiment plan
traincapsule experiment approve
traincapsule experiment run --local
traincapsule experiment run --federated
traincapsule reduce --budget ...
traincapsule disposition show
traincapsule recovery evaluate
traincapsule contract create
traincapsule contract run
traincapsule contract status
traincapsule export --target pytorch
traincapsule export --target nvidia-support
traincapsule export --target cloud-support
traincapsule verify
traincapsule revoke
```

A qualified operator should see, within five minutes:

- exact workload identity;
- evidence completeness and perturbation state;
- first observed inconsistency;
- strongest permitted claim;
- planned/failed experiments;
- best faithful case;
- applicability envelope;
- recovery properties;
- what remains unknown;
- and available export/action.

#### 15.12 Performance budgets

Initial internal design targets—not external facts:

| Operation | Target posture |
|---|---|
| Import-only mode | no workload overhead |
| C1 semantic markers | target below 1%; investigate tail impact |
| C2 selected capture | hard review above 2% or any incident perturbation |
| Minimum metadata freeze | bounded and independent of failed process group |
| Evidence growth | bounded by policy and retention |
| Local structural experiment | minutes where workload permits |
| Cancellation | prompt, audited, no orphaned GPU work |
| Viewer | secondary to core workflow |

No target is claimed until measured on representative workloads.

#### 15.13 Reliability requirements

- partial evidence remains partial;
- raw evidence never overwritten;
- every status is exhaustive and machine-readable;
- no broad exception swallowing;
- no hidden network call;
- no automatic recovery action;
- all long tasks resume or cancel safely;
- expired contracts cannot silently pass;
- revocation is enforced;
- every export verifies offline where required.

#### 15.14 Adapter lifecycle and environment-availability architecture

Each adapter release contains:

```text
adapter identity
supported upstream versions
source parser/executor contract
declared information loss
conformance fixtures
malformed-input limits
security posture
release and deprecation dates
contract migration rules
maintenance owner and cost record
```

Each environment lane records:

```text
hardware and topology class
firmware/driver/runtime compatibility
container and registry availability
private-reference availability
capacity owner
estimated experiment cost
last verified date
expiry or substitution policy
```

Ordinary upstream drift must be absorbed in adapters. A requirement to modify the trust core for routine version changes blocks the release and opens an architectural review.

---