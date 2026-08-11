# TrainCapsule V3 test matrix

## Baseline

The exact baseline and results are recorded in `V3_BASELINE_REPORT.md`: 394 tests passed, with Ruff, strict Pyright, schema comparison, packet validation, catalog validation, secrets, authority, billing, and repair-scope gates all green.

## Migration matrix

| Area | Required evidence | Current state |
|---|---|---|
| Source authority | deterministic manifest; positive and tamper/duplicate/archive negatives | passed |
| V3 models | strict work items, transitions, milestones, maturity, approvals, receipts, candidate manifest | passed |
| Scheduler/policy | lane independence, WIP, deterministic score, finite retries, repeated finding, hard stuck | passed; 40 focused checks and 430-test full-suite regression |
| Completion/context/value | proposal-only expansion, scoped context/freshness, terminal value outcomes | passed; focused adversarial coverage and 443-test full-suite regression |
| Backend | protocol, Claude adapter, fake backend, redaction, checkpoint recovery | passed; 33 focused checks and 456-test full-suite regression |
| Release | PR-only policy, exact candidate/ref/PR SHA, no force, divergence, required hosted CI, metadata | passed; 22 focused checks and 467-test full-suite regression; no network mutation |
| Startup/status | finite 15/60/300 restart, healthy reset, preflight, portable controls, durable stop/hard-stuck, complete status | passed; focused checks and 471-test full-suite regression; stopped launcher exercised without model use |
| Prompts | finite packet/session, native-first, exact truth states, bounded findings, external/human stop, specialist contracts | passed; focused checks and 478-test full-suite regression; no model use |
| Legacy migration | 124-entry mapping, exact ledger archive, dry/apply, non-resuming queue archive, deterministic migration | passed; 1 passed/1 paused/2 external-wait/120 blocked preserved; 88 mapped, 29 deferred, 7 factory history; original queue retained |
| Product preflight | identity golden vectors, CAS, importer, native baseline, completeness, eligibility, CLI | pending |
| Product journey | install through preflight; missing/native-sufficient/unsupported/policy/unknown/malicious cases | pending |
| Security | secrets, paths, symlinks, malicious input, synthetic evidence, forged/expired approval | pending |
| Rollback | disposable-clone/worktree rehearsal and restored baseline | pending |
| GPU/external | real GPU, customer archive, independent operator, human approval | external/deferred; never simulated as complete |

Every final result records the exact command, SHA, pass/fail count, and whether a failure was pre-existing or introduced.
