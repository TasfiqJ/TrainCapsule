# 06 — Commercial Model, Go-to-Market, and Validation Plan V3

## 06.1 Commercial objective

TrainCapsule is not successful when the repository is large, the controlled demo is impressive, or every planned component exists.

The business objective is:

> Repeatedly sell a bounded release, migration, or recovery decision that the customer's complete native workflow cannot produce as cheaply, credibly, or privately.

The first business may be expert-led. The repeatable product is the local qualification contract and its re-execution across changes.

## 06.2 Initial positioning

### Category

**Failure-derived change qualification for private distributed-training workloads.**

### Primary message

> Turn your worst distributed-training failure into a customer-local release gate for your next PyTorch, CUDA, NCCL, driver, checkpoint, GPU, topology, scheduler, or cloud change.

### Supporting message

TrainCapsule starts with the tools the customer already trusts. It imports native evidence, identifies what remains unresolved, constructs a bounded lower-cost experiment where possible, evaluates named recovery-state properties, and compares the current and proposed environments under an expiring contract.

### Do not lead with

- AI root-cause analysis;
- GPU observability;
- deterministic replay;
- black-box recording;
- NCCL debugging;
- automatic recovery;
- vendor-neutral dashboard;
- generic reliability platform.

Those positions are crowded, easily bundled, or too broad.

## 06.3 Initial buyer and user

### Economic buyer

A director, head, or lead responsible for:

- ML platform;
- training infrastructure;
- research infrastructure;
- GPU platform/reliability;
- model systems;
- infrastructure release or migration;
- managed training service operations.

### Primary user

A senior infrastructure, distributed-systems, ML systems, performance, or reliability engineer who owns the incident evidence and candidate change.

### Supporting users

- training framework engineer;
- checkpoint/recovery owner;
- SRE;
- provider support engineer;
- security reviewer;
- research engineer whose workload is blocked.

## 06.4 Ideal customer profile

The best first customer is a middle-sized AI organization that:

- operates recurring multi-node PyTorch/NCCL workloads;
- has a small infrastructure team supporting multiple model/research teams;
- has at least one expensive active or historical incident;
- has a real stack, hardware, topology, checkpoint, scheduler, or cloud change planned within 90 days;
- controls its images, launch process, evidence, and experimental capacity;
- already uses native diagnostics;
- cannot freely send code, data, checkpoints, or full topology to a provider;
- has a named decision owner;
- can fund a bounded technical pilot;
- has a plausible second qualification event.

### Strong entry situations

- delayed PyTorch/CUDA/NCCL upgrade because of a prior failure;
- GPU or cloud migration with unresolved workload-specific risk;
- resumed job whose application-specific state is not fully trusted;
- provider/workload disagreement that native tools do not close;
- repeated expensive reproduction of a private failure;
- release blocked because full-scale reproduction is too expensive;
- cross-provider decision where provider-owned tools cannot see the complete workload.

### Poor first customers

- frontier labs with mature internal diagnostic systems;
- hyperscalers;
- tiny fine-tuning teams with low incident economics;
- teams without access to evidence or execution;
- teams seeking a generic monitoring dashboard;
- customers demanding guaranteed root cause or hardware certification;
- customers whose accepted solution is simply restart/retry;
- customers with no actual upcoming decision.

## 06.5 Account qualification score

Score each account from 0–2 on each dimension.

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Incident cost | minor | material inconvenience | major GPU/delay/engineering cost |
| Upcoming change | none | possible | named within 90 days |
| Evidence access | poor | partial | strong |
| Experiment authority | none | constrained | customer-local authority |
| Native gap | native sufficient | uncertain | clear unresolved decision |
| Privacy need | low | moderate | private/local is essential |
| Repeat trigger | one-off | possible | recurring releases/migrations |
| Budget owner | absent | indirect | named and engaged |
| Second-use path | none | hypothetical | dated event/workload |
| Delivery fit | bespoke | mixed | within supported envelope |

Minimum pilot candidate:

- no zero in evidence access, experiment authority, or budget owner;
- score at least 14/20;
- one named incident;
- one named candidate change;
- one named decision;
- willingness to run a paid preflight or pilot.

## 06.6 Offer ladder

### Offer 1 — Paid Qualification Preflight

Purpose: decide whether a case is eligible and economically worth pursuing.

Deliverables:

- incident and decision intake;
- native-workflow baseline;
- evidence completeness and identity report;
- supported-pack fit;
- initial experiment and cost hypothesis;
- security/deployment plan;
- go/no-go recommendation;
- fixed pilot scope if eligible.

Internal pricing hypothesis:

```text
CAD/USD equivalent of $15,000–$25,000
```

This is unvalidated and must not be presented as a market fact.

Duration is not promised as a fixed universal number. Scope is bounded by evidence volume and access.

### Offer 2 — Incident-to-Change Qualification Pilot

Required inputs:

```text
one active or reconstructable incident
+ one planned change within 90 days
+ one named release or migration decision
+ one baseline environment
+ one candidate environment
+ customer-local experiment authority
```

Deliverables:

1. native baseline;
2. identity/evidence lock;
3. evidence-gap report;
4. pack-specific experiment;
5. reduction and faithfulness record;
6. baseline/candidate execution;
7. named Recovery Assurance properties;
8. bounded qualification decision;
9. expiring local incident contract;
10. second execution or dated re-execution event included in the engagement;
11. limitations and unsupported claims;
12. customer handoff and independent runbook.

Internal pricing hypothesis:

```text
$40,000–$75,000
```

### Offer 3 — Additional Qualification Event

Run an existing approved contract against another change.

Internal pricing hypothesis:

```text
$20,000–$50,000
```

The price should decline relative to the first incident while gross margin improves.

### Offer 4 — Protected Workload Agreement

For customers with repeated changes and several critical contracts.

Potential components:

- maintained local contract registry;
- scheduled requalification;
- pack/backend updates;
- private references;
- support and incident intake;
- annual security and trust review;
- bounded new contract allowance.

Internal annual hypothesis:

```text
$100,000–$200,000
```

Do not offer this until at least one customer has paid for a second action.

### Offer 5 — Provider or Platform Integration

Only after customer evidence shows recurring provider-side value.

Potential components:

- local/federated runner;
- support package integration;
- incident-contract handoff;
- workload qualification during migrations;
- provider-specific evidence adapter.

Internal hypothesis:

```text
$250,000+ project or strategic agreement
```

This is not part of the initial operating plan.

## 06.7 Initial engagement contract

The first serious contract must include the second use, not merely ask whether a second use might occur.

Example structure:

```text
Phase A: qualification preflight
Phase B: incident-derived contract construction
Phase C: baseline/candidate decision
Phase D: one scheduled requalification or second candidate execution
```

This directly tests whether the product creates repeat behavior.

The contract must state:

- customer-owned decision;
- required access;
- supported claims;
- unsupported claims;
- no universal safety/root-cause guarantee;
- customer-local data boundary;
- experiment budget;
- stop conditions;
- human-review responsibility;
- external evidence and case-study permissions;
- correction/revocation process.

## 06.8 Productized expert service

The first version should be delivered as:

> Expert-led incident-to-change qualification, powered by TrainCapsule.

This is acceptable because real incidents require judgment and access. It becomes a product only when each engagement improves reusable software, packs, runbooks, or evidence policy.

Track for each case:

- total delivery hours;
- founder hours;
- specialist hours;
- setup time;
- experiment cost;
- repeated versus bespoke steps;
- code changed;
- trust-core changes;
- customer-retained work;
- second-use setup time;
- gross margin;
- decision value.

### Productization test

By the third same-family case:

- no trust-core rewrite;
- no new identity semantics;
- no case-specific result-state semantics;
- pack extension is bounded;
- another qualified operator can run the workflow;
- setup and interpretation effort decline;
- the result remains independently verifiable.

Failure means the wedge is consulting-heavy and must be narrowed, redesigned, or stopped.

## 06.9 Open-source and free entry surface

Open or free tooling may:

- import PyTorch Flight Recorder evidence;
- validate environment/workload identity;
- report evidence gaps;
- display native findings;
- classify eligibility;
- verify a signed local contract;
- reproduce public controlled cases.

The paid product retains:

- private experiment design;
- legal reduction and faithfulness process;
- customer-local baseline/candidate execution;
- private references;
- Recovery Assurance;
- maintained qualification;
- support/export integration;
- expert interpretation and approval coordination.

The open component should create trust and qualified leads, not give away a one-time report while leaving no recurring product.

## 06.10 Complete-substitute benchmark

For every pilot and major feature, compare against:

```text
PyTorch/native framework tools
+ cloud/platform tooling
+ hardware/vendor support
+ customer scripts
+ approved coding/operations agents
+ reasonable senior-engineer effort
```

Required benchmark fields:

- native outcome;
- native operator time;
- native execution cost;
- unresolved decision;
- TrainCapsule incremental outcome;
- TrainCapsule retained effort;
- changed decision;
- reusable contract value;
- customer willingness to pay;
- limitations.

### Commercially weak outcomes

```text
NATIVE_WORKFLOW_SUFFICIENT
NO_INCREMENTAL_DECISION_VALUE
TECHNICALLY_VALID_BUT_NOT_ECONOMIC
```

These are successful learning outcomes, not product successes.

### Commercially promising outcome

```text
INCREMENTAL_DECISION_VALUE_DEMONSTRATED
```

It must be supported by a real operational decision and attributable customer confirmation.

## 06.11 Discovery program

Market discovery runs from day one in parallel with engineering.

### Initial evidence targets

```text
30 named accounts
15 detailed operator conversations
5 real incident timelines
3 organizations with a planned change
2 credible pilot candidates
1 genuine trace or historical evidence archive
```

These are activity/evidence targets, not proof of demand.

### Conversation requirements

A qualifying conversation must discuss a specific incident or change, including:

- workload and scale class;
- what happened;
- native tools used;
- evidence available;
- time and GPU cost;
- operator effort;
- decision delayed or made;
- residual uncertainty;
- privacy/access constraints;
- planned changes;
- budget ownership;
- accepted alternatives;
- whether a second use exists.

Generic “interesting idea” feedback does not count.

### Interview questions

1. Describe the last distributed-training incident that materially delayed work.
2. What was the first operational decision you needed to make?
3. Which tools and people were involved?
4. What remained unknown?
5. Did you reproduce it? At what cost?
6. Did the result become a regression or release check?
7. What stack or infrastructure changes are planned?
8. What prevents you from using the historical incident as a release gate?
9. What data cannot leave your environment?
10. Who owns the decision and budget?
11. What would make you pay for a preflight?
12. Under what condition would you pay for a second execution?
13. What would make the complete native workflow sufficient?

Do not pitch for most of the conversation. Collect concrete facts.

## 06.12 Reachable-account map

The account map should prioritize organizations reachable through:

- founder network;
- university/research contacts;
- open-source maintainers;
- Toronto/Canadian AI ecosystem;
- cloud/GPU infrastructure communities;
- PyTorch/NCCL issue participants;
- training-platform vendors;
- ML infrastructure events;
- technical advisers.

For each account record:

```yaml
account:
segment:
relationshipPath:
relevantWorkload:
knownIncident:
plannedChange:
decisionOwner:
technicalChampion:
budgetOwner:
nativeStack:
privacyConstraint:
qualificationScore:
nextEvidenceAction:
status:
```

Automated scraping and generic cold-email volume are not the primary strategy. High-context technical outreach is.

## 06.13 Design partner structure

A design partner must provide more than enthusiasm.

Minimum:

- real incident or controlled customer case;
- real upcoming change;
- execution access;
- named operator;
- scheduled technical sessions;
- permission to retain anonymized process learnings;
- willingness to evaluate price;
- second-use date;
- honest native baseline.

Preferred:

- paid engagement;
- public or sanitized technical case;
- adviser access;
- referral to another qualified account.

A free design partner may be useful for access, but it does not establish willingness to pay.

## 06.14 Sales sequence

```text
technical introduction
→ incident/change qualification
→ paid preflight
→ security/access plan
→ fixed-scope pilot
→ bounded release decision
→ second execution
→ protected workload agreement
```

### Initial outreach message

Lead with the operational decision, not architecture.

Example:

> We are building a customer-local way to turn a costly distributed-training failure into a release test for an upcoming PyTorch, CUDA, NCCL, GPU, checkpoint, topology, or cloud change. It starts from the native evidence you already use and is intended for cases where reproducing the full workload is too expensive or private evidence cannot leave your environment. I am looking for infrastructure teams with one real historical incident and one upcoming change to compare the workflow against what they already do.

Avoid acquisition, AI-factory, and “revolutionary” language.

## 06.15 Proof hierarchy

```text
plan
< controlled fixture
< local multi-process case
< real multi-GPU controlled case
< real incident archive
< independent operator
< paid pilot
< changed customer decision
< paid second action
< annual commitment
< multi-customer repeat
```

Only evidence at or above the relevant level may support a claim.

## 06.16 Validation gates

### Gate C0 — Problem access

Required:

- 15 detailed conversations;
- 5 incident timelines;
- one real evidence archive;
- at least three named upcoming changes.

Decision:

- continue current wedge;
- narrow;
- replace;
- stop.

### Gate C1 — Native gap

Required:

- two cases where the complete native workflow leaves a material decision unresolved;
- one controlled head-to-head demonstration;
- exact statement of incremental value.

### Gate C2 — Paid pilot

Required:

- signed paid preflight or pilot;
- execution and evidence access;
- named decision and deadline;
- included second use.

### Gate C3 — External value

Required:

- TrainCapsule changes or materially strengthens a real decision;
- customer confirms value exceeds price and retained effort;
- limitations accepted;
- native comparison recorded.

### Gate C4 — Repeat

Required:

- same customer pays for a second action;
- no trust-core rewrite;
- setup effort declines.

### Gate C5 — Productization

Required:

- third same-family case;
- independent operator;
- repeatable deployment and runbook;
- improving delivery margin;
- commercially supported pack approval.

### Gate C6 — Annual product

Required:

- at least two customers with repeated qualification;
- one annual or multi-event commitment;
- support/security process;
- founder dependence declining.

## 06.17 Stop and pivot rules

Stop or replace the wedge when any of the following is repeatedly observed:

- native tools produce the same release decision;
- customers accept restart and residual uncertainty;
- nobody pays for the second execution;
- every case requires a new trust model;
- reduced experiment costs nearly as much as the original;
- evidence or execution access is consistently unavailable;
- deployment/security burden exceeds decision value;
- the decision owner lacks budget;
- the historical incident does not matter to future changes;
- the pack produces reports but not decisions;
- the product is useful only as bespoke founder consulting.

The factory is not allowed to respond to these signals by automatically adding features.

## 06.18 Pricing experiments

Maintain a ledger for every price discussion.

Fields:

```yaml
offer:
account:
incidentClass:
decision:
quotedPrice:
scope:
response:
objection:
alternativeBudget:
buyer:
date:
nextStep:
evidenceStrength:
```

Test:

- paid versus free preflight;
- fixed fee versus milestone fee;
- pilot including second execution;
- annual contract after repeat;
- price tied to protected workload rather than seats;
- customer-local deployment fee;
- support response levels only when demanded.

Do not discount in exchange for vague future access. Exchange discounts for concrete evidence, public case rights, or second-use commitment.

## 06.19 Internal revenue hypothesis

A falsifiable $1 million annual model:

```text
6 annual customers × $125,000 = $750,000
5 paid pilots × $50,000       = $250,000
                                      ----
                                $1,000,000
```

This is an internal planning hypothesis, not a forecast.

Example first-year funnel hypothesis:

```text
60 named accounts
→ 25 qualified conversations
→ 10 real evidence reviews
→ 5 paid assessments/pilots
→ 3 material outcomes
→ 2 second paid actions
→ 1–2 annual agreements
```

Update with actual conversion data.

## 06.20 Unit economics

Track per engagement:

```text
revenue
- external GPU/compute cost
- specialist review
- security/deployment work
- support
- travel/procurement
- founder delivery allocation
= contribution margin
```

Also track:

- hours to preflight;
- hours to first valid experiment;
- hours to decision;
- customer-retained effort;
- second-execution effort;
- pack maintenance;
- support incidents;
- refund/credit risk.

Do not treat AI subscription cost as the only cost. Customer access, security, trust, GPU execution, expert review, and delivery are the expensive constraints.

## 06.21 Commercial data model

Create repository templates, but store private customer records outside the public/product repository.

Required ledgers:

```text
REACHABLE_ACCOUNT_MAP
DISCOVERY_INTERVIEW_LEDGER
INCIDENT_EVIDENCE_LEDGER
PILOT_PIPELINE
PRICING_EXPERIMENT_LEDGER
NATIVE_SUBSTITUTE_BENCHMARK_LEDGER
CUSTOMER_VALUE_RECEIPT_LEDGER
REPEAT_USE_LEDGER
WEDGE_DECISION_LEDGER
```

The AI factory may summarize sanitized entries. It may not fabricate or independently sign them.

## 06.22 Case-study strategy

The first public case should be a transparent head-to-head.

Structure:

1. original incident and decision;
2. native tools and what they found;
3. what remained unresolved;
4. evidence gaps;
5. rejected hypotheses;
6. legal reductions attempted;
7. reduction counterexamples;
8. baseline result;
9. candidate result;
10. Recovery Assurance;
11. bounded decision;
12. cost/resource comparison;
13. limitations;
14. what did not work.

A controlled case must be labeled controlled. A customer case requires permission and privacy review.

## 06.23 Competitive strategy

### Against native framework tools

Integrate and credit them. Win only on the remaining decision workflow.

### Against cloud/platform bundles

Target private, cross-provider, workload-specific, or migration decisions where provider tooling lacks complete authority or neutrality.

### Against diagnosis/remediation vendors

Do not compete on generic AI diagnosis. Emphasize incident-derived, expiring qualification against future change.

### Against deterministic replay systems

Do not promise universal replay. Emphasize lower-cost faithful experiment search, applicability, recovery properties, and release decision.

### Against internal scripts plus agents

Win through:

- signed identities;
- pack-specific legal reductions;
- explicit faithfulness;
- reusable local contracts;
- property-level recovery assurance;
- supportable and independently verifiable operation;
- maintained drift/expiry;
- trust and correction history.

If internal scripts produce the same decision with acceptable cost, classify the account as native/internal sufficient.

## 06.24 Trust as a sales asset

TrainCapsule should earn trust through:

- visible native findings;
- explicit unsupported claims;
- `UNKNOWN`;
- customer-local operation;
- independent verifier;
- human pack approval;
- correction/revocation;
- negative cases;
- no forced data export;
- no AI-only release authority.

Do not sell “AI magic.” Sell a disciplined decision process.

## 06.25 Procurement and security package

Before the first pilot, prepare:

- architecture and data-flow diagram;
- threat model;
- local deployment guide;
- data classification;
- network behavior;
- SBOM;
- vulnerability handling;
- incident response;
- retention/deletion policy;
- subprocess/GPU access model;
- AI usage disclosure;
- human review policy;
- support export policy;
- contract and result schemas;
- limitations.

Do not build broad enterprise RBAC before a customer requests it. Provide a clear local boundary first.

## 06.26 Team plan

Before external trust-critical use, secure:

- a distributed-training adviser/reviewer;
- a security/private-deployment reviewer;
- access to real GPU environments;
- an operator who can independently execute the workflow.

Potential later hires/cofounders:

- distributed training/PyTorch/NCCL;
- field or forward-deployed engineer;
- security/platform engineer;
- product/sales operator for AI infrastructure.

AI-generated implementation does not replace domain credibility or customer trust.

## 06.27 Founder operating cadence

Weekly:

- technical build progress;
- qualified conversations;
- incident evidence acquired;
- native/competitor changes;
- pilot pipeline;
- wedge stop signals;
- founder learning/defense.

Monthly:

- complete-substitute benchmark update;
- pack maturity review;
- pricing evidence;
- productization metrics;
- `KEEP`, `INTEGRATE`, `UPSTREAM`, `NARROW`, `REPLACE`, `PAUSE`, or `STOP` decision;
- independent adviser review for material trust changes.

The meeting should not be dominated by task count.

## 06.28 Company dashboard

Primary metrics:

- qualified incidents with upcoming change;
- paid preflights/pilots;
- decisions completed;
- complete-substitute wins;
- second paid actions;
- time to first valid experiment;
- original-to-reduced cost ratio;
- customer-retained effort;
- independent operator success;
- same-family reuse;
- contribution margin;
- pack commercial maturity;
- active/expired contracts.

Secondary engineering metrics:

- product tests;
- security findings;
- escaped defects;
- CI reliability;
- factory retries;
- token/quota use.

Task count and repository size are not company KPIs.

## 06.29 Success definition

The company has a credible initial business when:

- one supported pack repeatedly produces decisions beyond the complete substitute;
- customers permit local execution;
- at least one customer pays twice;
- the workflow becomes less bespoke;
- another operator can run it;
- security and trust reviews pass;
- annual protection of important workloads becomes a rational purchase.

Until then, TrainCapsule is a strong technical and commercial experiment, not a proven business.
