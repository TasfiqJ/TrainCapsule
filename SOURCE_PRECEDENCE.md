# TrainCapsule source precedence

TrainCapsule V3.1-ZH is the controlling repository authority for the zero-founder-intervention factory and bounded product build. The only active normative generation is:

```text
docs/source-of-truth/v3.1-zh-2026-08-12/
```

Its canonical manifest is `docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json`. Runtime configuration exposes one `active_generation` value and every startup, packet, context, gate, publication, and milestone path must resolve that same manifest. Mixed normative generations fail closed.

The bundles at `docs/source-of-truth/final-2026-08-09/` and `docs/source-of-truth/v3-2026-08-11/` are immutable historical evidence. They remain byte-preserved and may be consulted only when an active V3.1-ZH source explicitly requests historical context. Neither controls new work.

## Normative authority

Apply active-generation sources in this order, highest first:

1. `00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md`.
2. `03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md`.
3. `04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md`.
4. `05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md`.
5. `06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md`.
6. `12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md`.
7. `FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md`.
8. `14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md`.
9. Other accepted V3.1-ZH ADRs, released pack specifications, security policies, and bounded work-item packets.

All paths are relative to the active V3.1-ZH bundle. A verified external receipt controls only its exact external-evidence scope; it never rewrites normative product or factory policy.

V3.1-ZH is an explicit owner-approved amendment, not a claim that immutable V3 required zero-human operation. It replaces V3's qualified-human runtime approvals with independent off-repository machine authority and makes exact-SHA, receipt-authorized, ordinary non-force pushes to `main` the sole publication route. Required post-push checks and automatic ordinary-push revert preserve the fail-closed boundary. The residual risk of removing qualified-human review is disclosed in every affected active document.

`config/owner_directives.yaml`, `config/human_approval.yaml`, `factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json`, and their migration ADRs are historical migration evidence only. They cannot shadow, authorize, or modify active V3.1-ZH policy.

## Current factual authority

Current technical, competitor, and upstream facts use a separate hierarchy:

1. Current official primary documentation, exact upstream source, or a primary paper for the version in question.
2. A dated, attributable entry in `13_SOURCE_REGISTER_V3_1_ZH.md`.
3. A current capability or claim register with verified evidence.
4. Internal narrative and planning material.

A source monitor may mark an affected assumption `STALE` or `RECHECK_REQUIRED` and create a bounded ADR or wedge-review proposal. It may not silently rewrite policy. External facts, customer activity, payment, GPU behavior, and market outcomes require attributable receipts and may remain `WAITING_EXTERNAL` without blocking unrelated lanes.

## Zero-founder-intervention authority

- No runtime state waits for human approval.
- No candidate-writing agent or agent-visible repository file may self-certify trust, release, or activation.
- Independent off-repository machine authority issues signed, scoped, expiring, revocable receipts for the exact candidate SHA and evidence digests.
- Candidate publication is exact-SHA direct-to-`main` only after deterministic gates and a valid independent machine receipt. Pull requests, candidate branches, force pushes, deletion, and bypass are forbidden.
- Activation requires a signed external activation receipt bound to the exact merged SHA and verified runtime state.
- Missing machine authority is `BLOCKED_POLICY`; missing external truth is `WAITING_EXTERNAL`; neither may be fabricated or silently promoted.

## Advisory and historical material

- Acquisition and career documents are advisory and excluded from routine product, factory, completion, and release contexts.
- `TRAINCAPSULE_V3_MASTER_PLAN.md` is a historical navigation/consolidation artifact, not an active logical authority document.
- The V3 and V3.1 remediation prompts control their migrations but are not runtime product authority unless installed in the canonical active manifest.
- Repository audits are evidence about reviewed states; they do not outrank active normative documents.
- Duplicate historical filenames containing `(1)` are never active sources and broad globs are prohibited.

## Conflict handling

When active normative sources conflict, or when a required current fact is stale or unavailable:

1. stop only the affected work item;
2. preserve the conflict and exact evidence;
3. record `STALE`, `RECHECK_REQUIRED`, `WAITING_EXTERNAL`, `BLOCKED_POLICY`, or another truthful scoped state;
4. create a bounded machine-reviewable ADR or wedge-review proposal when policy or strategy may need change;
5. continue independent work in unaffected lanes.

Source monitors and engineering agents may propose changes. They may not rewrite the active manifest, normative sources, machine-authority policy, external receipts, external facts, or commercial maturity.

## Product and commercial truth

Engineering maturity and commercial maturity are independent. Controlled fixtures, AI reviews, repository documents, and internal tests cannot establish customer conversations, payment, decision value, repeat use, independent operation, or commercial support. Synthetic evidence remains labeled and cannot advance an external milestone. A technically valid native duplicate fails value unless a complete-substitute benchmark demonstrates an incremental decision advantage.

## Integrity and context

- Run `python scripts/gates/source_of_truth_integrity.py` to verify active generation, context, and authority.
- The active manifest excludes its own hash and uses normalized UTF-8 LF text with one trailing newline.
- `docs/CONTEXT_INDEX.yaml` contains only explicit, digest-bound, role-scoped entries from the active normative generation plus separately classified current facts.
- No active source or context entry may use an absolute machine-local path.
- The 124-item legacy inventory remains hash-preserved and T002 remains nonblocking historical evidence.

Any manifest mismatch, mixed normative generation, duplicate logical ID, missing source, unresolved context path, stale required fact, agent-writable machine authority, absent required verifier receipt, or synthetic commercial completion is a fail-closed condition for the affected claim, work item, release, or activation.
