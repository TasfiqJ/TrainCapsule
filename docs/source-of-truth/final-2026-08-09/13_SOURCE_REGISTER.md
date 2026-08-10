# 13 — Source Register and Claim Boundaries

## Research rules

- Primary official documentation and original papers are preferred.
- Vendor documentation establishes public product capability and vendor claims, not independent performance.
- Preprints establish author-reported findings, not universal industry rates.
- Public absence does not prove internal absence.
- Current product scope must be rechecked before public claims or customer work.
- Strategic conclusions are labeled reasoned inferences.
- Commercial demand and price remain unproven until payment and repeat use.

## Sources

### S01 — PyTorch Flight Recorder engineering report

**Title:** Flight Recorder: A New Lens for Understanding NCCL Watchdog Timeouts  
**Publisher:** PyTorch, 25 March 2026  
**URL:** https://pytorch.org/blog/flight-recorder-a-new-lens-for-understanding-nccl-watchdog-timeouts/

Supports:

- NCCL timeout is a catch-all symptom;
- cross-rank evidence is required;
- Flight Recorder automatically dumps c10d evidence;
- offline analysis and earlier debug-performance limitations.

Does not support:

- TrainCapsule demand or superiority.

### S02 — TorchFT

**Title:** Fault tolerance for PyTorch  
**Publisher:** PyTorch GitHub organization  
**URL:** https://github.com/pytorch/torchft

Supports:

- per-step health coordination;
- reconfigurable process groups;
- live recovery from healthy peers;
- DDP/HSDP fault-tolerance primitives.

### S03 — NVIDIA Mission Control Autonomous Job Recovery

**Title:** NMC Autonomous Job Recovery User Guide  
**Publisher:** NVIDIA  
**URL:** https://docs.nvidia.com/mission-control/docs/systems-quick-start-guide/2.2.0/ajr/ajr-overview.html

Supports:

- automated detection, isolation, and recovery in supported AI supercomputer environments.

Vendor documentation; performance and breadth require customer verification.

### S04 — SageMaker HyperPod in-process and checkpointless recovery

**Title:** In-process recovery and checkpointless training  
**Publisher:** AWS  
**URL:** https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-eks-checkpointless-in-process-recovery.html

Supports:

- in-memory checkpoints;
- peer-to-peer recovery;
- coordinated abort/restart barriers.

### S05 — PyTorch 2.12 release

**Title:** PyTorch 2.12 Release Blog  
**Publisher:** PyTorch, 13 May 2026  
**URL:** https://pytorch.org/blog/pytorch-2-12-release-blog/

Supports:

- continued Flight Recorder analyzer expansion across backends and operations.

### S06 — NVIDIA Autonomous Recovery Engine release notes

**Title:** Autonomous Recovery Engine release notes  
**Publisher:** NVIDIA  
**URL:** https://docs.nvidia.com/mission-control/docs/systems-quick-start-guide/2.0.0/are-release-notes.html

Supports:

- attribution pipeline and automated recovery-policy development in supported systems.

### S07 — HyperPod feature boundaries

**Title:** Using elastic training in SageMaker HyperPod  
**Publisher:** AWS  
**URL:** https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-eks-elastic-training.html

Supports:

- current combinations and limitations among resilience features.

### S08 — HyperPod checkpointless feature architecture

**Title:** HyperPod checkpointless training features  
**Publisher:** AWS  
**URL:** https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-eks-checkpointless-features.html

Supports:

- communication initialization, data loading, and restart optimizations as a combined native stack.

### S09 — Full AI lifecycle infrastructure

**Title:** NVIDIA Vera Rubin Opens Agentic AI Frontier  
**Publisher:** NVIDIA, 16 March 2026  
**URL:** https://nvidianews.nvidia.com/news/nvidia-vera-rubin-platform

Supports:

- current infrastructure strategy spanning pre-training, post-training, test-time scaling, and inference.

Vendor announcement; not market-share proof.

### S10 — Large-scale RL post-training architecture

**Title:** Miles: A PyTorch-Native Stack for Large-Scale LLM RL Post-Training  
**Publisher:** PyTorch, 30 June 2026  
**URL:** https://pytorch.org/blog/miles-a-pytorch-native-stack-for-large-scale-llm-rl-post-training/

Supports:

- modern post-training as a distributed system combining rollout, training, Ray, NCCL/RDMA synchronization, MoE, observability, and fault tolerance.

### S11 — Megatron parallelism

**Title:** Parallelism Strategies Guide  
**Publisher:** NVIDIA Megatron Core  
**URL:** https://docs.nvidia.com/megatron-core/developer-guide/latest/user-guide/parallelism-guide.html

Supports:

- combined data, tensor, pipeline, context, and expert parallelism across large GPU systems.

### S12 — AMD/PyTorch distributed expansion

**Title:** Bringing PyTorch Monarch to AMD GPUs  
**Publisher:** PyTorch, 6 July 2026  
**URL:** https://pytorch.org/blog/bringing-pytorch-monarch-to-amd-gpus-single-controller-distributed-training-on-rocm/

Supports:

- distributed training/runtime expansion and recovery on ROCm/AMD.

### S13 — PyTorch reproducibility limits

**Title:** Reproducibility  
**Publisher:** PyTorch documentation, updated 14 May 2026  
**URL:** https://docs.pytorch.org/docs/stable/notes/randomness.html

Supports:

- complete reproducibility is not guaranteed across releases, commits, or platforms.

### S14 — CUDA compatibility

**Title:** CUDA Compatibility  
**Publisher:** NVIDIA  
**URL:** https://docs.nvidia.com/deploy/cuda-compatibility/index.html

Supports:

- applications/toolkits depend on documented driver compatibility limits.

### S15 — ARGUS

**Title:** ARGUS: Production-Scale Tracing and Performance Diagnosis for over 10,000-GPU Clusters  
**Source:** arXiv 2606.20374, 2026  
**URL:** https://arxiv.org/abs/2606.20374

Supports author-reported:

- always-on cross-layer tracing at 10,000+ GPU scale;
- combined overhead below 2%;
- substantial event compression.

Preprint; environment-specific.

### S16 — SysOM-AI

**Title:** SysOM-AI: Continuous Cross-Layer Performance Diagnosis for Production AI Training  
**Source:** arXiv 2603.29235, 2026  
**URL:** https://arxiv.org/abs/2603.29235

Supports author-reported:

- deployment across 80,000+ GPUs;
- below 0.4% overhead;
- 94 confirmed diagnoses;
- large diagnosis-time reduction.

Preprint and organization-specific.

### S17 — SDCHUNTER

**Title:** SDCs in the Wild: Characterizing and Diagnosing SDC-defective GPUs in Large-scale Training Systems  
**Venue:** USENIX OSDI 2026  
**URL:** https://www.usenix.org/conference/osdi26/presentation/zheng

Supports:

- generic tests can miss workload/data-specific defects;
- exact workload replay can localize selected hardware faults;
- author-reported production incident results.

Does not support hardware replay for every incident class.

### S18 — 2026 AI Index

**Title:** The 2026 AI Index Report  
**Publisher:** Stanford HAI  
**URL:** https://hai.stanford.edu/ai-index/2026-ai-index-report

Supports:

- current broad AI adoption and industry production of notable models.

Does not enumerate TrainCapsule-qualified distributed-workload operators.

### S19 — AWS support log collectors

**Title:** Troubleshoot problems with Amazon EKS clusters and nodes  
**Publisher:** AWS  
**URL:** https://docs.aws.amazon.com/eks/latest/userguide/troubleshooting.html

Supports:

- providers already use native diagnostic bundles for support cases.

### S20 — NVIDIA NVDebug

**Title:** NVDebug log collection documentation  
**Publisher:** NVIDIA  
**URL:** https://docs.nvidia.com/multi-node-nvlink-systems/nvdebug-guide/oob_collector_shell_script.html

Supports:

- NVIDIA-specific collection of detailed support/debug bundles.

### S21 — GPU confidential-container attestation

**Title:** Attestation — NVIDIA Confidential Containers Architecture  
**Publisher:** NVIDIA  
**URL:** https://docs.nvidia.com/datacenter/cloud-native/confidential-containers/latest/attestation.html

Supports:

- remote proof of CPU/GPU guest state before secret release.

### S22 — Confidential Containers architecture and limits

**Title:** NVIDIA Confidential Containers Reference Architecture  
**Publisher:** NVIDIA  
**URL:** https://docs.nvidia.com/datacenter/cloud-native/confidential-containers/latest/overview.html

Supports:

- Kata/GPU Operator architecture;
- supported single/multi-GPU modes and deployment constraints.

### S23 — OCI artifacts

**Title:** OCI Image and Distribution Specs v1.1 Releases  
**Publisher:** Open Container Initiative  
**URL:** https://opencontainers.org/posts/blog/2024-03-13-image-and-distribution-1-1/

Supports:

- artifact types, subjects, and referrers for associated metadata artifacts.

### S24 — Sigstore and in-toto attestations

**Title:** In-Toto Attestations / Cosign verification  
**Publisher:** Sigstore  
**URL:** https://docs.sigstore.dev/cosign/verifying/attestation/

Supports:

- signing and policy validation of structured attestations.

### S25 — CoreWeave Mission Control

**Title:** Mission Control — The Operating Standard for AI  
**Publisher:** CoreWeave  
**URL:** https://www.coreweave.com/mission-control

Supports current public claims that Mission Control:

- is included as part of CoreWeave Cloud;
- includes cluster observability and lifecycle health management;
- offers rank/GPU/node straggler detection for distributed training;
- includes an interactive agent and direct-to-expert support;
- and exposes proactive remediation paths.

Vendor claims; not independent proof of performance or customer value.

### S26 — Crusoe AutoClusters

**Title:** Automated Node Remediation with AutoClusters  
**Publisher:** Crusoe Cloud documentation  
**URL:** https://docs.crusoecloud.com/orchestration/cmk/autoclusters/index.html

Supports current documented capability to:

- monitor selected hardware issues;
- restart or replace nodes;
- reschedule workloads;
- record remediation history;
- and expose manual/open-loop remediation integration.

Capability is limited to supported versions, instance types, policies, and conditions.

### S27 — Chamber

**Title:** Chamber — Your AIOps Teammate for GPU Infrastructure  
**Publisher:** Chamber  
**URL:** https://www.usechamber.io/

Supports current public positioning around:

- cross-cloud workload monitoring;
- AI-agent root-cause and remediation;
- configuration repair and checkpoint rerun;
- and incident replay.

Company marketing; no independent performance validation is inferred.

### S28 — Caladrius

**Title:** Caladrius Platform  
**Publisher:** Caladrius  
**URL:** https://www.caladrius.ai/platform

Supports current public positioning around:

- root-cause analysis across device, fabric, storage, and workload;
- approved remediation;
- and verification of the result.

Company marketing; no independent performance validation is inferred.

### S29 — OpGuard

**Title:** OpGuard: Bitwise Alignment for Precise and General LLM Training Debugging  
**Publisher:** USENIX OSDI 2026  
**URL:** https://www.usenix.org/conference/osdi26/presentation/zhou-ziming

Supports:

- operator-boundary bitwise alignment as a production debugging primitive;
- first divergent operator localization;
- author-reported deployment across pre-training and post-training;
- more than twenty diagnosed production issues and days-to-minutes examples.

Does not support:

- universal numerical replay;
- TrainCapsule demand;
- or that TrainCapsule should reimplement OpGuard.

### S30 — PrismLLM

**Title:** A Few GPUs, A Whole Lotta Scale: Faithful LLM Training Emulation with PrismLLM  
**Publisher:** arXiv, May 2026  
**URL:** https://arxiv.org/abs/2605.15617

Supports author-reported:

- execution-graph slicing;
- virtual participants and hybrid emulation;
- up to 8,192-GPU emulation with fewer than 1% of physical GPUs in evaluated workloads;
- 0.58% average iteration-time error and less than 0.01% peak-memory error in the reported evaluation.

Does not support:

- universal semantic failure reproduction;
- general accuracy across all workloads;
- or TrainCapsule demand.

### S31 — OpenAI–Astral acquisition announcement

**Title:** OpenAI to acquire Astral  
**Publisher:** OpenAI, 19 March 2026  
**URL:** https://openai.com/index/openai-to-acquire-astral/

Supports:

- broad open-source developer workflow adoption;
- direct fit with the acquirer's developer ecosystem;
- acquisition pattern involving an established workflow and team.

### S32 — Anthropic–Bun acquisition announcement

**Title:** Anthropic acquires Bun as Claude Code reaches $1B milestone  
**Publisher:** Anthropic, 3 December 2025  
**URL:** https://www.anthropic.com/news/anthropic-acquires-bun-as-claude-code-reaches-usd1b-milestone

Supports:

- broad external adoption;
- months of close partnership;
- Bun's role as important Claude Code infrastructure;
- acquisition pattern involving strategic dependence.

### S33 — OpenAI–Neptune acquisition announcement

**Title:** OpenAI to acquire Neptune  
**Publisher:** OpenAI, 3 December 2025  
**URL:** https://openai.com/index/openai-to-acquire-neptune/

Supports:

- specialized experiment/training analysis directly relevant to frontier-model workflow;
- strategic workflow fit as an acquisition factor.

### S34 — NVIDIA Brev current product and acquisition evidence

**Title:** NVIDIA Brev Console and NVIDIA author biography  
**Publishers:** NVIDIA  
**URLs:**
- https://brev.nvidia.com/
- https://developer.nvidia.com/blog/author/amaddipoti/
- https://developer.nvidia.com/blog/deploy-gpu-optimized-ai-software-with-one-click-using-brev-dev-and-nvidia-ngc-catalog/

Supports:

- Brev's current NVIDIA product position around multi-cloud GPU development;
- NVIDIA's statement that Brev.dev was acquired by NVIDIA;
- workflow simplification and one-click accelerated-software deployment.

Does not support:

- that TrainCapsule will follow the same acquisition path.

### S35 — OCI Image and Distribution Specifications 1.1

**Title:** OCI Image and Distribution Specifications 1.1  
**Publisher:** Open Container Initiative  
**URL:** https://opencontainers.org/posts/blog/2024-03-13-image-and-distribution-1-1/

Supports:

- artifact types, subjects, and referrers for associated supply-chain and metadata artifacts.

### S36 — Sigstore and in-toto attestations

**Titles:** Sigstore documentation; in-toto Attestation Framework  
**Publishers:** Sigstore; in-toto  
**URLs:**
- https://docs.sigstore.dev/
- https://in-toto.io/
- https://github.com/in-toto/attestation

Supports:

- signed software artifacts;
- identity-bound verification;
- supply-chain attestations and provenance models.

### S37 — SLSA

**Title:** Supply-chain Levels for Software Artifacts  
**Publisher:** OpenSSF/SLSA  
**URL:** https://slsa.dev/

Supports:

- provenance and build-integrity framework for released software.

### S38 — OpenAI Hardware Health role

**Title:** Software Engineer, Hardware Health  
**Publisher:** OpenAI Careers  
**URL:** https://openai.com/careers/software-engineer-hardware-health-san-francisco/

Supports career alignment with:

- observing, detecting, remediating, and verifying issues across hardware and platform infrastructure.

### S39 — OpenAI GPU Infrastructure — HPC role

**Title:** Software Engineer, GPU Infrastructure — HPC  
**Publisher:** OpenAI Careers  
**URL:** https://openai.com/careers/software-engineer-gpu-infrastructure-hpc-san-francisco/

Supports career alignment with:

- fleet reliability;
- comprehensive systems investigations;
- automation;
- performance bottleneck removal.

### S40 — OpenAI Workload Enablement role

**Title:** Software Engineer, Workload Enablement  
**Publisher:** OpenAI Careers  
**URL:** https://openai.com/careers/software-engineer-workload-enablement-san-francisco/

Supports career alignment with workload integration, systems debugging, and enabling complex AI workloads. Verify the current role URL and availability before public use.

### S41 — Anthropic GPU performance role

**Title:** Performance Engineer, GPU  
**Publisher:** Anthropic Careers  
**URL:** https://www.anthropic.com/careers/jobs/4926227008

Supports career alignment with:

- large-scale training infrastructure;
- NCCL;
- fault tolerance;
- cluster orchestration;
- measurable performance impact.

## Claim-to-source matrix

| Claim | Support | Boundary |
|---|---|---|
| Native recovery and diagnosis are expanding | S01–S08 | public supported capabilities only |
| Workloads are broadening beyond simple synchronous pre-training | S09–S12 | current public stack direction |
| Exact replay is not universal across versions/platforms | S13–S14 | official compatibility/reproducibility limits |
| Low-overhead cross-layer capture is feasible in selected systems | S15–S16 | author-reported internal deployments |
| Exact workload replay can help selected SDC cases | S17 | one mechanism family |
| Broad AI adoption is growing | S18 | not TrainCapsule market size |
| Providers already have native support bundles | S19–S20 | support workflow fact, not proof of rejection |
| Attested/federated execution is technically possible | S21–S24 | supported platforms and policies only |
| Cloud/platform reliability is increasingly bundled with compute/support | S25–S26 | public capability and packaging only |
| Broad AI-agent/full-loop GPU operations surfaces are commercially occupied | S25, S27–S28 | vendor positioning, not independent performance |
| Operator alignment is an occupied research primitive | S29 | author-reported production system; integration baseline |
| Scale-faithful emulation is an occupied research primitive | S30 | evaluated workloads only; integration baseline |
| Strategic acquisitions commonly involve adopted/dependent workflows and team fit | S31–S34 | selected official examples, not a predictive rule |
| OCI and standard attestations can represent signed capsule relationships | S35–S37 | standards capability, not deployment proof |
| TrainCapsule work maps to current AI-infrastructure roles | S38–S41 | role alignment, not a hiring guarantee |
| Customers will pay repeatedly | none | unproven |
| The first pack beats Flight Recorder | none | validation hypothesis |
| Faithful reduction will work on most incidents | none | unproven |
| Incident contracts create renewal | none | unproven |
| A provider will adopt the format | none | unproven |
| TrainCapsule is defensible | none yet | requires incremental value beyond bundled tools, repeat use, switching cost, and acceptable maintenance economics |
| Acquisition will occur | none | not a product claim |

## Unsupported public claims

The company must not claim:

- every large training job fails frequently;
- most organizations train large models;
- TrainCapsule can reproduce every incident;
- the first observed divergence is root cause;
- its reproducer is globally smallest;
- a reduced pass proves full-workload safety;
- a short canary proves model quality;
- exact workload replay proves every hardware defect;
- no major company has an internal equivalent;
- a standalone product will beat bundled provider economics;
- incident contracts necessarily create recurring value after upstreaming;
- historical source hardware will remain available;
- ordinary adapter maintenance will be inexpensive;
- providers will accept a new standard;
- target pricing is validated;
- recurring revenue is likely;
- acquisition is likely;
- or a completed repository has enterprise value without use.

## Source maintenance

Before every public release or customer engagement:

- recheck current PyTorch/Flight Recorder APIs;
- recheck NCCL and Mission Control scope;
- recheck HyperPod and cloud recovery features;
- recheck competitor product surfaces, packaging, and whether capabilities are bundled;
- recheck OpGuard, PrismLLM, and new diagnosis/emulation research for integration or absorption;
- recheck acquisition examples before using them as strategic analogies;
- recheck career-role URLs and current responsibilities before public claims;
- recheck customer-approved coding/operations agent baselines;
- recheck supported framework/accelerator lanes and deprecations;
- verify paper versions and review status;
- verify CUDA/driver compatibility;
- record source digests and access dates;
- update affected packs and claims;
- issue a stop/integrate/redesign decision when native capabilities close a gap.

---
