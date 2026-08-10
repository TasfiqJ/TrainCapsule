# 00 — Executive Build Decision

- **Document date:** 9 August 2026
- **Status:** **BUILD AUTHORIZED — proof-seeking, option-preserving company build**
- **Working codename:** TrainCapsule. Complete legal, domain, package, and trademark clearance before public release.
- **Initial category:** **Accelerated Workload Failure Reproduction and Change Qualification**
- **Initial technical surface:** containerized Linux; current pinned PyTorch stable release; c10d/DDP/FSDP; NCCL; NVIDIA GPUs; Slurm first; 2–64 GPUs for controlled engineering.
- **Commercial qualification:** determined by incident economics, recurrence, deployment authority, and the gap left by the buyer's complete native/bundled workflow—not by GPU count alone.
- **Source-of-truth rule:** this file and the accompanying final document set replace all earlier TrainCapsule plans where wording, scope, buyer, roadmap, or evidence standards conflict.

> **Final decision**
>
> Build TrainCapsule now. The autonomous engineering loop may construct the complete local, customer-deployable product before market proof because the founder's direct engineering-time cost is low. However, the loop is not authorized to fabricate demand, treat synthetic success as commercial proof, or expand into expensive hosted/provider breadth merely because code can be generated.
>
> The correct doctrine is:
>
> **Build the reusable truth, experiment, and qualification kernel; continuously search for the highest-value failure workflow that the kernel can close; then use real behavior to determine which commercial surface deserves focus.**

## 00.1 The company being built

TrainCapsule is not a GPU black box, observability dashboard, restart system, or AI log analyst.

> **TrainCapsule converts an unresolved accelerated-workload failure into the lowest-cost faithful experiment it can establish within a declared budget, evaluates a bounded recovery, and preserves the confirmed failure as an expiring workload incident contract that can qualify future software, hardware, topology, checkpoint, and cloud changes.**

The product has three connected loops.

### Close

```text
native evidence
→ exact workload/environment identity
→ evidence completeness and perturbation assessment
→ first observed inconsistent boundary
→ competing mechanism hypotheses
→ controlled discriminating experiments
→ minimum faithful experiment within budget
→ recovery assurance
→ failure-derived incident contract
```

The completed customer outcome is not “we found an anomaly.” It is one or more of:

- the incident is materially cheaper to execute and investigate;
- a mechanism is reproduced within a declared applicability envelope;
- a recovery decision is safer because named state properties were tested;
- a private incident becomes a durable executable or federated contract;
- or the product correctly recommends mitigation without further reproduction because deeper closure is uneconomic.

### Qualify

Confirmed incidents and explicitly purchased critical-workload controls become versioned contracts. TrainCapsule executes those contracts when the customer changes:

- PyTorch, CUDA, NCCL, compiler, driver, firmware, or container;
- accelerator generation, node type, cloud, topology, or scheduler;
- checkpoint, optimizer, RNG, sampler, or resume policy;
- workload code, parallelism graph, or data pipeline;
- or a customer-defined release boundary.

This is the recurring product. It is **not** a generic compatibility matrix. Every recurring contract must come from:

1. a confirmed failure;
2. a customer-approved recovery-state property;
3. or a specifically purchased critical-workload qualification requirement with objective pass/fail semantics.

Ordinary repository bugs that collapse into one stable test should be upstreamed or retained in the customer's CI. TrainCapsule earns recurring value only when continued environment materialization, private references, cross-stack execution, topology/hardware access, recovery assurance, or evidence operations remain necessary.

### Exchange

When an external organization adds value, TrainCapsule creates a provider-, framework-, or hardware-native evidence package or executes a federated experiment inside that organization's boundary.

Exchange is useful for:

- upstream regressions;
- provider support;
- workload-specific device investigations;
- RMA or quarantine evidence;
- service-credit evidence inventories;
- and shared technical dispositions.

External acceptance is **not** required for the first customer to receive value. A two-sided standard is optional upside, not a dependency built into the initial commercial transaction.

## 00.2 Why this is a stronger bet than the earlier incident-only shape

The incident-only product had five structural weaknesses:

1. expensive incidents may be too rare for recurring contracts;
2. automatic recovery may resolve enough events that customers rationally skip deep closure;
3. native platforms can bundle detection, remediation, and support at an apparent incremental price near zero;
4. a successful reproduction often becomes one upstream test, removing future paid work for that exact defect;
5. first-divergence and reduced-scale execution are increasingly becoming independent research and platform capabilities.

The revised product corrects each weakness:

| Structural risk | Final correction |
|---|---|
| Rare incident trigger | Qualify runs failure-derived contracts across real stack changes. |
| Customer prefers restart | Run `ClosureValueQualification` first and stop when deep closure is uneconomic. |
| Native tools improve | Import and benchmark them; duplicate primitives are replaceable backends. |
| Bug becomes free test | Upstream ordinary assertions; monetize private cross-stack execution and recovery assurance only. |
| Research absorbs a primitive | Use backend interfaces for operator alignment, scale emulation, hardware dependence, and checkpoint state. |
| External party will not adopt | Make the customer-local result sufficient by itself. |
| Exact reproduction impossible | Support structural, statistical, source/substitute, and evidence-only tiers with explicit applicability envelopes. |
| Customer will not export code/data | Default to federated execution and signed bounded results. |
| AI loop builds the wrong wedge | Maintain a Wedge Discovery Ledger and force periodic `KEEP`, `INTEGRATE`, `UPSTREAM`, `NARROW`, `REPLACE`, or `STOP` decisions. |

## 00.3 The most defensible company boundary

TrainCapsule does **not** defend:

- the recorder;
- a log parser;
- an event graph;
- an LLM explanation;
- one first-divergence algorithm;
- one reduction algorithm;
- one replay engine;
- one provider ticket template;
- or one synthetic benchmark.

Those can be copied, upstreamed, or bundled.

The defensible boundary is the complete trusted operating system for failure-derived workload contracts:

```text
customer-local evidence and identity
+ controlled experiment planning
+ replaceable diagnosis/emulation backends
+ faithfulness and applicability contracts
+ recovery-state assurance
+ private/federated execution
+ contract drift, expiry, and requalification
+ provider/upstream-native handoffs
+ longitudinal operational trust
```

The base business must work without a cross-customer data moat or industry-standard adoption. Those are upside only.

## 00.4 Replaceable backend law

TrainCapsule must assume that frameworks, clouds, vendors, and research systems will continue to absorb technical primitives.

The stable product interfaces are:

- `CollectiveTraceBackend`
- `OperatorAlignmentBackend`
- `ScaleEmulationBackend`
- `HardwareDependenceBackend`
- `CheckpointStateBackend`
- `EnvironmentMaterializationBackend`
- `SupportExportBackend`

Examples:

- PyTorch Flight Recorder can supply collective and call-stack evidence. [S01]
- An OpGuard-compatible backend can provide operator-boundary alignment for numerical/correctness investigations. [S29]
- A PrismLLM-compatible backend can provide scale-emulation capabilities when production-scale behavior cannot be reproduced by naive downscaling, subject to workload-specific validation. [S30]
- Provider- or vendor-native health systems can supply device and infrastructure evidence.

TrainCapsule competes only when its completed workflow produces material incremental value above the best available backend combination.

## 00.5 Initial wedge

The first released pack is:

> **`PRE_COLLECTIVE_LIFECYCLE_CONTRACT_V1` — pre-collective control-flow and distributed-lifecycle failure reproduction.**

It covers a bounded family in which actors cease to satisfy a declared collective or lifecycle contract because of an upstream event such as:

- omitted, reordered, or incompatible collectives;
- a data-dependent control-flow branch;
- a data-loader or checkpoint path preventing progress;
- process exit or illegal group membership change;
- or a bounded runtime/kernel lifecycle condition that can be separated from ordinary delay.

Flight Recorder is a mandatory baseline and evidence input. TrainCapsule receives no credit for merely identifying the missing rank, collective, shape mismatch, or source line already produced by native tools.

The pack succeeds commercially only when it additionally:

- preserves or reconstructs the upstream trigger;
- reduces the execution burden materially;
- produces a faithful executable or federated experiment;
- distinguishes omission, delay, process failure, and infrastructure failure;
- evaluates the recovery/guard;
- and creates a durable contract or native support artifact.

The second planned pack is:

> **`CHECKPOINT_RESUME_STATE_CONSISTENCY_V1`**

This was selected because increasingly effective restart and checkpointless recovery make post-recovery state assurance more—not less—important. It evaluates checkpoint integrity, optimizer/scheduler state, RNG and sampler continuity, data cursor, shard ownership, short-run trajectory sentinels, throughput, and declared observation windows. It does not claim universal long-horizon model correctness.

Further packs are evidence-selected, not precommitted:

- numerical divergence through an operator-alignment backend;
- workload-specific hardware dependence with a provider/hardware partner;
- fail-slow only when native tools identify the slow component but do not reproduce or close it;
- heterogeneous post-training actor graphs only after the initial IR proves extensible.

## 00.6 Build-first doctrine

The user's chosen strategy—build first, then look for proof—is authorized under the following distinction:

### Authorized without customer proof

- the stable trust core;
- canonical schemas and immutable identities;
- native evidence import;
- incident IR;
- first observed boundary logic;
- controlled experiment planner;
- Minimum Faithful Experiment compiler;
- local/federated runner;
- recovery assurance;
- incident contract registry;
- qualification engine;
- offline verifier;
- controlled fault lab;
- public incident corpus;
- native/bundled benchmark harness;
- CLI and thin local viewer;
- AI factory, source monitor, adversarial tests, and product-wedge review loop.

### Not authorized merely because AI can generate it

- owned GPU fleet;
- broad hosted ReproGrid;
- multi-tenant SaaS;
- billing;
- broad RBAC;
- generic dashboards;
- every framework, cloud, scheduler, and accelerator;
- autonomous production modification;
- public cross-customer incident graph;
- claims of root-cause accuracy, ROI, market size, customer demand, or acquisition interest;
- or customer-specific integrations with no committed user.

The engineering loop may continue independent work while external evidence is absent. It must mark real incident, payment, provider acceptance, and adoption claims as `EXTERNAL_VALIDATION_REQUIRED`.

## 00.7 Problem-discovery engine inside the build

The strongest hedge against choosing the wrong initial incident class is not a broad product. It is a disciplined mechanism for finding a better wedge while preserving the core.

The repository must maintain:

- `WEDGE_DISCOVERY_LEDGER.md`
- `PUBLIC_INCIDENT_CORPUS/`
- `NATIVE_BUNDLE_CAPABILITY_MATRIX.md`
- `BACKEND_ABSORPTION_REGISTER.md`
- `REACHABLE_ACCOUNT_MAP.md`
- `WEDGE_DECISION.md`

Every candidate incident family is scored on:

```text
severity
× recurrence or stack-change trigger frequency
× native/bundled gap
× evidence availability
× customer deployment authority
× one-party value
× productization potential
× price-supporting economics
× strategic buyer relevance
÷ security, integration, and adapter burden
```

The score is a decision aid, not a validated predictive model.

At least monthly, an adversarial product session must choose exactly one disposition for each candidate or current subsystem:

```text
KEEP
INTEGRATE_EXISTING_BACKEND
UPSTREAM
NARROW
REPLACE_WEDGE
PAUSE
STOP
```

The loop is forbidden from preserving a weak feature merely because it already generated code.

## 00.8 Customer and buyer

The best initial customer is a workload platform or model organization that:

- runs repeated distributed PyTorch/NCCL workloads;
- controls launch, images, checkpoints, and local experiment execution;
- has experienced at least one materially costly unresolved failure or has high-consequence stack changes;
- already uses native diagnostics, creating a fair benchmark;
- has a small enough systems team that incident work competes with core roadmap work;
- can supply a second workload, incident, or qualification trigger;
- and has a named budget owner.

A managed training provider or neocloud is a strong secondary segment when it has enough support volume but does not already possess the complete workflow.

Frontier labs and hyperscalers are strategically attractive but poor assumptions for an initial sale because internal capability and security boundaries are strongest.

Accounts are disqualified when:

- native mitigation is sufficient and residual uncertainty is acceptable;
- the customer lacks evidence or experiment authority;
- the product would require prohibited source, data, or checkpoint export;
- the incident value cannot exceed integration and delivery cost;
- or the customer demands guaranteed root cause, hardware certification, or universal recovery safety.

## 00.9 Commercial sequence

The final commercial sequence is:

```text
historical incident / failure-readiness assessment
→ bounded active or reconstructed closure
→ failure-derived incident contract
→ paid stack-change or recovery qualification
→ critical workload assurance
→ provider evidence gateway where volume supports it
```

Do not assume cold annual readiness sales. Recurring contracts should be earned after the customer has seen a useful closure, a convincing readiness drill, or a qualification result tied to an actual change.

The initial business may be software-assisted expert delivery. That is acceptable if:

- scope is bounded;
- each case compounds reusable software or contracts;
- delivery margin improves;
- founder-only reasoning declines;
- and customers repeat.

It must not be falsely described as SaaS.

## 00.10 What would make the product a real business

The company thesis becomes supported only when the following are observed:

1. **Complete-substitute advantage:** TrainCapsule materially improves on the buyer's framework tools, cloud/platform features, vendor support, internal engineers, and approved coding/operations agents taken together.
2. **One-party value:** the purchaser benefits even if no external provider accepts a TrainCapsule format.
3. **Faithful cost reduction:** a real incident becomes materially cheaper, faster, or more accessible without changing the relevant mechanism.
4. **Bounded recovery value:** named state properties change a real recovery or release decision.
5. **Contract value:** at least some confirmed failures retain value through future stack qualification after ordinary tests are upstreamed.
6. **Repeat use:** a useful first result causes a second incident, qualification, protected workload, or paid continuation.
7. **Productization:** later same-pack cases use the stable core and declarative packs rather than trust-core rewrites and hidden founder reasoning.
8. **Security feasibility:** local/federated execution satisfies customer policy.
9. **Reachable market:** enough named accounts have pain, authority, budget, and insufficient substitutes.
10. **Delivery economics:** adapter maintenance, GPU experiments, security review, and senior engineering leave an acceptable margin.

## 00.11 Acquisition objective

The product is built to become a valuable independent business. Acquisition is a possible consequence.

The relevant Brev lesson is not “build another GPU abstraction.” It is:

> Remove a high-friction workflow around accelerated computing, make the improvement obvious, earn adoption or strategic dependence, and integrate closely enough with a platform that ownership becomes more rational than rebuilding or partnering.

A code-complete TrainCapsule with no users has essentially no acquisition pressure.

An acquisition-shaped TrainCapsule has:

- real protected workloads and repeat qualification;
- provider/customer VPC deployment;
- externally useful native exports;
- accepted upstream artifacts;
- measurable support or research value;
- a trusted open verifier/protocol where useful;
- private integrations and operational history;
- a specialized team beyond the founder;
- and a buyer-specific ownership case.

## 00.12 Career objective

Even when the business thesis fails, the bounded build can be a strong career asset if it contains:

- real PyTorch/c10d/NCCL integration;
- valid multi-process or multi-node execution;
- truthful first-boundary and reduction logic;
- a clean replay/contract demo;
- measured overhead;
- a threat model;
- a meaningful upstream attempt or accepted contribution;
- and the founder's ability to explain and defend every trust-critical design decision.

A generated repository that the founder cannot defend has weak hiring value.

## 00.13 Hard stop and pivot conditions

The loop must narrow, replace, or stop the commercial thesis when any of these persist after a bounded remediation cycle:

- the best native/bundled/agent workflow produces the same complete outcome;
- representative incidents cannot be reduced or investigated faithfully;
- reduced results disagree with production-like sentinels;
- instrumentation materially changes the incident;
- customer-local evidence access is generally unavailable;
- customers consistently prefer mitigation and accept residual uncertainty;
- exact or equivalent environments are unavailable or uneconomic;
- ordinary upstream changes repeatedly require trust-core rewrites;
- most useful contracts become ordinary tests with no remaining paid operation;
- no second commercial action follows a material result;
- delivery remains dominated by unique senior investigation labor at poor margins;
- a false confirmed hardware or component claim occurs;
- security containment fails;
- the reachable customer-controlled segment is too small and providers will not integrate;
- or acquisition framing begins to drive features that do not improve customer value.

## 00.14 Final authorization

**Build TrainCapsule.**

Build it as an option-preserving truth, experiment, recovery-assurance, and failure-derived qualification system—not as a recorder with an oversized roadmap.

The strongest immediate goal is:

```text
one supported distributed failure
→ native baseline
→ lower-cost faithful experiment
→ bounded recovery assurance
→ failure-derived qualification contract
→ clean independent execution
```

The strongest company goal is:

```text
several customers repeatedly use those contracts
→ stack changes and incidents flow through the product
→ providers or vendors consume its native/federated evidence
→ the workflow becomes operationally difficult to replace
```

No document can guarantee demand or acquisition. This decision removes the most avoidable reasons the product would fail before the market gets a chance to judge it.
