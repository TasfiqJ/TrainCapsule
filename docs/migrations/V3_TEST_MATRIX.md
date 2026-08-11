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
| Backend | protocol, Claude adapter, fake backend, redaction, checkpoint recovery | pending |
| Release/startup | PR-mode dry run, exact SHA, bounded restart, portable controls | pending |
| Legacy migration | 124-entry mapping, dry run, queue archive, deterministic migration | pending |
| Product preflight | identity golden vectors, CAS, importer, native baseline, completeness, eligibility, CLI | pending |
| Product journey | install through preflight; missing/native-sufficient/unsupported/policy/unknown/malicious cases | pending |
| Security | secrets, paths, symlinks, malicious input, synthetic evidence, forged/expired approval | pending |
| Rollback | disposable-clone/worktree rehearsal and restored baseline | pending |
| GPU/external | real GPU, customer archive, independent operator, human approval | external/deferred; never simulated as complete |

Every final result records the exact command, SHA, pass/fail count, and whether a failure was pre-existing or introduced.
