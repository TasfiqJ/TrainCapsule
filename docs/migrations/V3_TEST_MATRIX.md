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
| Product preflight | identity golden vectors, CAS, importer, native baseline, completeness, eligibility, CLI | passed; 41 product checks and 527-test full-suite regression |
| Product journey | install through preflight; missing/native-sufficient/unsupported/policy/unknown/malicious cases | passed on controlled local fixtures; no GPU/customer claim |
| Security | secrets, paths, symlinks, malicious input, synthetic evidence, forged/expired approval | product adversarial coverage passed; final repository secret gate is recorded below |
| Rollback | detached disposable worktree at safety ref; authority and baseline suite | passed; exact base SHA, 394 baseline tests, worktree removed |
| GPU/external | real GPU, customer archive, independent operator, human approval | external/deferred; never simulated as complete |

Every final result records the exact command, SHA, pass/fail count, and whether a failure was pre-existing or introduced.

## Phase J exact commands

```text
scripts/gates/fast_quality.sh
uv run --active --no-sync pytest -q tests/product
uv run --active --no-sync pyright packages scripts/generate_product_schemas.py tests/product
uv run --active --no-sync python scripts/generate_product_schemas.py --check
uv build --offline --wheel
```

Results: 41 product checks passed; 527 complete-suite checks passed; Ruff passed; strict Pyright
reported 0 errors and 0 warnings; ten product schemas matched; the wheel built. These checks used no
model session, GitHub mutation, controller start, or paid service.

## Final acceptance exact commands

```text
scripts/gates/full_quality.sh
scripts/verify_factory_authority.sh
scripts/gates/no_paid_usage.sh
uv run --active --no-sync python scripts/generate_v3_schemas.py --check
uv run --active --no-sync python scripts/generate_v3_roadmap.py --check
uv run --active --no-sync python scripts/generate_v3_legacy_migration.py --check
uv run --active --no-sync python scripts/generate_product_schemas.py --check
uv run --active --no-sync python scripts/update_v3_migration_inventory.py --check
uv run --active --no-sync tcfactory config validate
uv run --active --no-sync tcfactory migrate-roadmap --from-v2 --dry-run
```

Final results before publication: secret scan passed; Ruff passed; strict Pyright reported 0 errors
and 0 warnings; 527 tests passed; both source authorities passed; 32 factory schemas, ten product
schemas, 109 roadmap items, and 124 legacy mappings matched; configuration validation and the
migration dry-run passed; the no-paid-usage gate passed.

The built wheel was installed into a new Python 3.12 virtual environment. Installed-wheel `doctor`,
workload identity, and Flight Recorder import commands passed. Dependency installation contacted the
public package registry only; it did not invoke a model or paid API.

Rollback rehearsal used a detached worktree at
`6b480232fa92b069103da44c475bd17bcb3e6bd1`. Historical authority, Ruff, strict Pyright, and all 394
baseline tests passed. The rehearsal worktree was removed and `main`/runtime were unchanged.

No GPU check was run. GPU/customer/external evidence remains deferred.
