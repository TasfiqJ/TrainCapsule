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
