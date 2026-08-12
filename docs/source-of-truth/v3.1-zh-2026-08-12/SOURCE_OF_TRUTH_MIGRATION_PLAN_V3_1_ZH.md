# Source-of-Truth Migration Plan V3.1-ZH
| Field | Value |
|---|---|
| Logical ID | `TC.V3_1_ZH.MIGRATION_PLAN` |
| Generation | `traincapsule-v3.1-zh-2026-08-12` |
| Authority class | `normative_migration` |
| Derived from | `TC.V3.SOURCE_MIGRATION_PLAN` |

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


## 1. Purpose

This plan installs the V3.1-ZH product and factory strategy without destroying the historical 9 August 2026 bundle or resuming an obsolete build graph.

The migration must be reversible, reviewable, and tied to an exact repository SHA.

## 2. Baseline

Audited baseline:

```text
repository: TasfiqJ/TrainCapsule
branch: main
commit: c31caefaeed7e605f6ef304fae6fcfe708a163b9
date reviewed: 11 August 2026
```

Before implementation, Codex must verify the current `main` SHA. When it differs, it must:

1. fetch the new commits;
2. summarize relevant changes;
3. re-run affected integrity and controller tests;
4. record the actual migration base SHA;
5. avoid assuming this audit is still exact.

## 3. Migration safety rules

- Pause the scheduled/autonomous controller before editing.
- Do not delete runtime evidence, queue records, checkpoints, or logs.
- Do not edit the old final bundle in place.
- Do not force-push.
- Do not merge directly to `main`.
- Work on a dedicated branch and open a draft PR.
- Preserve a rollback branch/tag or exact base SHA.
- Store a migration manifest containing old/new hashes.
- No AI-created independent machine-policy authorization.
- No synthetic external evidence may advance commercial milestones.
- No old active task automatically resumes after schema migration.

## 4. New document bundle

Create:

```text
docs/source-of-truth/v3.1-zh-2026-08-12/
├── README.md
├── 00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md
├── 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md
├── 04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md
├── 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md
├── 06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md
├── 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md
├── 13_SOURCE_REGISTER_V3_1_ZH.md
├── 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md
├── FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md
├── REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md
└── FINAL_MANIFEST_V3_1_ZH.json
```

The historical bundle remains:

```text
docs/source-of-truth/final-2026-08-09/
```

Add a clear archival marker inside a new adjacent README or index. Do not rewrite historical documents merely to remove conflicts.

## 5. New authority model

Replace one mixed hierarchy with two.

### 5.1 Normative product authority

```text
1. signed independent machine-policy authorizations for their exact scope
2. 00_EXECUTIVE_BUILD_DECISION_V3_1_ZH.md
3. 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3_1_ZH.md
4. 04_TECHNICAL_ARCHITECTURE_V3_1_ZH.md
5. 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3_1_ZH.md
6. 06_COMMERCIAL_MODEL_AND_GTM_V3_1_ZH.md
7. 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3_1_ZH.md
8. FACTORY_LOOP_REDESIGN_SPEC_V3_1_ZH.md
9. 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3_1_ZH.md
10. approved ADRs, pack specifications, security policies, and work-item packets
```

### 5.2 Current factual authority

```text
1. current official primary source or exact upstream code/version
2. dated source-register entry
3. current capability/claim register
4. affected internal narrative
```

A current source may mark a normative assumption stale. It may not silently change product policy. That requires an ADR or wedge decision.

### 5.3 Advisory documents

Acquisition and career documents remain advisory and must not be injected into routine product tasks.

## 6. `SOURCE_PRECEDENCE.md` replacement

The file should:

- identify V3.1-ZH as controlling;
- name the historical bundle;
- separate normative and factual authority;
- define conflict handling;
- define signed independent machine-policy authorization scope;
- prohibit source-monitor agents from rewriting policy;
- prohibit old duplicate filenames from active globs;
- state that product and commercial maturity are separate;
- define the baseline manifest.

## 7. `docs/CONTEXT_INDEX.yaml` replacement

Create role/task-specific groups.

```yaml
version: 3
groups:
  product_normative:
  technical_architecture:
  trust_core:
  commercial:
  roadmap:
  current_facts:
  factory_control:
  advisory_acquisition:
  advisory_career:
```

Rules:

- routine product tasks receive no acquisition/career context;
- factory repair receives factory-control context, not customer strategy;
- market research receives commercial/current-fact context, not product implementation;
- trust review receives trust/technical/current facts;
- each context entry includes digest and authority class;
- stale factual sources trigger a current-fact refresh, not automatic policy edits.

## 8. Duplicate and manifest cleanup

The old bundle includes byte-identical duplicate logical documents with `(1)` suffixes.

Migration actions:

1. leave the old physical files untouched for historical integrity;
2. exclude duplicates from active V3.1-ZH authority;
3. include one canonical logical document in V3.1-ZH;
4. define aliases only in a historical mapping file;
5. ensure no active script uses broad globs that include both copies.

## 9. Canonical hashing

Do not embed an ordinary self-hash inside the file being hashed.

`FINAL_MANIFEST_V3_1_ZH.json` contains:

```json
{
  "schemaVersion": 1,
  "generationId": "traincapsule-v3.1-zh-2026-08-12",
  "generatedAt": "...",
  "authorityModel": {
    "machineAuthorityIndependentOffRepository": true,
    "releaseFlow": "AUTOMATED_PR_REQUIRED_CHECKS_MACHINE_RECEIPT_AUTO_MERGE"
  },
  "documents": [
    {
      "logicalId": "...",
      "path": "...",
      "sha256": "...",
      "authorityClass": "...",
      "generationId": "traincapsule-v3.1-zh-2026-08-12",
      "sections": []
    }
  ],
  "coverageEvidence": {
    "path": "docs/source-of-truth/v3.1-zh-2026-08-12/SECTION_COVERAGE_V3_TO_V3_1_ZH.json",
    "sha256": "..."
  },
  "integrity": {
    "algorithm": "sha256",
    "documentCount": 11,
    "manifestSelfIncluded": false,
    "generatorPath": "scripts/generate_v3_1_zh_source.py"
  }
}
```

The manifest may omit its own hash or use an external detached digest. It must not create an impossible self-referential hash requirement.

## 10. Integrity gate

Create `scripts/gates/source_of_truth_integrity.py`.

It verifies:

- every active V3.1-ZH file exists;
- hashes match manifest;
- no unlisted normative file enters the active bundle;
- old archive is not treated as active;
- authority order is valid;
- current-fact and normative classes are distinct;
- no duplicate logical IDs;
- no self-hash contradiction;
- no absolute local paths;
- no active references to `(1)` duplicates;
- V3.1-ZH context index resolves;
- required independent machine-policy authorization policy exists;
- no external/commercial milestone is marked complete from synthetic evidence.

Run locally and in GitHub Actions.

## 11. Product/factory package separation

Change `pyproject.toml` from a factory-only package arrangement to a workspace or explicit multi-package setup.

At minimum:

- retain `tcfactory`;
- add product package paths;
- add product dependency groups;
- add product CLI entrypoint separately;
- configure Ruff/Pyright/Pytest for product and factory;
- do not exclude the active V3.1-ZH bundle from all integrity checking;
- avoid importing factory domain types into product packages.

## 12. Legacy roadmap migration

Create:

```text
factory/roadmap/migrations/v2_to_v3.yaml
```

For every legacy task:

```yaml
legacyTaskId:
legacyStatus:
legacyPacket:
v3Disposition:
mappedWorkItems:
reason:
evidencePreserved:
```

Rules:

- legacy tasks remain historical;
- broad architecture work defaults to deferred;
- no chain from T001 through T124 controls V3.1-ZH scheduling;
- current T002 is not automatically re-run;
- only concepts represented by explicit V3.1-ZH work items become active;
- old task artifacts retain original policy and SHA.

## 13. Queue and checkpoint migration

Procedure:

1. export queue listing and hashes;
2. checkpoint any live candidate;
3. stop controller;
4. move active V2 queue entries into an archive namespace;
5. do not alter candidate Git commits;
6. create V3.1-ZH queue directories;
7. add a salvage command for relevant candidate work;
8. record all moves in migration manifest;
9. require independent machine-policy decision before salvaging obsolete task work.

## 14. Configuration migration

Do not mutate V2 config in place without version handling.

- introduce config version 3;
- reject mixed V2/V3 runtime;
- provide a migration command;
- remove zero/unlimited semantics;
- set PR release mode;
- add scheduler, milestone, machine-policy receipt, evidence, executor files;
- validate before controller starts;
- preserve V2 files in Git history.

## 15. Runtime state migration

New state records must have explicit schemas and versions.

Do not load arbitrary old JSON into new models.

For each state file:

- parse using old model;
- emit normalized migration record;
- write V3.1-ZH state to a new path;
- preserve old file read-only;
- hash source and destination;
- test rollback.

## 16. GitHub migration

- create migration branch;
- push branch;
- open draft PR;
- run GitHub-hosted CPU checks;
- run optional self-hosted checks;
- require machine-policy evaluation for source authority and trust/release changes;
- enable auto-merge only after required exact-SHA checks and independent machine-policy authorization;
- do not alter branch protection automatically unless explicitly authorized.

## 17. CI migration

Keep current factory workflow temporarily but rename/clarify it.

Add:

- source-of-truth integrity;
- factory quality;
- product unit;
- product contract;
- security;
- controlled journey.

The migration PR must show which checks are required and which depend on local GPU infrastructure.

## 18. Prompt migration

Update prompts only after V3.1-ZH authority exists.

Every prompt must reference the V3.1-ZH context resolver and new work-item model.

Remove:

- work-until-done language;
- universal completion language;
- automatic roadmap expansion;
- implicit AI commercial authority;
- broad source injection.

Add:

- bounded outcome;
- finite limits;
- native-equivalence;
- external/machine-policy states;
- value rejection;
- no scope expansion.

## 19. Verification plan

### Static

- schemas;
- typing;
- lint;
- manifest;
- path rules;
- no duplicate authority;
- no direct-main release code path in active mode.

### Dynamic

- scheduler simulation;
- finite retry exhaustion;
- candidate preservation;
- external wait;
- policy block;
- rejected-value stop;
- milestone completion;
- proposal-only expansion;
- PR creation dry-run;
- launcher restart budget;
- V2 rollback.

### Adversarial

- forged independent machine-policy authorization;
- synthetic payment;
- stale source;
- modified old bundle;
- direct main push;
- zero retry limit;
- cross-lane global block;
- completion evaluation role attempting ledger mutation.

## 20. Rollback

Rollback conditions:

- migration corrupts queue or evidence;
- V3.1-ZH controller makes unauthorized changes;
- candidate preservation fails;
- source integrity is ambiguous;
- machine-authority root is writable by AI;
- release bypasses PR policy.

Rollback steps:

1. stop V3.1-ZH controller;
2. preserve V3.1-ZH artifacts/logs;
3. checkout exact migration base SHA or rollback branch;
4. restore archived runtime state to a separate copy;
5. run V2 deterministic verification;
6. do not automatically restart obsolete queued work;
7. document cause before retrying migration.

## 21. Final migration acceptance

Migration is accepted only when:

- old and new source bundles are distinguishable;
- hashes and authority pass;
- V3.1-ZH scheduler runs in observation mode correctly;
- no unlimited loops remain;
- no direct main promotion remains active;
- machine-policy/external evidence is unforgeable by AI roles;
- legacy task chain no longer defines company completion;
- product package can begin independently;
- rollback is demonstrated;
- qualified independent machine policy authorizes the source/release migration.
