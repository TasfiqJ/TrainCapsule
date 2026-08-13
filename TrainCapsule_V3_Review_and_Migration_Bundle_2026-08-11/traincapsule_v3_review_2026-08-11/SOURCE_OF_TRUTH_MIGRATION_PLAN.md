# Source-of-Truth and Repository Migration Plan

## 1. Purpose

This plan installs the V3 product and factory strategy without destroying the historical 9 August 2026 bundle or resuming an obsolete build graph.

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
- No AI-created human approval.
- No synthetic external evidence may advance commercial milestones.
- No old active task automatically resumes after schema migration.

## 4. New document bundle

Create:

```text
docs/source-of-truth/v3-2026-08-11/
├── README.md
├── 00_EXECUTIVE_BUILD_DECISION_V3.md
├── 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md
├── 04_TECHNICAL_ARCHITECTURE_V3.md
├── 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md
├── 06_COMMERCIAL_MODEL_AND_GTM_V3.md
├── 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md
├── 13_SOURCE_REGISTER_V3.md
├── 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md
├── FACTORY_LOOP_REDESIGN_SPEC.md
├── REPOSITORY_AUDIT_AND_FILE_CHANGE_MATRIX.md
└── FINAL_MANIFEST_V3.json
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
1. signed human approvals for their exact scope
2. 00_EXECUTIVE_BUILD_DECISION_V3.md
3. 03_PRODUCT_STRATEGY_AND_REQUIREMENTS_V3.md
4. 04_TECHNICAL_ARCHITECTURE_V3.md
5. 05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC_V3.md
6. 06_COMMERCIAL_MODEL_AND_GTM_V3.md
7. 12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md
8. FACTORY_LOOP_REDESIGN_SPEC.md
9. 14_CLAUDE_CODE_MASTER_BUILD_PROMPT_V3.md
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

- identify V3 as controlling;
- name the historical bundle;
- separate normative and factual authority;
- define conflict handling;
- define signed human approval scope;
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
2. exclude duplicates from active V3 authority;
3. include one canonical logical document in V3;
4. define aliases only in a historical mapping file;
5. ensure no active script uses broad globs that include both copies.

## 9. Canonical hashing

Do not embed an ordinary self-hash inside the file being hashed.

`FINAL_MANIFEST_V3.json` contains:

```json
{
  "manifestVersion": 3,
  "bundleVersion": "v3-2026-08-11",
  "generatedAt": "...",
  "migrationBaseSha": "...",
  "hashAlgorithm": "sha256",
  "canonicalization": {
    "textEncoding": "utf-8",
    "lineEndings": "lf",
    "trailingNewline": true
  },
  "files": [
    {
      "path": "...",
      "sha256": "...",
      "bytes": 0,
      "authorityClass": "normative"
    }
  ]
}
```

The manifest may omit its own hash or use an external detached digest. It must not create an impossible self-referential hash requirement.

## 10. Integrity gate

Create `scripts/gates/source_of_truth_integrity.py`.

It verifies:

- every active V3 file exists;
- hashes match manifest;
- no unlisted normative file enters the active bundle;
- old archive is not treated as active;
- authority order is valid;
- current-fact and normative classes are distinct;
- no duplicate logical IDs;
- no self-hash contradiction;
- no absolute local paths;
- no active references to `(1)` duplicates;
- V3 context index resolves;
- required human-approval policy exists;
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
- do not exclude the active V3 bundle from all integrity checking;
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
- no chain from T001 through T124 controls V3 scheduling;
- current T002 is not automatically re-run;
- only concepts represented by explicit V3 work items become active;
- old task artifacts retain original policy and SHA.

## 13. Queue and checkpoint migration

Procedure:

1. export queue listing and hashes;
2. checkpoint any live candidate;
3. stop controller;
4. move active V2 queue entries into an archive namespace;
5. do not alter candidate Git commits;
6. create V3 queue directories;
7. add a salvage command for relevant candidate work;
8. record all moves in migration manifest;
9. require human decision before salvaging obsolete task work.

## 14. Configuration migration

Do not mutate V2 config in place without version handling.

- introduce config version 3;
- reject mixed V2/V3 runtime;
- provide a migration command;
- remove zero/unlimited semantics;
- set PR release mode;
- add scheduler, milestone, approval, evidence, executor files;
- validate before controller starts;
- preserve V2 files in Git history.

## 15. Runtime state migration

New state records must have explicit schemas and versions.

Do not load arbitrary old JSON into new models.

For each state file:

- parse using old model;
- emit normalized migration record;
- write V3 state to a new path;
- preserve old file read-only;
- hash source and destination;
- test rollback.

## 16. GitHub migration

- create migration branch;
- push branch;
- open draft PR;
- run GitHub-hosted CPU checks;
- run optional self-hosted checks;
- require human review for source authority and trust/release changes;
- do not enable auto-merge during migration;
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

Update prompts only after V3 authority exists.

Every prompt must reference the V3 context resolver and new work-item model.

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
- external/human states;
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
- human wait;
- rejected-value stop;
- milestone completion;
- proposal-only expansion;
- PR creation dry-run;
- launcher restart budget;
- V2 rollback.

### Adversarial

- forged human approval;
- synthetic payment;
- stale source;
- modified old bundle;
- direct main push;
- zero retry limit;
- cross-lane global block;
- completion reviewer attempting ledger mutation.

## 20. Rollback

Rollback conditions:

- migration corrupts queue or evidence;
- V3 controller makes unauthorized changes;
- candidate preservation fails;
- source integrity is ambiguous;
- approval root is writable by AI;
- release bypasses PR policy.

Rollback steps:

1. stop V3 controller;
2. preserve V3 artifacts/logs;
3. checkout exact migration base SHA or rollback branch;
4. restore archived runtime state to a separate copy;
5. run V2 deterministic verification;
6. do not automatically restart obsolete queued work;
7. document cause before retrying migration.

## 21. Final migration acceptance

Migration is accepted only when:

- old and new source bundles are distinguishable;
- hashes and authority pass;
- V3 scheduler runs in observation mode correctly;
- no unlimited loops remain;
- no direct main promotion remains active;
- human/external evidence is unforgeable by AI roles;
- legacy task chain no longer defines company completion;
- product package can begin independently;
- rollback is demonstrated;
- qualified human approves the source/release migration.
