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
