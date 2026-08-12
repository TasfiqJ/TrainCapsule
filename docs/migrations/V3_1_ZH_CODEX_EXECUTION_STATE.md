# TrainCapsule V3.1-ZH Codex execution state

This file is the durable continuation record for the V3.1-ZH full-remediation execution. It is current as of 2026-08-12 and must be reread with `01_CODEX_MASTER_EXECUTION_PROMPT.md` before every continuation.

## Immutable starting point

- Repository: `TasfiqJ/TrainCapsule`
- Baseline `main` SHA: `1ae79ba02c2b0cbec9b21ad3d2fc08d0afdbface`
- Safety ref: `safety/traincapsule-pre-v3-1-zh-hardening-20260812T122011Z`
- Working branch: `codex/traincapsule-v3-1-zh-hardening`
- Preserved untracked-input archive: `/home/jasim/projects/traincapsule-preservation-20260812T122011Z.tar.gz`
- Preservation archive SHA-256: `037398dc1f42e8f9f79bb3d8e74ca6f05a05204957402a445cd0241ebfca8381`
- Original V3.1-ZH ZIP SHA-256: `8780393305926d04697b78c615645bd908075708b61607c61571a76807551a64`
- Pasted master prompt and packaged master prompt SHA-256: `32ab80745d20e4e4b7fa30c948469a79d0cd9a6800d07bdbda0c9e43394351ed`

The safety tag and branch were pushed before V3.1 implementation changes. Direct pushes to `main`, force pushes, and test or acceptance weakening are prohibited for this execution.

## Package processing

- `00_START_HERE.md` was read first.
- All 43 payloads declared by `12_SHA256SUMS.txt` were verified byte-for-byte.
- All 44 package files, including the checksum ledger, were indexed and processed.
- The package authority order is: master execution prompt; acceptance contract; audit; 158-row finding matrix; historical original V3 sources; repository evidence.
- The package explicitly supersedes the prior owner-directed direct-main deviation with automated PR-only release plus machine authorization and zero human approval.

Durable Phase-0 evidence:

- `docs/migrations/V3_1_ZH_PACKAGE_INTEGRITY.json` — SHA-256 `e759af78caf0d410b0b1f3306c016a1b1af01db52d16faa3c59b916be87fabfd`.
- `docs/migrations/V3_1_ZH_PHASE_0_BASELINE.json` — SHA-256 `db2eac2b8c92475dba7c8c0b803308fac80df2c2d1a5d696945135c9b84e71cf`.
- `docs/migrations/V3_1_ZH_158_ROW_FINDINGS_LEDGER.json` — SHA-256 `dbae15fe968005a46f15b625b4a4ef384964039fa727c7d467433c7e61f49075`.
- Package matrix SHA-256 `0f4101f5b02330931e0e0a9392330aa8fe609c07224fb990bd97021d2b3b9f6b`.
- Checksum ledger SHA-256 `299e273b9eeed2e7ea0db923855edff9098a21865989a617e75acf8834c16310`.

## Current phase

Phase 0 — safety, inventory, baseline proof, and hostile cross-reference — is complete and awaiting its isolated baseline commit.

Completed Phase 0 actions:

- frozen the exact successful V3 baseline;
- archived untracked user/package inputs without changing them;
- created and pushed the annotated safety tag;
- created and pushed the hardening branch;
- verified package integrity and prompt identity;
- collected current local runtime, GitHub, queue, milestone, and Windows-task facts;
- started three independent, read-only hostile audits covering factory/runtime, product/trust, and authority/zero-human acceptance.
- completed the exact 158-row current-SHA hostile classification and recorded all closure fields;
- recorded the extracted-package source-tree defect without losing the independently matching historical files;
- recorded all 32 existing worktrees, V2/V3 queue state, checkpoints, runtime controls, scheduled tasks, GitHub state, and exact hosted baseline runs.

No V3.1 implementation commit exists yet. No draft PR exists yet. The first commit contains only the Phase-0 durable evidence listed above.

## Exact baseline evidence

The baseline at `1ae79ba02c2b0cbec9b21ad3d2fc08d0afdbface` had:

- 599 local tests passing;
- Ruff and strict Pyright passing;
- 45 generated schemas current;
- 109 V3 roadmap items and all 124 legacy mappings validated;
- package/build/config/migration/no-paid-use gates passing;
- all eight required hosted workflows passing at the exact SHA;
- an exact-SHA signed private-gate proof passing under the previous trust model;
- exact-SHA migration marker and STOP-free startup preflight passing during a bounded probe;
- the durable STOP marker restored immediately after that probe.

These facts prove only the completed V3 baseline. They do not prove V3.1-ZH acceptance.

## Current runtime and external state

- Product controller: stopped.
- Durable STOP marker: present.
- Windows `TrainCapsule Lights-Out Autopilot` task: disabled.
- Current active milestone: `M1_NATIVE_PREFLIGHT`.
- Current queue: 61 `PROPOSED`, 1 `READY`, 12 `WAITING_EXTERNAL`, 2 `BLOCKED_TECHNICAL`, 13 `PASSED_ENGINEERING`.
- Current external blockers: `V3-MKT-003` through `V3-MKT-007` remain receipt-bound.
- Current controller claims/leases: none.
- Current publication transactions: none.
- Existing GitHub runner: online as a separately launched WSL process.
- Repository visibility: public.
- GitHub rulesets: none.
- `main` branch protection: absent.
- Existing private-gate installation is the previous `/var/lib/traincapsule-factory/private-gates` design, not the V3.1 independent verifier service.
- Windows Automatic Activation, Calibration Recovery, and GitHub Runner tasks remain enabled and require V3.1 disposition.

## Open blockers that prohibit activation

All package findings are presumed unresolved until the cross-reference records exact current-SHA proof. At minimum:

1. GitHub ruleset and `main` protection are absent.
2. The current repository release configuration implements the superseded direct-main policy, not V3.1 automated PR-only release.
3. The separately owned and independently operated V3.1 verifier service is absent.
4. Exact-SHA machine receipts for PR merge and activation are absent.
5. Mandatory negative controls and live canaries have not been executed against a V3.1 candidate.
6. The exact `milestone-status` operator command required by the package is absent.
7. Enabled legacy/automatic Windows tasks have not been reconciled with the new activation contract.
8. Current blocked work items and retained checkpoints require explicit recovery/disposition proof.
9. The 75 open Phase-0 findings need implementation and exact-candidate closure evidence; the other 83 rows still require final V3.1 replay or authorized external/deferred disposition.

Open findings by exact ID:

`A003 A006 A007 A008 A009 A011 A012 A018 B001 B003 B005 B006 B008 B010 C002 C003 C013 C014 D003 D005 D007 D008 D009 D010 D011 E003 E004 E005 E006 E007 E008 E012 E014 E017 F002 F003 F004 F006 F008 F009 F011 F012 F015 F016 F017 G002 G005 G006 G007 G009 G010 G012 G013 G014 G016 G018 H001 H002 H003 H004 H005 H006 H007 H008 H009 H013 H015 H016 I012 J001 J002 J008 J010 J011 J012`

Critical open findings:

`A006 A007 A008 B001 B005 B006 B008 C013 D005 D009 D010 E003 E004 E005 E007 F003 F004 F006 F008 F011 F012 F015 F016 G005 G006 G007 G009 G010 G012 G013 G014 G018 H001 H002 H003 H004 H005 H008 H015 J011`

Critical contract defect: matrix row `B004` is critical but absent from the acceptance contract's critical-ID list. It remains an honest, nonblocking external wait and must be added explicitly during Phase 1.

## Mandatory canaries still pending

- `real_claude_mechanical_task`
- `process_kill_and_resume`
- `quota_pause_and_resume`
- `authentication_expiry_and_recovery`
- `repeated_finding_finite_stop`
- `external_wait_lane_isolation`
- `bad_candidate_rejected_before_main`
- `release_transaction_crash_idempotency`
- `automatic_milestone_advancement`
- `machine_receipt_missing_invalid_expired_revoked`
- duplicate-controller rejection
- claim-renewal failure
- stale-current-facts rejection
- missing-authoritative-source rejection
- malformed-agent-report rejection
- private-gate-missing rejection
- verifier-unavailable rejection
- wrong-activation-SHA rejection
- external-runtime-root operation
- post-merge invariant failure and automated revert PR

## Activation state

`STOPPED / NOT AUTHORIZED`

The STOP marker and disabled product-controller task must remain unchanged until every applicable `CRITICAL` and `HIGH` acceptance row, server-side rule, independent verifier check, exact-SHA receipt, negative control, and mandatory canary passes. Activation must be a machine-authorized, SHA-bound transition with intervention mode `NONE`.

## Next exact action

Validate the four Phase-0 durable artifacts, record their final hashes, commit only those intended files as `chore: record v3.1 zh hardening baseline`, and push the hardening branch. Then begin Phase 1 by installing a coherent V3.1-ZH authority without changing either historical source generation.

## Rollback and safe stop

For any ambiguous or failed phase: preserve artifacts, create/retain STOP, disable product-controller activation, do not merge, and return to the annotated safety ref for comparison. Never force-update `main` or delete preserved queue, checkpoint, evidence, or untracked user inputs.
