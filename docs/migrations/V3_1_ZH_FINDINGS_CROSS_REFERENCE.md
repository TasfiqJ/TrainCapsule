# V3.1-ZH findings cross-reference

This is the no-forgetting ledger requested by the owner. It joins the 158-row V3.1-ZH package matrix with the hostile findings discovered during the preceding zero-human V3 overhaul. A row is not closed by code presence, a prior passing test, or documentation. Closure requires exact-candidate evidence under the V3.1 acceptance contract.

## Classification rules

- `OPEN`: no current-SHA proof or an active contradiction exists.
- `PARTIAL`: some implementation exists but the complete acceptance boundary is unproven.
- `PROVEN-BASELINE`: objectively passed under the prior V3 model only; V3.1 proof is still required when policy changed.
- `PROVEN-V3.1`: exact-candidate implementation, negative control, hosted check, and required receipt are all bound and replayable.
- `EXTERNAL-WAIT`: outside fact or access is genuinely absent; unrelated lanes must continue.
- `DEFERRED`: explicitly outside scope with no false completion claim.

Only `PROVEN-V3.1`, `EXTERNAL-WAIT`, or contract-authorized `DEFERRED` may remain at activation. No `CRITICAL` or `HIGH` requirement may remain `OPEN` or `PARTIAL`.

## Cross-reference of owner/package findings and prior hostile findings

| Concern | Package IDs / areas | Prior hostile evidence | Phase-0 current classification | Required closure proof |
|---|---|---|---|---|
| Source authority and zero-human amendment | A006-A008, B001, B005-B008 | Original bundle required human approval and PR restrictions; a scoped owner override was added during V3 | OPEN: V3.1 package is now the controlling amendment, but active authority and generated policy have not been migrated | New immutable authority layer, residue gate, exact source digests, and no reachable human/direct-main policy |
| Automated PR-only release | A006-A008, B005, G012-G014, G018 | Previous hostile audit found dead PR helpers and unsafe direct-main; V3 then deliberately implemented main-only publication | OPEN: current release configuration contradicts V3.1 and GitHub has no ruleset/protection | Candidate branch to automated PR only; required exact-SHA checks; machine receipt; no direct-main refspec; negative bypass tests |
| Independent verifier trust boundary | B006, G005-G007, G009-G010, G014 | Previous private gate was made root-owned and signed, but it remains part of the factory installation | OPEN: separate verifier identity/service/storage/logging do not exist | Separate OS account/service/key roots, non-agent-writable inputs and outputs, signed/revocable/expiring exact-SHA receipts, outage/tamper tests |
| Milestone progression | D005, D009-D010, H008 | Prior audit proved milestone completion had no runtime caller; V3 added completion and crash-replay progression | PARTIAL: local implementation exists, but package authority and live automatic advancement canary are absent | Exact-state canary advances one milestone once, preserves evidence, rejects missing gates, and survives restart |
| Finite retry, repair, resume, and repeated findings | E003-E005, E007, F003-F004, H003-H004 | Prior audit proved first failure became permanently blocked and resume was dead; V3 added persistent budgets/fingerprints | PARTIAL: unit/crash simulations passed under V3; real backend and process-kill canaries are absent | Real Claude mechanical task, process kill/resume, quota/auth recovery, repeated-fingerprint finite stop, immutable handoff/checkpoint receipts |
| Queue atomicity, controller ownership, and runtime paths | E003-E007 and scheduler/recovery rows | Prior audit found non-atomic claims, split runtime roots, live-lease theft, and duplicate controller risk; V3 repaired these | PROVEN-BASELINE: hostile process tests passed, but V3.1 external-root and duplicate/renewal canaries remain | Two-process and external-root canaries at candidate SHA plus durable lease/lock evidence |
| Legacy V2 mutation and setup escapes | Authority, backend/execution, live-autonomy rows | Prior audit found `start`, setup scripts, GitHub configuration script, and status/recover paths could invoke legacy behavior | PROVEN-BASELINE for known paths after fail-closed repairs; full V3.1 reachable-surface scan pending | Reachability scan plus mutation-negative tests showing no V2 ledger/queue/setup path can alter active state |
| Role-scoped source/current-fact context | A009 and F006/F018-family context rows | Prior audit found dead context code, missing digests/budgets, wrong role names, and absent commercial routing | PARTIAL: bounded manifests and signed market receipts were added; V3.1 stale/missing-source canaries are pending | Per-role manifest replay, exact source sections/digests/budgets, stale-current-facts rejection, missing-source rejection |
| External truth and lane isolation | Market/research and H015-family rows | Prior audit found external work could be auto-passed; V3 moved MKT-003..007 to signed `WAITING_EXTERNAL` | PARTIAL / EXTERNAL-WAIT: scoped blockers are represented, but live isolation and freshness proof remain | External-receipt signature/freshness tests and canary proving unrelated lanes continue without fabricated evidence |
| Product identity and caller-forged approval | Product/trust rows | Prior audit demonstrated caller-laundered identity strength and mutable workload/environment IDs could approve | PROVEN-BASELINE after self-authenticating identity repair; package-ID mapping and exact V3.1 tests pending | Recomputed identities/strengths, hostile serialization probes, installed-wheel journey, exact schema/vector receipts |
| Evidence completeness and omitted ranks/collectives | Product/trust rows | Prior audit demonstrated caller-defined OPTIONAL rosters and incomplete multi-rank traces could approve | PROVEN-BASELINE after fixed pack completeness and raw-CAS recomputation; V3.1 mapping pending | Fixed requirement roster, omitted-rank/collective negative controls, raw evidence binding, installed journey |
| Native tool/source/findings integrity | Product/trust rows | Prior audit forged tool versions, findings, native decisions, and unsupported `2.5evil` inputs | PROVEN-BASELINE after exact allowlists/full raw re-import; V3.1 mapping pending | Full canonical record comparison, unsupported/malformed negative tests, attribution-safe human report |
| CAS metadata, identity binding, and filesystem races | Product/security rows | Prior audit substituted metadata and escaped parent directories through symlink races | PROVEN-BASELINE after authenticated metadata and dir-fd writes; V3.1 mapping pending | Replayed metadata digests, cross-identity rejection, high-iteration race canaries, clean-wheel evidence |
| Local execution and economics authority | Product/value rows | Prior audit found presence-only recipe digests and caller-authored economics could approve | PROVEN-BASELINE after bound recipe artifacts and deterministic economics; package mapping pending | Exact input/output/economics provenance and policy-verifier records at candidate SHA |
| Parser/report hardening | Product/security rows | Prior audit found recursion failure, cross-rank metadata mismatch, secret leakage, and Markdown injection | PROVEN-BASELINE after bounded parser, recursive redaction, rank equality, and escaped report output | Malformed/depth/secret/injection negative suite in hosted installed-package check |
| Hosted CI and exact-SHA checks | G012-G014, G018 and activation rows | Prior V3 exact-SHA workflows eventually passed after correcting action pins and runner/billing state | PROVEN-BASELINE only: V3.1 requires PR rules and verifier-backed machine merge | Ruleset-enforced PR checks at exact head SHA, stale/wrong/partial check rejection, signed merge authorization |
| Live unattended activation | H001-H005, H008, H015, J011 | Prior V3 controller stayed stopped by design; startup preflight was only bounded and no production loop canary was run | OPEN | All mandatory canaries, signed activation receipt, exact merge SHA, reboot observation, intervention `NONE`, automatic recovery without humans |

## Package-wide row accounting

The package matrix contains 158 rows. Its starting verdicts are not accepted as current truth:

- 47 `PROVEN`
- 4 `CONTRADICTS_BUNDLE`
- 46 `DEFECT`
- 30 `PARTIAL`
- 15 `NOT_PROVEN`
- 10 `EXTERNAL_WAIT`
- 6 `DEFERRED_BY_SCOPE`

Current-SHA hostile reclassification is complete in the machine-readable [158-row ledger](./V3_1_ZH_158_ROW_FINDINGS_LEDGER.json). It contains all 158 unique IDs, every original package field, current-SHA classification, evidence paths, remediation phase, positive and hostile controls, rollback behavior, and before/after status.

The Phase-0 current classifications are:

- 71 `PROVEN_BASELINE` — objective proof exists at `1ae79ba02c2b0cbec9b21ad3d2fc08d0afdbface`, but V3.1-sensitive claims must still be replayed under the new immutable authority and verifier.
- 41 `PARTIAL`.
- 31 `DEFECT`.
- 3 `OPEN_CONFLICT`.
- 10 `EXTERNAL_WAIT` — these remain scoped and cannot globally block independent engineering lanes.
- 2 `DEFERRED` — these may not be used as completion proxies.

There are 75 Phase-0 open findings, including 40 critical open findings. The package matrix has 45 critical rows, while its acceptance contract lists only 44 critical IDs. The omitted row is `B004`; V3.1 remediation must add it explicitly as a critical, scoped, nonblocking external wait.

The independent hostile audits converged on five causal blocking groups:

1. coherent V3.1 authority and package bootstrap (`A003`, `A006-A009`, `A012`, `A018`, `B005`, `D005`, `G012`, `G018`);
2. independent verifier, receipt lifecycle, and server policy (`B006`, `G005-G007`, `G013-G014`, `H015`);
3. backend/recovery execution and typed continuation (`E003-E008`, `E014`, `E017`, `F002-F004`, `F006`, `F008-F012`, `F015-F017`, `H004`);
4. enforced complete-substitute/value and executable research gates (`B008`, `B010`, `C013`, `G009-G010`, `J001-J002`, `J010`, `J012`);
5. exact-SHA live canaries and activation (`B001`, `B003`, `H001-H009`, `H013`).

The product preflight spine itself is baseline-proven: hostile identity, CAS, parser, importer, native, completeness, redaction, filesystem-race, and clean installed-wheel controls passed. That evidence does not close the disconnected value gate, independent verifier, server protection, or live-autonomy rows.

## Closure evidence required per row

Every resolved row must record:

1. requirement ID and controlling clause;
2. exact candidate SHA;
3. implementation files and protected ownership boundary;
4. positive test or live canary;
5. negative/adversarial control;
6. local and hosted check names/results;
7. machine receipt or external evidence reference when applicable;
8. rollback behavior;
9. final classification and reason.

No row may be closed from prose, simulated output, agent-authored external evidence, a check from another SHA, or an unprotected repository file that can authorize itself.
