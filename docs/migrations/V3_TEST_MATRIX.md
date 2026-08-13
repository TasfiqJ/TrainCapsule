# TrainCapsule V3 test matrix

> **HISTORICAL V3 TEST RECORD — NOT CURRENT V3.1-ZH ACCEPTANCE.** The historical tables and results below
> describe the frozen V3 baseline under its superseded release policy. Current V3.1-ZH status is
> `STOPPED / NOT AUTHORIZED` and M0 is active/pending. The repository's Phase 4 PR-only
> publisher is implemented, but external repository rules, trusted check identity, verifier
> installation, and signed activation evidence remain unprovisioned; see
> `docs/migrations/V3_1_ZH_CODEX_EXECUTION_STATE.md`.

> Historical acceptance at `f1fd8077fee001fa6751aa86b26f341f04d0d150` superseded the
> phase-by-phase counts below at that SHA only. Its 554-test local result and eight remote workflow
> runs must not be attributed to a later repair.

## Current V3.1-ZH candidate status

Implementation candidate `81e46ce5ad95c588c8fae3bd64f5704e40ac984b` is pushed on the draft
PR branch. Scoped candidate evidence includes exact 109-row completion policy, 63 V3 schemas,
repository-wide Ruff, strict Pyright with zero errors, 71 product/trust tests, 28 controller
simulations, 124 exact legacy mappings, 11 hostile legacy tests, and 11 hosted-runtime regression
tests. These results do not constitute complete candidate acceptance.

Still pending are the canonical full local/pre-evidence gate, every exact-head hosted PR check,
the independent root-owned verifier/runtime installation, trusted GitHub App and exact ruleset,
V3.1 M0 receipts, all 20 live canaries, a signed LIVE activation transaction, and the ordered
seven-event post-activation observation. See
`docs/migrations/V3_1_ZH_REMAINING_ACCEPTANCE.md` and the candidate section of the 158-row ledger.

## Baseline

The exact baseline and results are recorded in `V3_BASELINE_REPORT.md`: 394 tests passed, with Ruff, strict Pyright, schema comparison, packet validation, catalog validation, secrets, authority, billing, and repair-scope gates all green.

## Migration matrix

| Area | Required evidence | Historical V3 state |
|---|---|---|
| Source authority | deterministic manifest; positive and tamper/duplicate/archive negatives | passed |
| V3 models | strict work items, transitions, milestones, maturity, approvals, receipts, candidate manifest | passed |
| Scheduler/policy | lane independence, WIP, deterministic score, finite retries, repeated finding, hard stuck | passed; 40 focused checks and 430-test full-suite regression |
| Completion/context/value | proposal-only expansion, scoped context/freshness, terminal value outcomes | passed; focused adversarial coverage and 443-test full-suite regression |
| Backend | protocol, Claude adapter, fake backend, redaction, checkpoint recovery | passed; 33 focused checks and 456-test full-suite regression |
| Release | main-only exact-SHA policy, no non-main ref, no force, divergence, durable recovery, required hosted CI, automatic ordinary revert | passed locally and all eight required workflows passed at exact implementation SHA `f1fd8077…` |
| Startup/status | finite 15/60/300 restart, healthy reset, preflight, portable controls, durable stop/hard-stuck, complete status | passed; focused checks and 471-test full-suite regression; stopped launcher exercised without model use |
| Prompts | finite packet/session, native-first, exact truth states, bounded findings, external/policy stop, specialist contracts | passed; focused adversarial coverage; no model use |
| Legacy migration | 124-entry mapping, exact ledger archive, dry/apply, non-resuming queue archive, deterministic migration | passed historically; 1 passed/1 paused/2 external-wait/120 blocked preserved; 88 mapped, 29 deferred-design, 6 factory, 1 deferred-non-blocking; original queue retained |
| Product preflight | identity golden vectors, CAS, importer, native baseline, completeness, eligibility, CLI | passed; 41 product checks and 527-test full-suite regression |
| Product journey | install through preflight; missing/native-sufficient/unsupported/policy/unknown/malicious cases | passed on controlled local fixtures; no GPU/customer claim |
| Security | secrets, paths, symlinks, malicious input, synthetic evidence, forged/expired approval | product adversarial coverage passed; final repository secret gate is recorded below |
| Rollback | detached disposable worktree at safety ref; authority and baseline suite | passed; exact base SHA, 394 baseline tests, worktree removed |
| GPU/external | real GPU, customer archive, independent operator, customer/payment facts | external/deferred; never simulated as complete |

Every final M0 evidence result is now required to record an exact subject SHA or nonrecursive
mode-aware implementation-tree digest, per-ID allowlisted argv, transcript-derived exit/result/count,
failure attribution, transcript path and
SHA-256, and the active source/precedence/owner-policy digests. Pending records cannot satisfy the M0
evidence gate.

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

## Historical V3 final acceptance exact commands

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

Final results at implementation acceptance: secret scan passed; Ruff passed; strict Pyright reported
0 errors and 0 warnings; 554 tests passed locally; both source authorities passed; 39 factory schemas, ten product
schemas, 109 roadmap items, and 124 legacy mappings matched; configuration validation and the
migration dry-run passed; the no-paid-usage gate passed.

The built wheel was installed into a new Python 3.12 virtual environment. Installed-wheel `doctor`,
workload identity, and Flight Recorder import commands passed. Dependency installation contacted the
public package registry only; it did not invoke a model or paid API.

Rollback rehearsal used a detached worktree at
`6b480232fa92b069103da44c475bd17bcb3e6bd1`. Historical authority, Ruff, strict Pyright, and all 394
baseline tests passed. The rehearsal worktree was removed and `main`/runtime were unchanged.

The independent four-wheel install and complete installed-CLI journey passed locally and in remote
workflow `31563636469`. Remote Factory quality reported 497 non-product tests passing, with product
tests enforced separately by Product unit and Product contract.

## Historical exact-SHA publication acceptance

All required workflows completed successfully at
`f1fd8077fee001fa6751aa86b26f341f04d0d150`:

| Required workflow | Run |
|---|---|
| Factory quality | `31563636477` |
| Product unit | `31563636487` |
| Product contract | `31563636485` |
| Security | `31563636472` |
| Source-of-truth integrity | `31563636497` |
| Packaging install | `31563636469` |
| Docs and schemas | `31563636505` |
| Source freshness | `31563636499` |

The first GitHub-hosted attempt never received a runner because of the private account's
billing/spending restriction. A second defect, an invalid immutable `setup-uv` revision, was also
corrected. Final verification ran on the already-provisioned `traincapsule-wsl-local` runner through
the bounded repository variable; `ubuntu-latest` remains the workflow fallback. This used no new
paid runner entitlement.

The first direct startup-preflight probe returned `AUTH_EXPIRED` because it did not load the launcher
PATH. Loading the real launcher environment then exposed and removed two forbidden V2-only
overrides. Private-gate discovery was moved to its fixed controller-owned path outside the repository.
The corrected launcher-environment preflight returned `ready: true`, `credentials: AUTHENTICATED`,
`runtimeState: CLEAN`, and validated all 16 V3 configuration sets, exact marker, source, legacy
archive, and publication recovery. The runtime-path follow-up raises the current complete-suite proof
to 555 passing tests. No model was invoked. No GPU check was run; GPU/customer/external evidence
remains deferred.

## Historical V3 exact-tree and exact-SHA finalization

The frozen implementation was finalized with:

```text
.venv/bin/python scripts/finalize_v3_m0_evidence.py
scripts/gates/full_quality.sh
.venv/bin/python -m pytest
```

The finalizer's `V3-MIG-020` phase first runs `full_quality.sh --pre-evidence`, which performs complete
acceptance without circularly requiring the still-pending final receipts. The normal invocation then
validates those final receipts and repeats complete acceptance.

Results: five exact M0 records passed; implementation-tree digest
`8a2f80ae17cfe2dbcf45ea296bc7c984901ca2a744809ee4151569203e66db6b` covered 663 files; the independent
full suite passed 599 tests; Ruff and strict Pyright were clean; 45 factory schemas, product schemas,
109 roadmap items, 124 legacy mappings, inventory, source/bundle/policy gates, configuration,
migration dry-run, no-paid-usage, and offline wheel build passed. The real root-owned private-gate
health probe passed without creating a receipt or signature.

The historical V3 handoff instructed exact-main publication. That instruction is superseded and is
not current guidance. Active V3.1 publication must use the automated PR-only path with the trusted
machine-policy App, exact required checks, independently verified receipt, and verified merged SHA.
A historical run ID, an unbound PASS JSON object, or a digest of a self-declared claim is not
acceptable current evidence.
