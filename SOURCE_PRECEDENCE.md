# TrainCapsule source precedence

TrainCapsule V3 is the controlling repository authority for the bounded migration and product build. The active bundle is:

```text
docs/source-of-truth/v3-2026-08-11/
```

The migration base is `6b480232fa92b069103da44c475bd17bcb3e6bd1`. The V3 manifest is `docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json`.

The previous bundle at `docs/source-of-truth/final-2026-08-09/` is immutable historical evidence. It remains byte-preserved and may be consulted only when an active V3 source explicitly asks for historical context. It does not control new work.

## Normative authority

Apply these sources in order, highest first:

1. A verified human approval for its exact scope, candidate SHA, artifact digests, conditions, and validity period.
2. `00_EXECUTIVE_BUILD_DECISION_V3.md`.
3. `03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md`.
4. `04_TECHNICAL_ARCHITECTURE_V3.md`.
5. `05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md`.
6. `06_COMMERCIAL_MODEL_AND_GTM_V3.md`.
7. `12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md`.
8. `FACTORY_LOOP_REDESIGN_SPEC.md`.
9. `14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md`.
10. Accepted ADRs, released pack specifications, security policies, and bounded work-item packets.

Paths in items 2–9 are relative to the active V3 bundle.

Human approval is authoritative only when it passes the configured trusted-root verifier. A repository file created by an AI role is not human approval.

## Current factual authority

Current technical, competitor, and upstream facts use a separate hierarchy:

1. Current official primary documentation, exact upstream source, or a primary paper for the version in question.
2. A dated entry in `13_SOURCE_REGISTER_V3.md`.
3. A current capability or claim register with attributable evidence.
4. Internal narrative and planning material.

A current fact may mark a normative assumption `STALE`. It may not silently rewrite policy. Policy changes require an accepted ADR, scoped approval, or recorded wedge decision.

## Advisory and historical material

- Acquisition and career documents are advisory and excluded from routine product, factory, completion, and release contexts.
- `TRAINCAPSULE_V3_MASTER_PLAN.md` is a navigation/consolidation artifact in the review bundle, not an additional active logical authority document.
- `CODEX_MASTER_MIGRATION_PROMPT.md` controls this migration procedure but is not installed as product authority.
- The V3 repository audit is evidence about the reviewed repository state; it does not outrank normative V3 documents.
- Duplicate historical filenames containing `(1)` are never active sources and must not be included by broad globs.

## Conflict handling

When active normative sources conflict, or when a required current fact is stale or unavailable:

1. stop only the affected work item;
2. preserve the conflict and evidence;
3. record `STALE`, `WAITING_HUMAN`, `BLOCKED_POLICY`, or another truthful scoped state;
4. create an ADR or wedge-review request when policy must change;
5. continue independent work in unaffected lanes.

Source monitors and engineering agents may propose changes. They may not rewrite normative policy, human approvals, external receipts, or commercial maturity.

## Product and commercial truth

Engineering maturity and commercial maturity are independent. Controlled fixtures, AI reviews, repository documents, and internal tests cannot establish customer conversations, payment, decision value, repeat use, independent operation, or commercial support. Synthetic evidence must remain labeled and cannot advance an external milestone.

## Integrity and context

- Run `python scripts/gates/source_of_truth_integrity.py` to verify the active bundle, context index, and authority model.
- The active manifest excludes its own hash and uses normalized UTF-8 LF text with one trailing newline.
- `docs/CONTEXT_INDEX.yaml` provides explicit, role-scoped context groups. Routine product work receives no acquisition or career material.
- No active source or context entry may use an absolute machine-local path.

Any manifest mismatch, duplicate active logical ID, unresolved required context path, agent-writable approval root, or synthetic commercial completion is a fail-closed condition for the affected authority or release action.
