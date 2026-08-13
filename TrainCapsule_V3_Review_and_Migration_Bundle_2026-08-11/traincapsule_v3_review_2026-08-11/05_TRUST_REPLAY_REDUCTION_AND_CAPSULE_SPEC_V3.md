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
