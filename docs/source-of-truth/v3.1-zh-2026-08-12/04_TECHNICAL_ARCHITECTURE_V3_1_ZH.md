# 04 — Technical Architecture V3.1-ZH
| Field | Value |
|---|---|
| Logical ID | `TC.V3_1_ZH.TECHNICAL_ARCHITECTURE` |
| Generation | `traincapsule-v3.1-zh-2026-08-12` |
| Authority class | `normative_architecture` |
| Derived from | `TC.V3.TECHNICAL_ARCHITECTURE` |

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

Release is candidate branch → automated pull request → required exact-head-SHA hosted/private checks
→ valid independent machine-policy receipt/check → merge queue or auto-merge → exact merged-main
verification. Direct updates to protected `main`, force push, bypass, and reuse of another SHA's pass
are forbidden. Controller activation requires a separate signed external receipt binding the exact
merged SHA, environment, generation, controller, configuration, policy, canaries, and expiry.

All original V3 laws for exact identity, evidence provenance, native-first and complete-substitute
comparison, explicit `UNKNOWN`, controlled-evidence ceilings, finite retry/recovery, bounded roadmap,
and truthful commercial claims remain mandatory. Controlled or synthetic fixtures cannot prove GPU,
customer, payment, adoption, independent-operation, external-value, or commercial-support facts.

This generation is a disclosed amendment, not a claim of exact original-V3 conformance. Replacing
qualified-person review with encoded independent machine policy loses contextual judgment that might
detect novel ambiguity outside declared policy/private oracles. Separation of authority, hidden
checks, scoped receipts, expiry, revocation, exact-SHA binding, complete evidence, fail-closed release,
and rollback reduce but do not eliminate that residual risk.


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
9. **Trust-critical release requires independent machine authority.** AI review is supporting evidence, never the sole external release authority.
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
                      independent machine-policy authorization where required
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
machinePolicyReceipts:
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
machinePolicyReceipt:
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
ELIGIBLE_WITH_MACHINE_POLICY
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
- required private-oracle and policy coverage.

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
- independent machine-policy authorizations;
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

## 04.16 Independent machine authorization boundary

Create a signed `MachinePolicyReceipt` for:

- first external use;
- each new commercially released incident pack;
- each material change to identity, canonical serialization, reduction legality, applicability, recovery semantics, or qualification decision logic;
- security boundary changes;
- customer-facing claims;
- exceptional case-specific override.

Machine-policy receipt fields:

```yaml
schemaVersion:
receiptId:
scope:
candidateCommit:
artifactDigests:
verifierPolicyId:
verifierPolicyQualification:
decision:
conditions:
limitations:
expiresAt:
signature:
```

The factory may prepare an machine-policy request. It may not create or forge a signed machine-policy receipt.

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
- machine-policy receipt state;
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

Commands must support `--json`, deterministic exit codes, operator-readable diagnostics, and local-only operation.

## 04.20 Exit-code contract

Example:

```text
0  command completed and truth record written
2  invalid CLI use
10 unsupported input/version
11 evidence incomplete
12 identity mismatch
13 policy blocked
14 independent machine-policy authorization required
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
- independent machine-policy trust/security evaluation.

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
8. Add independent machine-policy authorization and product release policy before external use.
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
- independent machine-policy authorization for external use.

V1 is commercially validated only after:

- one paid pilot;
- material advantage over the complete native workflow;
- one paid repeat action;
- customer-confirmed decision value greater than price and retained effort.

Technical completion must never be reported as commercial validation.
