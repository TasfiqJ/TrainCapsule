# TrainCapsule V3 Zero-Human Conformance Audit

**Audit date:** 12 August 2026  
**Repository:** `TasfiqJ/TrainCapsule`  
**Repository SHA reviewed:** `26c855efbe9178066a10c8981c32bf5b2a07a6c6`  
**Original V3 audit baseline:** `c31caefaeed7e605f6ef304fae6fcfe708a163b9`  
**Supplied bundle:** `traincapsule_v3_review_2026-08-11`  
**Method:** fail-closed; a requirement is treated as absent or defective until supported by executable code, exact-SHA tests, and—where required—live or external evidence.

## Executive verdict

**The current repository does not fully match the supplied V3 bundle.**

It also **does not yet implement a proven, safe, fully autonomous zero-operator loop**.

There are two distinct reasons:

1. **Strict V3 conformance fails by design.** The repository copied the V3 documents byte-for-byte, then installed higher-precedence owner directives that reverse two explicit V3 controls: qualified-human approval and pull-request-first release. This is a disclosed policy fork, not full conformance.
2. **The amended zero-human design is incomplete in runtime code.** Important V3 structures exist—typed lanes, finite limits, source integrity, separate product packages, external evidence receipts, split CI—but the live controller does not yet exercise many of them. Several critical policies are schema-only, test-only, static-ledger-only, or simulation-only.

The current state is best named:

```text
V3-ZH MIGRATION SCAFFOLD
+ CONTROLLED PRODUCT PREFLIGHT
+ UNPROVEN LIVE AUTONOMOUS CONTROLLER
+ UNSAFE/INCOMPLETE MACHINE RELEASE AUTHORITY
```

It is not yet:

```text
FULLY AUTONOMOUS PRODUCTION FACTORY
or
FULL V3 BUNDLE CONFORMANCE
```

## What “zero human intervention” can truthfully mean

Use this exact operating definition:

> **ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP:** after credentials, permissions, external machine-verifier roots, GitHub rules, and runtime installation are configured once, the engineering factory plans, executes, tests, repairs, pauses, resumes, opens releases, merges qualifying work, advances milestones, and stops weak work without founder/operator action.

This definition still permits external people and organizations to create facts the factory cannot manufacture:

- customer conversations;
- evidence-access permission;
- incident archives;
- payment;
- customer-local execution authority;
- operator use;
- renewal;
- upstream acceptance.

Those remain signed/attributable `WAITING_EXTERNAL` inputs. A doctrine of literally “no human anywhere” cannot truthfully complete the commercial milestones because the milestones themselves concern actions by customers, operators, and maintainers.

## Strict-bundle versus amended-plan verdict

| Question | Verdict |
|---|---|
| Were the supplied V3 files copied and hashed correctly? | **Yes** |
| Does the active repository preserve the original V3 semantics? | **No** |
| Is the zero-human change clearly represented as a new complete source generation? | **No** |
| Are finite limits represented in configuration? | **Yes** |
| Are those limits fully executed by the live controller? | **No** |
| Does the V3 controller have a real, durable Claude resume path? | **No** |
| Can market/competitor research tasks currently write and use allowlisted network sources? | **No** |
| Is machine policy approval independent and mandatory before release? | **No** |
| Are releases contained before reaching `main`? | **No** |
| Are required GitHub checks enforced server-side? | **No** |
| Has a real Claude-backed unattended cycle been proven? | **No** |
| Has live crash/quota/release recovery been proven? | **No** |
| Is the bounded product preflight substantial and tested? | **Yes, controlled/CPU scope** |
| Is real GPU/native/customer/commercial value proven? | **No; correctly external or unproven** |

## Audit inventory

The matrix contains **158 requirements**.

### Verdict counts

- `CONTRADICTS_BUNDLE`: 4
- `DEFECT`: 46
- `DEFERRED_BY_SCOPE`: 6
- `EXTERNAL_WAIT`: 10
- `NOT_PROVEN`: 15
- `PARTIAL`: 30
- `PROVEN`: 47

### Severity counts

- `CRITICAL`: 45
- `HIGH`: 40
- `MEDIUM`: 11
- `INFO`: 62


The supplied local bundle manifest verification was **PASS** for 30 manifest entries. This validates the review bundle itself; it does not validate the live repository implementation.

## Critical blockers

### 1. The repository is a fork of V3, not a full match

The original V3 authority explicitly requires qualified-human approval and pull-request release. The live repository instead adds:

- `factory/policy/ZERO_HUMAN_OPERATION_OVERRIDE.json`;
- `config/owner_directives.yaml`;
- disabled `config/human_approval.yaml`;
- source-integrity rules that require the override;
- tests that reject the words/states associated with human approval and require direct-main publication.

This may be the owner’s intended policy, but it must be represented honestly as a new source generation, for example:

```text
docs/source-of-truth/v3.1-zh-2026-08-12/
```

Do not leave the original V3 files active and rely on shadow authority outside the manifest.

### 2. The machine-policy replacement is not independent authority

The current `MachinePolicyGateReceipt` is not an adequate replacement for the original human authority. It is essentially a candidate/artifact/directive digest receipt produced and checked by repository-visible code. The V3 controller does not invoke the evaluator before release.

A safe machine-only authority must be:

- outside the agent-visible repository;
- not writable by builder/reviewer/controller identities;
- backed by a root-owned or hardware/remote signing key;
- scope-bound to work item, risk tier, candidate SHA, policy version, allowed claims, and expiry;
- bound to independent oracle identities and raw evidence hashes;
- revocable;
- mandatory before merge/publication;
- independently tested with hidden mutations.

Without that, different AI sessions are still approving assumptions created within the same machine-controlled trust boundary.

### 3. Direct-main publication is unnecessary and unsafe for zero-human operation

Zero human involvement does not require direct pushes to `main`. The safer fully automatic path is:

```text
candidate branch
→ automated PR
→ required server-side checks
→ machine-policy receipt
→ merge queue / auto-merge
→ exact-SHA post-merge verification
```

The current repository has branch protection disabled. A candidate can become `main` before checks finish; a later revert does not undo the period during which the bad SHA was the branch head.

### 4. The live controller is not proven

Migration receipts prove simulations and deterministic tests, not a complete live cycle. The execution state says the controller is stopped, STOP/PAUSE exist, and the Windows task is disabled. This is correct while defects remain, but it means the zero-intervention claim is not yet demonstrated.

Required live proofs include:

- real Claude mechanical canary;
- kill and resume;
- quota pause and automatic resume;
- authentication expiry and recovery;
- repeated finding and finite stop;
- failed CI contained before merge;
- external-wait lane isolation;
- automatic milestone advancement;
- crash-idempotent release transaction.

### 5. The V3 controller cannot execute several current roadmap tasks

Concrete code defects include:

- a hard-coded source path to a file absent from the active V3 directory;
- market/competitor lane write scopes that exclude their intended outputs;
- network denied for every task and backend refusal of allowlisted research;
- mutation tools granted only to the literal `builder` role;
- `outputs=[]` for every generated packet;
- generic `{"type": "object"}` output schema;
- current-fact freshness receipts never supplied;
- context selection omitting required market/current/native groups.

This means the static roadmap can say a task is ready while the live execution contract makes it impossible.

### 6. Retry, repair, re-specification, quota, and resume are not real V3 runtime behavior

Finite counters exist, but existence is not execution. The controller currently lacks the full bounded sequence:

```text
attempt
→ typed failure
→ candidate-preserving repair
→ independent recheck
→ bounded re-specification
→ terminal disposition
```

ClaudeBackend also advertises resume capability while its resume path refuses. Broad exceptions can turn quota/auth conditions into ordinary technical blocks.

### 7. Queue leases can expire during valid work

The queue lease is shorter than a possible stage run and is not renewed during execution. A second controller or restart can classify active work as expired and requeue/block it. Add an ownership token and durable renewal heartbeat.

### 8. Milestone and completion progression are disconnected

Milestone evaluators and completion proposal types exist, but the V3 controller does not automatically:

- evaluate milestone gates;
- advance the active milestone;
- accept/reject a bounded completion proposal;
- update the authoritative roadmap through machine authority;
- schedule the next milestone.

A loop that cannot advance milestones is not a complete autonomous product factory.

### 9. Value and native-substitute gates are disconnected

`apply_v3_value_decision` exists but is not integrated. No complete `NativeSubstituteBenchmark` execution path was found. Therefore the controller can technically pass work without proving that it adds a different operational decision over the complete native substitute.

### 10. Status and runtime paths are inconsistent

The controller, CLI, supervisor, and runtime-status code do not all resolve the same V3 queue/runtime root. External runtime-root support also has path-relativization defects. This can create a healthy-looking dashboard while the active queue or decision artifacts live elsewhere.

## Proven strengths that should remain

The audit found real, useful implementation—not just defects:

- historical source bundle preservation;
- separate V3 manifest and source-integrity checking;
- normative/current-fact context classes;
- typed V3 lanes, maturity, value, and disposition states;
- finite configuration limits;
- external evidence verifier with root ownership, immutability, and Ed25519 checks;
- checkpoint quarantine rather than silent loss;
- backend-neutral protocol surface;
- separate product packages outside `tcfactory`;
- deterministic product identity and evidence models;
- Flight Recorder/native evidence import fixtures;
- explicit UNKNOWN/native-sufficient/uneconomic outcomes;
- install-to-preflight CLI journey;
- split exact-SHA factory/product/source/security/packaging CI;
- accurate nonclaims around GPU, full qualification, payment, and customer use.

These are enough to justify hardening the migration rather than discarding it.

## Required remediation order

### P0 — Keep the controller stopped

Do not remove STOP/PAUSE or re-enable the Windows task until all P0 criteria pass.

1. Create a current-head safety tag/ref.
2. Create `codex/traincapsule-v3-zh-hardening`.
3. Create complete `v3.1-zh` source authority and manifest.
4. Remove shadow-policy ambiguity.
5. Replace direct-main with automated PR + merge queue/auto-merge.
6. Enable server-side required checks/ruleset.
7. Install an external signed machine-policy verifier.
8. Make machine receipt mandatory in controller release flow.
9. Fix packet source resolution, lane paths, role mutability, network allowlists, context, outputs, and strict report schema.
10. Implement real typed retry/repair/re-spec/quota/auth/resume logic.
11. Renew queue leases.
12. Unify runtime paths/status.
13. Integrate value/native gates.
14. Integrate milestone/completion advancement.

### P1 — Prove the factory in a disposable repository

Run deterministic canaries for:

- mechanical pass;
- standard pass;
- product defect;
- factory defect;
- external wait;
- quota wait;
- auth expiry;
- timeout;
- malformed report;
- process kill;
- stale lease;
- duplicate controller;
- failing CI;
- signed receipt missing/invalid/expired/revoked;
- exact-SHA mismatch;
- milestone advancement;
- bounded roadmap proposal.

### P2 — Real-backend observation mode

Run real Claude against harmless mechanical work without publication. Then enable automated PR publication but not auto-merge. After clean evidence, enable auto-merge only for mechanical work. Standard/integration/trust work may auto-merge only after the external machine-policy verifier and hidden suites have demonstrated reliable rejection.

### P3 — Resume M1 lanes

- Product lane: continue bounded preflight/first-pack work.
- Competitor lane: enable allowlisted current-source research and native differential.
- Trust lane: run hidden/controlled/GPU work as evidence permits.
- Market lane: prepare automation and ingest external receipts; do not fabricate conversations or payment.

## Definition of done for the zero-founder loop

Do not describe the loop as fully autonomous until all of these are true:

1. The active authority is one coherent signed/hashed V3.1-ZH generation.
2. Original V3 remains immutable history.
3. Branch/ruleset checks prevent unverified main updates.
4. Machine-policy verifier is outside candidate/controller write authority.
5. Every release receipt is signed, scoped, expiring, revocable, and exact-SHA bound.
6. All roadmap task classes have executable path/network/context/output contracts.
7. Backend capability claims are truthful.
8. Quota/auth/timeout/crash paths pause and resume correctly.
9. Queue leases renew and duplicate controllers cannot claim active work.
10. Repair/re-specification/no-progress paths are finite and tested.
11. Value/native differential runs before maturity promotion.
12. Completion proposals cannot self-approve or expand indefinitely.
13. Milestones advance automatically and atomically.
14. External waits do not stall unrelated lanes.
15. A real Claude-backed observation canary passes.
16. A real automated PR/merge canary passes.
17. A deliberately bad candidate is rejected before main.
18. A controller kill at every release boundary is idempotently recovered.
19. Status reads the authoritative runtime state.
20. No controlled/synthetic evidence is presented as customer, GPU, payment, retention, or production evidence.

## Matrix

The full requirement-by-requirement matrix is provided separately as:

`TRAINCAPSULE_V3_ZERO_HUMAN_CONFORMANCE_MATRIX_2026-08-12.csv`

Critical unresolved IDs:

```text
A006 A007 A008 B001 B005 B006 B008 C013 D005 D009 D010 E003 E004 E005 E007 F003 F004 F006 F007 F008 F010 F011 F012 F014 F015 F016 F018 G005 G006 G007 G009 G010 G012 G013 G014 G018 H001 H002 H003 H004 H005 H008 H015 J011
```

## Audit limitations

This audit used the supplied bundle, connected GitHub repository content, commit history, branch/rules metadata, workflow results, and repository evidence files. It could not directly inspect the user’s local-only OAuth token, off-repository private-gate implementation, local WSL process table, Windows Task Scheduler state, ignored runtime artifacts, or customer/private evidence. Repository claims about those surfaces remain unproven unless supported by independent receipts.
