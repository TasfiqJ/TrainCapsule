# 05 — Trust, Replay, Reduction, Recovery, Contract, and Capsule Specification

- **Document date:** 9 August 2026
- **Status:** **Normative final specification**
- **Governing rule:** TrainCapsule never sells certainty that the evidence and experiment do not support.
- **Primary durable artifact:** `WorkloadIncidentContract`
- **Portable representation:** `.tcap` bundle when permitted; federated result when portable execution is unsafe or impossible.
- **Product relationship:** Close establishes the record; Qualify applies the contract to change; Exchange carries bounded evidence across trust boundaries.

## 05.1 Purpose

This specification defines:

- evidence authority;
- workload and environment identity;
- capture completeness and perturbation;
- observed divergence;
- causal experiments;
- replay and evidence tiers;
- Minimum Faithful Experiment search;
- applicability envelopes;
- component disposition;
- recovery assurance;
- incident contracts and change qualification;
- portable and federated capsule formats;
- hardware attribution;
- statistical policy;
- security, privacy, provenance, expiry, dispute, and revocation;
- and conditions that must remain `UNKNOWN`.

An AI-generated explanation is never authoritative.

## 05.2 Governing truth chain

```text
raw source evidence
        ↓
verified workload, environment, product, pack, and backend identity
        ↓
capture completeness + observational perturbation
        ↓
first observed inconsistent boundary
        ↓
competing mechanism hypotheses
        ↓
predeclared controlled experiments
        ↓
faithful experiment or bounded evidence-only result
        ↓
component/mechanism disposition or UNKNOWN
        ↓
named recovery-state assurance
        ↓
incident contract + applicability envelope
        ↓
change qualification, drift, expiry, dispute, or revocation
```

The product may not generate a narrative first and search for confirming evidence afterward.

## 05.3 Separated records

These records must remain distinct:

```text
SymptomRecord
ObservedDivergenceRecord
CausalPrecursorRecord
MechanismExperimentRecord
ComponentDispositionRecord
OperationalOwnerRecord
RecoveryAssuranceRecord
WorkloadIncidentContract
QualificationRun
ValueRecord
```

A timeout reported by one rank, the first recorded mismatch, the underlying mechanism, the component on which the outcome depends, and the team that should act are different statements.

## 05.4 Authority hierarchy

| Rank | Authority | Strongest permitted conclusion | Limitation |
|---|---|---|---|
| A1 | repeated controlled mechanism experiment | changed variable is causal within tested envelope | not universal |
| A2 | source/substitute or version A/B with strong controls | component/environment dependence supported | residual confounders |
| A3 | exact distributed/runtime/state invariant | named contract was violated | deeper cause may precede boundary |
| A4 | independent provider/vendor/component evidence | corroboration | generic tests may miss workload-specific faults |
| A5 | statistical cross-rank/temporal evidence | anomaly or association | correlation |
| A6 | prior incident contract match | investigation prior | signatures can collide |
| A7 | rule or LLM proposal | candidate experiment only | no final authority |

No majority vote among correlated tools creates truth.

## 05.5 Identity

A high-trust result requires exact identity for every material item:

- source commit and source-tree digest;
- dirty state;
- container digest and SBOM;
- package/compiler/framework build;
- CUDA, NCCL, driver, firmware;
- accelerator identities and topology;
- scheduler, launcher, environment variables;
- model and parallelism configuration;
- checkpoint, optimizer, RNG, sampler, data reference;
- pack, backend, comparator, recorder, reducer, runner, policy, and product versions;
- recovery change and qualification change.

Mutable tags, unknown builds, unpinned policies, or unavailable private references lower the maximum attainable tier.

## 05.6 Capture completeness

```text
COMPLETE_FOR_DECLARED_PACK
COMPLETE_WITH_OPTIONAL_GAPS
PARTIAL_REQUIRED_EVIDENCE
CORRUPTED
UNTRUSTED_IDENTITY
PERTURBATION_UNVALIDATED
UNAVAILABLE
```

A partial capture may support a narrow observed boundary. It cannot support a claim requiring missing fields.

## 05.7 Observational perturbation

Custom capture may create, hide, or move a timing-sensitive incident.

Every capture level records:

- capture-on/off workload identities;
- median, p95, p99 step time;
- collective wait distribution;
- CPU, memory, storage, network, and GPU effects;
- timeout/error frequency;
- evidence loss;
- output sentinels;
- incident-rate comparison where enough trials exist.

States:

```text
PERTURBATION_WITHIN_POLICY
PERTURBATION_MATERIAL_BUT_ACCEPTED
PERTURBATION_CHANGES_INCIDENT
PERTURBATION_UNDERPOWERED
UNSAFE
UNKNOWN
```

Import-only operation is preferred until additional instrumentation is proven necessary.

## 05.8 Observed divergence

The system reports:

```text
EXACT_OBSERVED_DIVERGENCE
BOUNDED_OBSERVED_DIVERGENCE
STATISTICAL_DEGRADATION_WINDOW
EVIDENCE_ONLY_BOUNDARY
UNATTRIBUTED
UNKNOWN
```

The record includes:

- last observed consistent state;
- first observed inconsistent state;
- invariant;
- evidence sources;
- completeness;
- unobserved intervals;
- alternative alignments;
- possible precursors;
- strongest permitted statement.

“First observed” must never be silently shortened to “root cause.”

## 05.9 Replay and evidence tiers

### T0 — evidence-only

The original evidence verifies a bounded inconsistency, but safe or faithful replay is unavailable.

### T1 — structural mechanism experiment

The same distributed, lifecycle, or state-transition contract fails, while exact numerical outputs need not match.

### T2 — deterministic relevant-state experiment

The declared relevant state or output matches at the named boundary under fixed identity and controlled nondeterminism.

### T3 — statistical experiment

The anomaly recurs relative to a predeclared baseline, effect size, trial plan, and threshold.

### T4 — source/substitute dependence experiment

A workload and declared controls are held constant while source/substitute environments differ.

### T5 — topology/scale-preserving emulation

A declared execution graph, communication relation, memory behavior, or selected ranks are reproduced through a validated scale-emulation backend. This tier does not automatically establish semantic correctness outside the measured properties.

The tiers are not a universal strength ladder. The permitted claim depends on the incident predicate and applicability envelope.

## 05.10 Deterministic and statistical policy

For deterministic examples:

- every declared repetition must pass;
- all failed and infrastructure-error trials remain in history;
- exact environment identity is fixed;
- no retry-until-green;
- no post hoc seed selection.

A 20/20 result is an internal release discipline for selected deterministic examples, not proof of zero future failure probability.

For statistical cases, predeclare:

- null and alternative;
- operationally meaningful effect;
- Type I/II error targets;
- baseline;
- trial count/stopping rule;
- confounders;
- missing-data treatment.

When zero failures occur in `n` independent trials, the approximate one-sided 95% rule-of-three upper bound is `3/n`; zero observed failures do not establish zero probability.

## 05.11 Minimum Faithful Experiment

TrainCapsule does not promise the globally smallest reproducer.

A `MinimumFaithfulExperiment` is:

> the lowest-cost candidate found within a declared search space, resource budget, wall-clock budget, privacy policy, and faithfulness predicate.

A candidate must preserve:

1. triggering preconditions;
2. incident pack;
3. violated invariant or mechanism;
4. observed-boundary class;
5. required topology/state relation;
6. replay/evidence tier;
7. relevant component dependence or ambiguity;
8. applicability and legal/export validity.

Every reduction trial records:

```yaml
trial:
  id: ...
  parent: sha256:...
  transformation: ...
  preconditions: []
  mustPreserve: []
  validator: sha256:...
  environment: sha256:...
  outcome: ACCEPTED | REJECTED | INFRASTRUCTURE_ERROR
  rejectReason: ...
  evidence: []
```

Search stops with a reason:

```text
BUDGET_EXHAUSTED
NO_LEGAL_REDUCTION
NO_SMALLER_FAITHFUL_CANDIDATE_FOUND
ENVIRONMENT_UNAVAILABLE
PRIVATE_REFERENCE_UNAVAILABLE
RISK_EXCEEDS_VALUE
OPERATOR_CANCELLED
```

## 05.12 Applicability envelope

Every result and contract states:

- framework, runtime, compiler, driver, firmware, and hardware range;
- topology and parallelism graph;
- actor/scale range;
- data/checkpoint/RNG assumptions;
- required private references;
- concurrency and load assumptions;
- capture/backend requirements;
- permitted substitutions;
- last verification;
- revalidation triggers;
- expiration;
- unsupported conclusions.

A reduced pass cannot be generalized beyond this envelope.

## 05.13 Component disposition

States:

```text
OBSERVED_BOUNDARY_ONLY
MECHANISM_SUPPORTED
MECHANISM_REPRODUCED
COMPONENT_DEPENDENCE_SUPPORTED
MULTI_COMPONENT_INTERACTION
ALTERNATIVES_REMAIN
UNATTRIBUTED
UNKNOWN
DISPUTED
REVOKED
```

Component classes:

```text
APPLICATION_CONTROL_FLOW
DATA_OR_SAMPLER
CHECKPOINT_OR_RESTORE
NUMERICAL_OR_PRECISION
FRAMEWORK_OR_DISTRIBUTED_RUNTIME
COMPILER_OR_GENERATED_KERNEL
COMMUNICATION_LIBRARY
GPU_KERNEL_OR_DEVICE
HOST_CPU_OR_MEMORY
NETWORK_OR_FABRIC
STORAGE
SCHEDULER_OR_CO_TENANCY
EXTERNAL_SERVICE
MULTI_COMPONENT_INTERACTION
```

Technical disposition is not legal fault, warranty determination, service-credit entitlement, or employee responsibility.

## 05.14 Hardware attribution

False hardware attribution is release-blocking.

Strong device-dependence evidence requires, where operationally possible:

- same locked workload/input;
- repeated failure on suspected device;
- matched same-model substitutes;
- placement/follow-the-device experiment;
- software/version controls;
- first divergent operator/tensor compatible with the claim;
- complete contradictory evidence;
- and provider/vendor corroboration for the strongest public state.

States:

```text
DEVICE_DEPENDENCE_NOT_SUPPORTED
DEVICE_DEPENDENCE_SUSPECTED
DEVICE_DEPENDENCE_REPRODUCED_WITHIN_SCOPE
VENDOR_CORROBORATED
DISPUTED
UNKNOWN
```

TrainCapsule never certifies that a device is defective.

## 05.15 Recovery Assurance

Recovery Assurance evaluates named properties, not universal safety.

Property groups:

- artifact integrity;
- checkpoint completeness;
- optimizer/scheduler state;
- RNG/sampler continuity;
- data cursor;
- shard ownership and distributed membership;
- loss/gradient/tensor sentinels;
- throughput and resource behavior;
- clean controls;
- rollback;
- recurrence during observation window.

States:

```text
RECOVERY_NOT_EVALUATED
RECOVERY_PATH_EXECUTED
STATE_PROPERTIES_PASSED
REDUCED_CANARY_PASSED
TOPOLOGY_PRESERVING_CANARY_PASSED
PRODUCTION_LIKE_CANARY_PASSED
OBSERVATION_WINDOW_PASSED
QUALITY_NOT_ESTABLISHED
PERFORMANCE_REGRESSION
RECURRENCE_OBSERVED
UNSAFE_OR_UNPROVEN
UNKNOWN
```

A short canary cannot establish unmeasured long-horizon model quality.

## 05.16 Workload Incident Contract

A contract is failure-derived or explicitly purchased as a critical-workload control.

Required fields:

```yaml
contract:
  schemaVersion: 1
  contractId: ...
  sourceIncident: ...
  predicate: ...
  observedBoundary: ...
  mechanism: ...
  faithfulness: ...
  applicabilityEnvelope: ...
  requiredPrivateReferences: []
  executionPolicy: ...
  recoveryProperties: []
  expectedOutcomes: ...
  qualificationTriggers: []
  validity:
    createdAt: ...
    lastVerifiedAt: ...
    expiresAt: ...
    state: CURRENT
  provenance: ...
  revocation: ...
```

Contract classification:

```text
UPSTREAMABLE_REPOSITORY_TEST
PRIVATE_CROSS_STACK_CONTRACT
ENVIRONMENT_OR_TOPOLOGY_QUALIFICATION
HARDWARE_OR_FLEET_QUALIFICATION
RECOVERY_STATE_CONTRACT
EVIDENCE_ONLY_OPERATIONAL_RECORD
NO_DURABLE_CONTRACT
```

Rules:

- upstream ordinary repository tests when rights permit;
- do not charge indefinitely for storing one assertion;
- recurring value requires maintained execution, private references, environment/topology materialization, hardware access, recovery assurance, or operational evidence;
- stale/expired contracts cannot approve a release.

## 05.17 Qualification run

A qualification run binds:

- contract digest;
- baseline workload lock;
- candidate `ChangeLock`;
- exact environment;
- backend/runner versions;
- experiment policy;
- outcomes;
- applicability and drift;
- operator approval where required.

A qualification pass means only:

> the named incident predicate was not reproduced and the selected properties passed in the tested envelope.

It does not mean the new stack is globally correct.

## 05.18 Capsule representation

The `.tcap` artifact is an OCI-compatible signed bundle or directory representation. It is not required when federated execution is the only safe mode.

```text
TC-.../
├── capsule.json
├── workload/
│   ├── workload.lock.json
│   ├── change.lock.json
│   ├── topology.json
│   └── sbom.cdx.json
├── incident/
│   ├── symptom.json
│   ├── capture-completeness.json
│   ├── perturbation.json
│   ├── observed-divergence.json
│   └── hypotheses.json
├── evidence/
│   ├── manifest.json
│   └── policy-approved-artifacts/
├── experiments/
│   ├── plans.jsonl
│   ├── results.jsonl
│   └── environment-availability.json
├── reduction/
│   ├── trials.jsonl
│   ├── accepted-experiment.json
│   └── faithfulness.json
├── disposition/
│   ├── mechanism.json
│   ├── component.json
│   ├── alternatives.json
│   └── dispute.json
├── recovery/
│   ├── properties.json
│   ├── trials.jsonl
│   └── assurance.json
├── contract/
│   ├── workload-incident-contract.json
│   ├── applicability-envelope.json
│   └── qualification-history.jsonl
├── exports/
├── privacy/
├── provenance/
│   ├── materials.json
│   ├── attestations/
│   └── signatures/
└── verify/
    ├── verify.sh
    └── expected-digests.json
```

## 05.19 Federated result

When code/data cannot leave, the capsule contains:

- signed experiment plan;
- policy decision;
- environment and private-reference attestations;
- runner and backend identities;
- bounded result;
- evidence digests;
- permitted summaries;
- applicability and limitations;
- dispute/revocation path.

The external verifier does not pretend to possess raw evidence it was not permitted to receive.

## 05.20 Security and provenance

Required:

- canonical digests;
- signed release and result artifacts;
- OCI subject/referrer relationships where appropriate;
- SBOM;
- in-toto/SLSA-compatible provenance;
- Sigstore/Cosign-compatible signing where deployment permits;
- no arbitrary generated shell;
- trusted templates;
- no network by default;
- non-root;
- no arbitrary mounts;
- archive escape/device-file/decompression-bomb protection;
- secret and restricted-data scans;
- license review;
- exact retention and deletion;
- revocation and correction.

No model-generated text may directly become executable code in a released capsule.

## 05.21 Data rights

Customer owns:

- source;
- model/checkpoint;
- data;
- raw evidence;
- private topology;
- organization-specific incident history.

TrainCapsule may retain or own only what contract expressly permits:

- product code;
- general reducers;
- declarative packs;
- open schemas/verifier;
- nonidentifying transformation recipes;
- aggregate product metrics;
- approved anonymous signatures/outcomes.

Permission to investigate one case does not imply permission to train a model, publish, retain raw evidence, correlate customers, or create a benchmark.

## 05.22 Dispute, correction, and revocation

Any credible contradictory evidence changes the state to `DISPUTED`.

A result is revoked when:

- identity or integrity fails;
- privacy/export policy was violated;
- faithfulness was false;
- a stronger controlled result contradicts it;
- hardware/component attribution was wrong;
- the contract expired or dependencies disappeared;
- or the customer/legal owner revokes permitted use.

Revocation propagates to derived qualifications and public claims.

## 05.23 Hidden fault catalog

At minimum, the hidden suite includes:

- skipped/reordered/incompatible collective;
- CPU branch stall;
- data-loader block;
- checkpoint wait/corruption;
- process exit and membership drift;
- timestamp skew;
- missing rank;
- stale identity;
- invalid reduction removing trigger;
- reduced case changing boundary;
- 15/20 statistical behavior misclaimed as deterministic;
- source/substitute both failing;
- generic hardware test contradicting exact workload;
- false recovery from timeout increase;
- replacement node masking software defect;
- malicious archive and network exfiltration;
- public export contamination;
- AI agent modifying expected evidence;
- stale/expired contract approving a change;
- qualification pass outside applicability envelope.

## 05.24 Release gates

- every result names evidence/replay tier;
- every disposition names authority and alternatives;
- `UNKNOWN` survives all surfaces;
- no causal claim from observed boundary alone;
- no hardware confirmation from telemetry alone;
- every accepted reduction preserves declared faithfulness;
- statistical plans are predeclared;
- sanitization is followed by replay;
- federated results verify signer, identity, and scope;
- capsule execution passes security tests;
- stale/expired contracts cannot pass qualification;
- independent operator can execute supported workflow;
- false public attribution blocks release;
- value claims retain attempted-case denominator.

## 05.25 Final trust rule

> **TrainCapsule sells a controlled reduction in uncertainty and execution burden. It does not sell omniscience.**

## 05.26 Detailed truth, causality, replay, and statistics

### 06 — Truth, Causality, Replay, and Statistical Policy

#### 06.1 Governing truth chain

```text
raw source evidence
        ↓
verified execution identity
        ↓
observational validity and capture completeness
        ↓
first observed inconsistent boundary
        ↓
competing mechanism hypotheses
        ↓
predeclared discriminating experiments
        ↓
mechanism support or bounded uncertainty
        ↓
recovery-assurance properties
        ↓
incident contract and applicability envelope
```

The product must not begin with a root-cause narrative and search for confirming evidence.

#### 06.2 Authority hierarchy

| Rank | Authority | Permitted conclusion | Limitation |
|---|---|---|---|
| A1 | repeated controlled mechanism experiment | declared variable is causal within the tested envelope | may not generalize beyond envelope |
| A2 | source/substitute or version A/B with strong controls | environment/component dependence supported | unobserved differences may remain |
| A3 | exact distributed/runtime invariant | contract violation at named boundary | deeper initiating cause may precede it |
| A4 | independent component health or provider evidence | corroborating component evidence | generic tests can miss workload-specific faults |
| A5 | statistical cross-rank or temporal evidence | anomaly or association | correlation is not causation |
| A6 | prior incident contract match | investigation prior and experiment recommendation | similar signatures can differ |
| A7 | rule or LLM hypothesis | candidate only | never final authority |

A support-ticket closure, human opinion, or model consensus does not outrank contradictory controlled evidence.

#### 06.3 Capture completeness states

```text
COMPLETE_FOR_DECLARED_PACK
COMPLETE_WITH_OPTIONAL_GAPS
PARTIAL_REQUIRED_EVIDENCE
CORRUPTED
UNTRUSTED_IDENTITY
PERTURBATION_UNVALIDATED
UNAVAILABLE
```

A partial capture may support a narrow observed boundary. It cannot be described as complete.

#### 06.4 Replay and evidence tiers

##### T0 — Evidence-only boundary

- original evidence verifies;
- a bounded inconsistent boundary is present;
- replay is unsafe, unavailable, or impractical;
- no mechanism claim beyond evidence.

##### T1 — Structural mechanism replay

- the same distributed/lifecycle contract fails;
- numerical outputs need not match;
- required topology and control preconditions are preserved.

##### T2 — Deterministic relevant-state replay

- the named relevant state or output matches at the declared boundary;
- exact input and environment constraints verify;
- nondeterministic inputs are absent or controlled.

##### T3 — Statistical replay

- the anomaly recurs against a predeclared baseline and threshold;
- trial count and power are justified;
- uncertainty and failed trials are retained.

##### T4 — Source/substitute dependence experiment

- workload and declared controls are held constant;
- source and substitute environments produce materially different outcomes;
- residual confounders are named.

The tiers are not a simple strength ladder for every case. A T4 hardware dependence experiment may still rely on T1 structural evidence.

#### 06.5 Deterministic repeat policy

“20/20” may remain an internal release gate for selected deterministic public examples, but it is not a universal statistical proof.

For a claimed deterministic case:

- all repetitions must pass;
- environment identity must remain fixed;
- trial order and seeds are retained;
- no failed trial may be deleted;
- infrastructure retries are separate;
- and the product must state that the sample does not establish behavior on untested environments.

#### 06.6 Statistical cases

Before execution, define:

- null and alternative hypotheses;
- outcome metric;
- minimum effect of operational interest;
- acceptable Type I and Type II error;
- baseline distribution;
- trial budget and stopping rule;
- confounders;
- and missing-data handling.

Use confidence intervals or a justified nonparametric method. Do not select a threshold after viewing the favorable result.

##### Zero-failure interpretation

When zero recurrences occur in `n` independent trials, the approximate one-sided 95% upper bound on the true failure probability is `3/n` under the common rule-of-three approximation. Therefore:

- 0/20 does not establish a failure probability of zero;
- 0/100 still leaves an approximate upper bound near 3%;
- and independence assumptions must be justified.

Use this to constrain recovery and incident-contract language.

#### 06.7 First observed divergence record

```yaml
observedDivergence:
  lastObservedConsistent:
    step: 48212
    boundary: collective-912043
  firstObservedInconsistent:
    step: 48213
    actor: rank-91
    boundary: expected-all-reduce-not-reached
  invariant: COLLECTIVE_CONTRACT
  evidenceCompleteness: COMPLETE_FOR_DECLARED_PACK
  strongestPermittedStatement: OBSERVED_BOUNDARY_ONLY
  possiblePrecursors:
    - data-dependent-control-flow
    - dataloader-block
    - process-scheduling-stall
  unobservedIntervals:
    - application-code-between-marker-and-collective
```

#### 06.8 Mechanism record

```yaml
mechanism:
  class: DATA_DEPENDENT_CONTROL_FLOW
  status: MECHANISM_REPRODUCED
  experiment:
    changedVariable: triggering-record
    heldConstant:
      - source-image
      - framework-runtime
      - actor-topology
      - seed-and-sampler-state
    outcomes:
      triggerPresent: incident-reproduced-20-of-20
      triggerAbsent: clean-20-of-20
  limitations:
    - only tested on declared two-rank topology
```

#### 06.9 Hardware and provider attribution

A product result may report component dependence, not definitive legal responsibility.

Hardware dependence requires, where operationally possible:

- same locked workload and input;
- repeated failure on suspected device;
- matched substitutes;
- placement/follow-the-device experiment;
- software/version controls;
- first divergent operator/tensor compatible with the claim;
- independent corroboration or provider disposition for a stronger status;
- and full contradictory evidence.

States:

```text
DEVICE_DEPENDENCE_NOT_SUPPORTED
DEVICE_DEPENDENCE_SUSPECTED
DEVICE_DEPENDENCE_REPRODUCED_WITHIN_SCOPE
VENDOR_CORROBORATED
DISPUTED
UNKNOWN
```

TrainCapsule never certifies a warranty defect.

#### 06.10 Hypothesis ledger

Every case retains:

- prior basis;
- planned experiment;
- outcome;
- supporting evidence;
- contradicting evidence;
- residual uncertainty;
- and status.

Rejected hypotheses remain visible to prevent hindsight-biased reports and to support later re-evaluation.

---

## 05.27 Detailed security, privacy, licensing, and federated verification

### 08 — Security, Privacy, Licensing, and Federated Verification

#### 08.1 Default security posture

> **Customer-local evidence, customer-controlled storage, minimum necessary capture, signed experiment plans, explicit export, and no mandatory external telemetry.**

TrainCapsule handles unusually sensitive material:

- source and generated code;
- model architecture and configuration;
- checkpoints and optimizer state;
- training examples and data references;
- tensor signatures;
- infrastructure topology;
- component vulnerabilities;
- device health;
- and incident history.

Security failure can outweigh every technical benefit.

#### 08.2 Execution and export tiers

##### E0 — Local evidence analysis

- raw evidence never leaves;
- only local reports;
- no portable code.

##### E1 — Federated experiment

- signed experiment plan enters the environment;
- approved local references are resolved there;
- signed result and bounded evidence exit.

##### E2 — Private portable reproducer

- transferred only to a named authorized receiver;
- explicit license and data authorization;
- sandbox and identity lock required.

##### E3 — Sanitized portable reproducer

- sanitization preserves predicate and is replayed;
- no restricted material;
- receiver can execute independently.

##### E4 — Public capsule

- public code/data or legally cleared transformations;
- clean-environment execution;
- no private credentials or references.

The product must succeed commercially at E0/E1 for sensitive customers.

#### 08.3 Federated experiment protocol

```text
planner creates immutable experiment request
        ↓
customer policy engine verifies request and signer
        ↓
local runner resolves approved private references
        ↓
sandbox executes experiment
        ↓
runner records environment and result digests
        ↓
attestation and bounded evidence are signed
        ↓
external verifier checks identity, policy, and result
```

A receiving organization may trust the attestation, request its own run, or dispute the methodology. TrainCapsule does not force trust.

#### 08.4 Confidential computing

Where supported, remote attestation can cryptographically prove CPU/GPU guest state before secrets or encrypted artifacts are released. NVIDIA documents confidential-container architectures with CPU/GPU attestation and policy-controlled secret release. [S21][S22]

Constraints must be explicit:

- supported GPU and CPU platforms;
- multi-GPU topology limitations;
- performance overhead;
- operator and Kubernetes requirements;
- attestation-service dependencies;
- and unsupported networks/storage paths.

Confidential computing is an optional deployment mode, not the universal answer to cross-company trust.

#### 08.5 Sandbox requirements

- rootless or non-root execution;
- read-only root filesystem;
- dropped capabilities;
- no host Docker socket;
- no SSH agent or host home;
- no cloud metadata;
- network disabled by default;
- dedicated input/output mounts;
- CPU, memory, PID, disk, GPU, and time limits;
- seccomp/AppArmor or equivalent where available;
- customer code treated as untrusted;
- complete audit;
- and explicit cleanup.

#### 08.6 Archive and artifact safety

Reject:

- path traversal;
- absolute paths;
- escaping symlinks or hardlinks;
- device files and FIFOs;
- ownership manipulation;
- decompression bombs;
- duplicate conflicting paths;
- unexpected executable bits;
- oversized expansion;
- malformed nested structures;
- and unverifiable digests.

#### 08.7 Supply-chain identity

Use existing standards:

- OCI images and artifacts;
- OCI subject/referrer relationships;
- Sigstore/Cosign or approved private PKI;
- in-toto attestations;
- SBOMs;
- pinned dependencies and immutable images;
- isolated builds;
- signed releases;
- vulnerability and license scanning.

OCI v1.1 supports artifact types, subjects, and referrers; Cosign supports artifact signatures and policy-checked in-toto attestations. [S23][S24]

TrainCapsule should define incident semantics, not invent a new cryptographic transport.

#### 08.8 Data classification

```text
PUBLIC
INTERNAL
CONFIDENTIAL
RESTRICTED
SECRET
REGULATED
CUSTOMER_MANAGED_REFERENCE_ONLY
```

Every artifact has:

- owner;
- classification;
- source;
- retention;
- export policy;
- derived-artifact lineage;
- and deletion/revocation behavior.

#### 08.9 Data rights

Customer owns or controls:

- source code;
- models and checkpoints;
- training data;
- raw evidence;
- workload configuration;
- customer identifiers;
- private incident history.

TrainCapsule may retain only what the contract explicitly permits, such as:

- product code;
- general reducers;
- pack logic;
- public schemas;
- nonidentifying transformation recipes;
- aggregate metrics;
- or permissioned incident signatures.

One investigation does not grant rights to train a model, publish the case, retain raw evidence, or correlate customers.

#### 08.10 Licensing and redistribution

A faithful reproducer may contain code or artifacts whose licenses prohibit redistribution or derivative publication.

Every export must record:

- component licenses;
- customer and third-party rights;
- model/data redistribution restrictions;
- generated-code provenance;
- patch or test licensing;
- and receiver authorization.

When rights are insufficient, use a local reference or federated experiment. Do not copy private code into a supposedly sanitized public case.

#### 08.11 Retention, expiry, and revocation

- raw evidence: shortest customer-approved period;
- temporary replay data: delete after verified run;
- private incident contract: contract and policy duration;
- public artifact: indefinite only with correction/revocation mechanism;
- signature/outcome metadata: explicit permission duration;
- secrets: never stored.

Revocation propagates to derived artifacts where contract or law requires it.

#### 08.12 Recovery-action safety

Initial product actions are advisory or isolated.

Prohibited by default:

- draining production nodes;
- restarting clusters;
- changing timeouts;
- modifying model code;
- replacing hardware;
- deleting checkpoints;
- changing network/storage configuration.

Future production actions require:

- explicit policy;
- least privilege;
- human or customer-approved authorization;
- canary;
- rollback;
- blast-radius limit;
- audit;
- and independent verification.

---