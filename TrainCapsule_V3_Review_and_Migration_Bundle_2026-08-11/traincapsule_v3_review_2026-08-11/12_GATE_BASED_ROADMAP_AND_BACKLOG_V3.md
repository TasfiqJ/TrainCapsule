# 12 — Gate-Based Roadmap and Backlog V3

## 12.1 Roadmap principle

The roadmap is not a promise to build every designed capability. It is a sequence of evidence gates.

Four lanes run in parallel:

```text
PRODUCT      — build the bounded qualification workflow
MARKET       — acquire real incident, buyer, price, and repeat evidence
COMPETITOR   — establish the complete native/bundled/agent baseline
TRUST        — create independent oracles, security evidence, and human authority
```

`FACTORY` is a temporary migration/maintenance lane, not a fifth product strategy.

The next milestone may begin only when its entry criteria are satisfied. Independent work in other lanes may continue when a particular external item is waiting.

## 12.2 Milestone map

```text
M0  Factory and authority migration
 │
 ├─────────────┬─────────────┬─────────────┐
 ▼             ▼             ▼             ▼
M1-PRODUCT   M1-MARKET    M1-COMP       M1-TRUST
 Native       problem      native         trust
 preflight    access       baseline       foundations
 └─────────────┴─────────────┴─────────────┘
                         │
                         ▼
              M2 Controlled qualification
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
        M3 External preflight   continued controlled proof
               │
               ▼
           M4 Paid pilot
               │
               ▼
           M5 Paid repeat
               │
               ▼
   M6 Commercially supported pack
```

## 12.3 M0 — Factory and source-of-truth migration

### Exit criteria

- V3 source authority installed and integrity-checked;
- old bundle archived, not silently edited;
- lane/work-item/milestone schemas active;
- finite retry and restart budgets enforced;
- human and external evidence states implemented;
- completion expansion is proposal-only;
- release uses pull requests;
- factory and product CI separated;
- current queue safely migrated;
- one mechanical and one standard simulated work item complete;
- rollback tested;
- human approval of source migration recorded.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-MIG-001` | FACTORY | Pause autopilot and snapshot repository/runtime state | — | baseline SHA, clean status, queue/checkpoint export |
| `V3-MIG-002` | FACTORY | Create immutable migration branch and rollback tag/instructions | 001 | branch/tag refs, rollback drill |
| `V3-MIG-003` | TRUST | Install V3 documents without mutating old bundle | 001 | source tree, authority diff |
| `V3-MIG-004` | TRUST | Replace source-precedence and context-index policy | 003 | integrity tests, normative/current-fact separation |
| `V3-MIG-005` | FACTORY | Add V3 work-item, milestone, maturity, disposition models | 003 | schemas, model tests |
| `V3-MIG-006` | FACTORY | Add lane-aware scheduler and deterministic score | 005 | scheduler simulation and unit tests |
| `V3-MIG-007` | FACTORY | Enforce finite planning, repair, redesign, expansion, and restart budgets | 005 | retry tests, no-zero-unlimited test |
| `V3-MIG-008` | TRUST | Add signed human-approval model and trusted-root verification | 005 | positive/negative/expiry/SHA tests |
| `V3-MIG-009` | MARKET | Generalize signed external-evidence receipts | 005 | invalid/synthetic/issuer tests |
| `V3-MIG-010` | FACTORY | Convert completion audit to milestone proposal-only behavior | 005,007 | proposal artifact; no ledger mutation |
| `V3-MIG-011` | FACTORY | Add backend-neutral executor interface and Claude adapter | 005 | protocol tests; current Claude flow preserved |
| `V3-MIG-012` | FACTORY | Change release path from direct main to draft PR | 005 | PR dry run, exact-SHA checks |
| `V3-MIG-013` | FACTORY | Split factory, product, security, and source-integrity CI | 012 | workflows and local equivalents |
| `V3-MIG-014` | FACTORY | Make Windows/WSL controls configurable; add restart budget | 007 | non-hardcoded config tests |
| `V3-MIG-015` | FACTORY | Migrate legacy ledger/queue/checkpoints without resuming obsolete work | 005,006,007 | migration report and hashes |
| `V3-MIG-016` | TRUST | Human review of authority, release, and rollback | 003–015 | signed source-migration approval |
| `V3-MIG-017` | FACTORY | Run controlled migration rehearsal and rollback | 006–015 | full transcript and restored SHA |
| `V3-MIG-018` | FACTORY | Enable V3 controller in observation mode | 016,017 | scheduler decisions with no mutation |
| `V3-MIG-019` | FACTORY | Execute one mechanical and one standard V3 task | 018 | candidate manifests, PRs, CI |
| `V3-MIG-020` | FACTORY | Close M0 and archive legacy active queue | 019 | milestone completion record |

### M0 stop conditions

- migration cannot preserve current evidence/history;
- approval root can be written by AI roles;
- release can still bypass PR/human policy;
- rollback cannot restore baseline;
- V3 scheduler still serializes all lanes behind one item.

## 12.4 M1 — Native preflight and problem access

M1 deliberately combines product, market, competitor, and trust evidence. Engineering may progress while market items are waiting, but M2 commercial claims remain blocked.

### M1 product exit criteria

- product packages exist separately from `tcfactory`;
- product schemas exist;
- Flight Recorder importer works on controlled and real-format fixtures;
- identity/evidence lock works;
- native baseline and evidence-completeness report work;
- eligibility engine can return native sufficient, uneconomic, unsupported, policy blocked, and unknown;
- local CLI completes install-to-preflight journey.

### M1 market exit criteria

- 30 named accounts;
- 15 detailed conversations;
- 5 incident timelines;
- 3 upcoming changes;
- 2 credible pilot candidates;
- 1 real trace/archive under lawful access.

These are targets. Failure triggers a wedge decision, not fabricated completion.

### M1 competitor exit criteria

- current capability matrix for PyTorch, NVIDIA, AWS, CoreWeave, Chamber, Teyon, Harbor, Caladrius, TrainCheck, TrainVerify, TTrace, and relevant internal-scale research;
- reproducible native baseline for initial controlled case;
- exact remaining decision gap.

### M1 trust exit criteria

- product threat model;
- canonical identity oracle;
- parser adversarial tests;
- data/AI boundary;
- initial human-reviewer/adviser plan.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PROD-001` | PRODUCT | Create product monorepo/package skeleton | M0 | clean install, package import |
| `V3-PROD-002` | PRODUCT | Define product result, identity, evidence, and case schemas | 001 | schema round-trip/compatibility |
| `V3-TRUST-001` | TRUST | Build independent canonical serialization/identity oracle | PROD-002 | independent implementation, negative cases |
| `V3-PROD-003` | PRODUCT | Implement content-addressed local evidence manifest | PROD-002 | tamper/mixing tests |
| `V3-PROD-004` | PRODUCT | Implement workload identity | PROD-002,TRUST-001 | drift and weak-identity tests |
| `V3-PROD-005` | PRODUCT | Implement environment identity | PROD-002,TRUST-001 | material/immaterial drift tests |
| `V3-PROD-006` | PRODUCT | Implement PyTorch Flight Recorder importer | PROD-003–005 | official-format fixtures, malformed inputs |
| `V3-COMP-001` | COMPETITOR | Freeze current PyTorch Flight Recorder capability baseline | M0 | official sources, commands, findings |
| `V3-PROD-007` | PRODUCT | Emit native findings without attribution laundering | PROD-006,COMP-001 | source labels and tests |
| `V3-PROD-008` | PRODUCT | Implement evidence-completeness report for initial pack | PROD-006 | full missing/conflicting state matrix |
| `V3-PROD-009` | PRODUCT | Implement eligibility and economic preflight | PROD-007,008 | all terminal outcomes |
| `V3-PROD-010` | PRODUCT | Implement local CLI through `preflight` | PROD-003–009 | install-to-preflight journey |
| `V3-TRUST-002` | TRUST | Threat model importer, CAS, identity, CLI, and local storage | PROD-010 | security review and tests |
| `V3-TRUST-003` | TRUST | Implement deterministic redaction and export policy | PROD-003 | secret and policy tests |
| `V3-COMP-002` | COMPETITOR | Build complete native/bundled/agent capability matrix | COMP-001 | dated source register |
| `V3-COMP-003` | COMPETITOR | Reproduce native baseline on initial controlled case | PROD-006,COMP-001 | commands, artifacts, operator effort |
| `V3-COMP-004` | COMPETITOR | Define the exact unowned decision gap | COMP-002,003 | decision-level differential |
| `V3-MKT-001` | MARKET | Build 30-account reachable map | M0 | attributable account records |
| `V3-MKT-002` | MARKET | Prepare interview guide and evidence policy | M0 | review-ready packet |
| `V3-MKT-003` | MARKET | Record 15 qualified conversations | MKT-001,002 | external receipts/notes |
| `V3-MKT-004` | MARKET | Record 5 incident timelines | MKT-003 | sanitized timelines |
| `V3-MKT-005` | MARKET | Identify 3 real upcoming changes | MKT-003 | named decision/deadline |
| `V3-MKT-006` | MARKET | Qualify 2 pilot candidates | MKT-004,005 | ICP score and next action |
| `V3-MKT-007` | MARKET | Secure lawful access to one real trace/archive | MKT-004 | access/rights receipt |
| `V3-DEC-001` | TRUST | Conduct M1 wedge review | all M1 critical items | `KEEP/NARROW/REPLACE/STOP` decision |

### M1 decision

Continue the initial pack only when:

- at least two concrete incidents fit the pack;
- a future change creates a real decision;
- the native workflow leaves a meaningful gap;
- evidence and local execution are feasible.

Otherwise narrow or replace before M2 broad implementation.

## 12.5 M2 — Controlled end-to-end qualification

### Exit criteria

- one controlled failure goes from native evidence to bounded qualification;
- one candidate fixes or guards the contract;
- one candidate regresses or remains failing;
- at least one legal reduction is verified;
- at least one illegal reduction is rejected;
- Recovery Assurance evaluates named properties;
- contract is locally verifiable, expiring, and requalifiable;
- result viewer is thin and read-only;
- real 2–8 GPU execution occurs;
- independent operator runs the journey;
- qualified human approves only controlled external demonstration, not commercial support.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PROD-011` | PRODUCT | Define initial pack schema and mechanism boundaries | M1 decision | pack spec and negative boundaries |
| `V3-TRUST-004` | TRUST | Build independent observed-boundary oracle | PROD-011 | positive/ambiguous/missing-rank cases |
| `V3-PROD-012` | PRODUCT | Implement rank/process-group lifecycle alignment | PROD-011,TRUST-004 | controlled traces |
| `V3-PROD-013` | PRODUCT | Implement hypothesis ledger and plan schema | PROD-011 | falsifier and status tests |
| `V3-PROD-014` | PRODUCT | Implement registered reduction operators for initial pack | PROD-011 | precondition and rollback tests |
| `V3-TRUST-005` | TRUST | Build reduction-faithfulness oracle | PROD-014 | independent negative controls |
| `V3-PROD-015` | PRODUCT | Implement pack-specific experiment planner | PROD-012–014,TRUST-005 | bounded plans, no universal planner |
| `V3-PROD-016` | PRODUCT | Implement signed faithfulness contract | PROD-014,015 | tamper, drift, expiry tests |
| `V3-PROD-017` | PRODUCT | Implement customer-local runner preflight/materialization | PROD-002,016 | containment/resource tests |
| `V3-TRUST-006` | TRUST | Complete runner threat model and containment tests | PROD-017 | escape/network/path tests |
| `V3-PROD-018` | PRODUCT | Implement execution records and artifact capture | PROD-017 | identity/tamper tests |
| `V3-PROD-019` | PRODUCT | Implement Recovery Property contracts | PROD-002 | per-property oracle schema |
| `V3-TRUST-007` | TRUST | Implement independent recovery aggregation oracle | PROD-019 | fail/unknown/optional tests |
| `V3-PROD-020` | PRODUCT | Implement baseline/candidate comparator | PROD-016,018,019,TRUST-007 | decision matrix tests |
| `V3-TRUST-008` | TRUST | Build independent qualification semantics oracle | PROD-020 | invalid-oracle and unknown tests |
| `V3-PROD-021` | PRODUCT | Implement local incident-contract registry | PROD-020 | create/verify/expire/supersede |
| `V3-PROD-022` | PRODUCT | Implement external verifier | PROD-021,TRUST-001,005,007,008 | independent verification |
| `V3-PROD-023` | PRODUCT | Implement thin local report viewer | PROD-020–022 | report/machine-record consistency |
| `V3-PROD-024` | PRODUCT | Build controlled omitted/reordered/data-branch/rank-exit cases | PROD-011 | labeled controlled corpus |
| `V3-PROD-025` | PRODUCT | Execute CPU/local multi-process journeys | PROD-012–024 | end-to-end evidence |
| `V3-PROD-026` | PRODUCT | Execute real 2–8 GPU controlled journey | PROD-025,TRUST-006 | real GPU artifacts |
| `V3-COMP-005` | COMPETITOR | Run head-to-head native versus TrainCapsule case | PROD-026 | decision differential |
| `V3-PROD-027` | PRODUCT | Add upgrade/rollback and offline bundle | PROD-022,026 | install/rollback evidence |
| `V3-TRUST-009` | TRUST | Independent operator executes controlled journey | PROD-027 | signed operator receipt |
| `V3-TRUST-010` | TRUST | Human review of controlled demonstration | all M2 trust/product | scoped approval |
| `V3-DEC-002` | TRUST | M2 product/native/value disposition | COMP-005,TRUST-010 | continue/narrow/stop |

### M2 stop conditions

- no material decision beyond native workflow;
- legal reduction cannot be established;
- cost reduction is not meaningful;
- independent operator cannot run the workflow;
- runner security cannot be bounded;
- controlled success depends on hidden manual intervention.

## 12.6 M3 — External paid-preflight readiness

### Exit criteria

- real evidence can be imported locally under policy;
- one customer-specific decision is in supported envelope;
- paid preflight packet, contract, security package, and pricing hypothesis are ready;
- adviser/reviewer availability confirmed;
- no customer/payment claim is made yet.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-MKT-008` | MARKET | Finalize paid preflight offer and scope | M2 | offer document |
| `V3-MKT-009` | MARKET | Finalize pricing experiment and commercial terms | M2 | pricing ledger |
| `V3-TRUST-011` | TRUST | Complete customer security/procurement packet | M2 | security documents |
| `V3-TRUST-012` | TRUST | Contract qualified distributed-training adviser | M2 | external receipt |
| `V3-TRUST-013` | TRUST | Contract security reviewer | M2 | external receipt |
| `V3-PROD-028` | PRODUCT | Run real-archive preflight without unsupported execution claims | MKT-007,M2 | local evidence report |
| `V3-COMP-006` | COMPETITOR | Run customer-case native baseline | PROD-028 | exact native result |
| `V3-MKT-010` | MARKET | Secure customer approval for paid preflight proposal | MKT-006,008–009,TRUST-011 | signed/external receipt |
| `V3-DEC-003` | TRUST | Authorize paid preflight | PROD-028,COMP-006,TRUST-012–013,MKT-010 | founder/human decision |

## 12.7 M4 — Paid Incident-to-Change Qualification Pilot

M4 is external. It cannot be completed by repository fixtures.

### Entry criteria

- paid contract or invoice/payment evidence;
- named incident;
- named upcoming change;
- named decision owner and deadline;
- baseline/candidate access;
- local execution authority;
- privacy/security approval;
- second execution included.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PILOT-001` | MARKET | Record paid engagement and exact scope | M3 | signed paid receipt |
| `V3-PILOT-002` | PRODUCT | Import and lock customer-local case | 001 | customer-local manifest |
| `V3-PILOT-003` | COMPETITOR | Complete native workflow baseline | 002 | commands/findings/decision |
| `V3-PILOT-004` | PRODUCT | Produce evidence/eligibility decision | 002,003 | preflight |
| `V3-PILOT-005` | TRUST | Human approve case-specific experiment/reduction plan | 004 | signed approval |
| `V3-PILOT-006` | PRODUCT | Construct and verify faithful experiment | 005 | faithfulness record |
| `V3-PILOT-007` | PRODUCT | Execute baseline and candidate locally | 006 | execution records |
| `V3-PILOT-008` | PRODUCT | Evaluate Recovery Assurance | 007 | property matrix |
| `V3-PILOT-009` | PRODUCT | Issue bounded qualification decision | 007,008 | signed result |
| `V3-PILOT-010` | TRUST | Human approve customer-facing claims | 009 | signed approval |
| `V3-PILOT-011` | MARKET | Obtain customer decision/value feedback | 009,010 | attributable receipt |
| `V3-PILOT-012` | PRODUCT | Install reusable local contract and runbook | 009 | independent verification |
| `V3-PILOT-013` | MARKET | Schedule and contract the included second execution | 001,012 | dated commitment |
| `V3-DEC-004` | TRUST | Pilot disposition | 011–013 | continue/narrow/stop |

### M4 successful outcome

- real decision changed or materially strengthened;
- complete substitute did not produce the same bounded result at acceptable cost;
- customer confirms value exceeds price and retained effort;
- reusable contract installed;
- second action scheduled.

A technically valid but commercially weak result completes the pilot honestly and may stop the wedge.

## 12.8 M5 — Paid repeat

### Exit criteria

- same customer pays for or contractually consumes a second qualification;
- no trust-core rewrite;
- setup and delivery effort decline;
- contract drift/expiry works;
- another qualified operator participates;
- margin trajectory is improving.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-REPEAT-001` | MARKET | Record second paid/contracted action | M4 | signed receipt |
| `V3-REPEAT-002` | PRODUCT | Detect candidate/environment drift | 001 | drift report |
| `V3-REPEAT-003` | PRODUCT | Requalify existing contract | 002 | new decision |
| `V3-REPEAT-004` | TRUST | Independent operator completes workflow | 003 | operator receipt |
| `V3-REPEAT-005` | MARKET | Measure retained effort and value | 003 | customer receipt |
| `V3-REPEAT-006` | MARKET | Measure delivery economics | 003 | internal cost record |
| `V3-DEC-005` | TRUST | Repeat/productization disposition | 004–006 | continue/narrow/stop |

## 12.9 M6 — Commercially supported initial pack

### Exit criteria

- at least one external-value demonstration;
- paid repeat;
- third same-family case or equivalent reusable proof;
- no trust-core rewrite;
- qualified human pack approval;
- security/support/rollback;
- native advantage remains current;
- commercially supportable scope and version policy.

### Work items

| ID | Lane | Outcome | Depends on | Required evidence |
|---|---|---|---|---|
| `V3-PACK-001` | PRODUCT | Consolidate pack from repeated cases | M5 | versioned pack |
| `V3-PACK-002` | PRODUCT | Demonstrate third same-family case without core rewrite | 001 | case evidence |
| `V3-COMP-007` | COMPETITOR | Refresh complete-substitute benchmark | 001 | current sources/run |
| `V3-TRUST-014` | TRUST | Final pack oracle/security review | 001–003 | independent reports |
| `V3-TRUST-015` | TRUST | Qualified human commercial-pack approval | 014 | signed approval |
| `V3-PROD-029` | PRODUCT | Publish support/upgrade/deprecation policy | 015 | operator docs |
| `V3-MKT-011` | MARKET | Offer protected-workload agreement | M5 | customer response |
| `V3-DEC-006` | TRUST | Mark pack commercially supported or refuse | all M6 | maturity decision |

## 12.10 Checkpoint pack roadmap

The checkpoint/resume pack is not on the initial commercial critical path.

Allowed before M5:

- schema design;
- controlled reference implementation;
- comparison against AWS/NVIDIA/native recovery;
- customer-property discovery.

Commercial promotion requires a specific external gap.

Potential work items remain `DEFERRED`:

```text
V3-REF-CKPT-001  reference property schema
V3-REF-CKPT-002  controlled model/optimizer/RNG/sampler/data-cursor cases
V3-REF-CKPT-003  native recovery capability benchmark
V3-REF-CKPT-004  customer-specific property evidence
V3-REF-CKPT-005  commercial-release decision
```

Do not implement universal checkpoint certification.

## 12.11 Deferred platform backlog

Keep as design-only until M5/M6 evidence:

- generalized actor IR;
- broad FSDP/parallelism abstraction;
- arbitrary scale-emulation backend;
- provider federation;
- hosted control plane;
- multi-tenant service;
- dashboard suite;
- automatic repair;
- cross-customer knowledge graph;
- hardware-dependence pack;
- numerical divergence pack;
- fail-slow pack;
- provider marketplace;
- billing/RBAC.

Each requires a promotion record with:

- paid or repeated need;
- complete-substitute gap;
- security burden;
- expected decision value;
- owner;
- stop criteria.

## 12.12 Legacy 124-task ledger disposition

The current ledger is preserved as historical design input, not active company completion.

Migration policy:

- T001/T002 and existing factory work become legacy `FACTORY` history.
- Broad P0–P9 product tasks become `DEFERRED_DESIGN` unless explicitly represented in V3.
- Concepts required by V3 are reintroduced as new work items with bounded acceptance.
- No V3 task depends on all earlier numerical IDs.
- Passing a legacy task does not advance commercial maturity.
- Legacy packets are not automatically resumed.
- Old artifacts remain attributable to their original SHA and policy.

The migration must produce a machine-readable mapping:

```yaml
legacyTaskId:
legacyOutcome:
v3Disposition:
v3WorkItems:
reason:
preservedEvidence:
```

## 12.13 Operating cadence

### Daily automated

- scheduler selects critical path;
- deterministic health/CI;
- current candidate/retry budget;
- external/human wait visibility;
- no autonomous external contact.

### Weekly founder review

- active milestone;
- market evidence;
- native changes;
- candidate pilot;
- stop signals;
- product/factory code ratio;
- next human action.

### Monthly wedge review

For every active pack/backend/surface choose:

```text
KEEP
INTEGRATE_EXISTING_BACKEND
UPSTREAM
NARROW
REPLACE
PAUSE
STOP
```

The decision and evidence are versioned.

## 12.14 Roadmap success criteria

This roadmap succeeds when it reduces uncertainty in this order:

1. Can the customer and decision be identified?
2. Does the complete native workflow leave a meaningful gap?
3. Can one bounded workflow close that gap?
4. Can it run safely in the customer environment?
5. Will someone pay?
6. Does the customer use it again?
7. Does delivery compound into product?
8. Is a supported pack economically defensible?

It fails when it optimizes for finishing architecture before answering those questions.
