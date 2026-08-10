# T001 verification record

Task: Commit final source-of-truth bundle and precedence rules.
Role: research. Recorded 2026-08-10 (UTC date only).
Base commit: `035a3c562fde9690903af34ae3730f1d9a904c4f`. All checks in this record were re-measured at that
commit; digests, gate exit codes, and raw captures below supersede the readings taken at
`5fa0711660cce164e5d6fec320e62695ef0b24cc`.
Environment: linux WSL2, sandboxed, network denied, no credentials used.

All statements below are deterministic local measurements over repository bytes at the base commit.
No customer, upstream maintainer, benchmark, accelerator hardware, or production evidence is claimed.
Raw captured output is stored verbatim under `docs/evidence/T001/raw/`.

## 1. Normative behavior checks

| ID | Statement | Command | Result | Truth state |
| --- | --- | --- | --- | --- |
| NB1 | Every manifest-locked bundle file matches its recorded SHA-256. | `(cd docs/source-of-truth/final-2026-08-09 && sha256sum -c "$PWD/../../evidence/T001/final_bundle.sha256")` | 20 of 20 lines `OK`, exit 0. `git ls-files` reports 21 tracked files in the bundle directory (20 locked files plus `FINAL_MANIFEST.json`); `git status --short` on that directory reports 0 lines. | PASS |
| NB2 | The manifest excludes itself; the docs copy and the source-lock copy are byte-identical. | `sha256sum -c docs/evidence/T001/manifest_copies.sha256` | 4 of 4 lines `OK`, exit 0. Both `FINAL_MANIFEST.json` copies hash to `51872ae1eacce06869a5924143b896364372b2b95997dcd3b4e3af080c9e6bdc`. `files` map holds 20 entries and does not contain `FINAL_MANIFEST.json`. | PASS |
| NB3 | `SOURCE_PRECEDENCE.md` section 1 order equals `FINAL_MANIFEST.authority_order`. | parse both lists, compare element-wise (`docs/evidence/T001/raw/nb3_nb4_consistency.txt`) | `NB3_equal: True`; nine entries, identical order. | PASS |
| NB4 | The three `(1)`-suffixed bundle files are byte-identical duplicates and add no normative content. | sha256 of each pair | `08_ACQUISITION_THESIS(1).md` = `d9eb52ab5993…`, `09_CAREER_AND_HIRING_THESIS(1).md` = `f132056a4845…`, `12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT(1).md` = `4833aeef102e…`, each equal to its unsuffixed counterpart. | PASS |
| NB5 | `README.md` read order and `FINAL_MANIFEST.authority_order` agree on which documents hold authority. | compare `README.md` "Read order" list against `authority_order` | `README.md` lists ten entries and adds `TRAINCAPSULE_FINAL_MASTER_PLAN.md` at position 10; `authority_order` lists nine and omits it. `SUPERSESSION_AND_MIGRATION.md` does not disambiguate. Not resolvable from the bundle alone. | UNKNOWN |

NB5 is **not** converted to a pass. It is recorded as an open discrepancy in `SOURCE_PRECEDENCE.md` section 7.
Resolution requires an independently reviewed ADR. Until then `TRAINCAPSULE_FINAL_MASTER_PLAN.md` is treated as
non-authoritative and normative instructions unique to it must not be acted on.

## 2. Machine gate results (re-run at this commit)

| Gate | Command | Exit | Truth state | Raw capture |
| --- | --- | --- | --- | --- |
| contract | `bash scripts/gates/contract_gate.sh T001` | 0 | PASS | `raw/contract.txt` |
| secret-scan | `bash scripts/gates/secret_scan.sh` | 0 | PASS | `raw/secret_scan.txt` |
| fast-quality | `bash scripts/gates/fast_quality.sh` | 0 | PASS | `raw/fast_quality.txt` |
| real-integration | `bash scripts/gates/real_integration.sh T001` | 0 | PASS | `raw/real_integration.txt` |

### fast-quality raw stdout (verbatim, 6 lines including the recorded exit code)

```
All checks passed!
0 errors, 0 warnings, 0 informations
........................................................................ [ 41%]
........................................................................ [ 82%]
...............................                                          [100%]
EXIT_CODE=0
```

Correction to earlier evidence, retained: a previous revision of `.factory/external-evidence/T001.json` recorded the
fast-quality stdout as containing the string `161 tests passed`. That string does not appear in the gate output.
The gate prints progress dots only. A test count is a **derived** figure obtained by counting dots, and is labelled
as derived wherever it appears. At this commit the dot count is 72 + 72 + 31 = **175**; the earlier derived figure of
161 corresponded to the older commit and is superseded, not corrected upward by any change made in this task.
The verbatim stdout above is the attributable evidence.

### real-integration raw stdout (verbatim)

```
PASS T001: declared outputs and static integration evidence are present
EXIT_CODE=0
```

History of this gate, retained for attribution: at base commit `5fa07116` the gate exited 1 with
`declared outputs are missing: .factory/external-evidence/T001.json` while that file was present and well-formed.
Root cause was `scripts/gates/gate_common.py`, which normalized a declared output with
`pattern.replace("\\", "/").lstrip("./")`. `str.lstrip` strips a *character set*, not a prefix, so the leading `.`
of `.factory/...` was removed and the matcher looked up `factory/external-evidence/T001.json`, which does not exist.
Every declared output whose path begins with a dot was affected. That reading was recorded as INFRASTRUCTURE_ERROR
and was never treated as a pass; no substitute or duplicate file was created to satisfy the broken matcher.

The defect was fixed outside this task, under separate authorization, in commit `e25777e`
(`fix(factory): recover tasks after controller repair`), which replaced `lstrip("./")` with `removeprefix("./")`
and is an ancestor of the current commit. `scripts/gates/**` remains in this stage's forbidden paths and was not
modified by this task. Verified at the current commit:

```
$ git log --oneline -1 -- scripts/gates/gate_common.py
e25777e fix(factory): recover tasks after controller repair
$ git status --short scripts/
(no output)
```

The PASS above is therefore a real gate result on unmodified gate tooling, not an evidence-side workaround.

## 3. Reproduction

From the repository root:

```bash
(cd docs/source-of-truth/final-2026-08-09 && sha256sum -c "$PWD/../../evidence/T001/final_bundle.sha256")
sha256sum -c docs/evidence/T001/manifest_copies.sha256
bash scripts/gates/contract_gate.sh T001
bash scripts/gates/secret_scan.sh
bash scripts/gates/fast_quality.sh
bash scripts/gates/real_integration.sh T001
```

All six commands exit 0 at commit `035a3c56`. Raw captures of each are stored under `docs/evidence/T001/raw/`.

## 3a. Re-runnable oracle for NB1-NB5 (added at commit `bd2b40cc`)

Section 1 previously recorded NB1-NB5 as prose plus one-off captured output. `docs/evidence/T001/verify_precedence.py`
is the machine-checkable form of the same five statements: read-only, no network, no credentials, no subprocess,
stdlib only. It re-derives every NB result from repository bytes at run time rather than reading a stored result.

```
python3 docs/evidence/T001/verify_precedence.py
NB1: PASS - 20 of 20 OK
NB2: PASS - manifest files map = 20, self-excluded
NB3: PASS - declared=9 entries, equal=True
NB4: PASS - 3 of 3 pairs byte-identical
NB5: UNKNOWN - read_order=10, authority_order=9, extra_in_readme=['TRAINCAPSULE_FINAL_MASTER_PLAN.md'], missing_from_readme=[], matches_recorded_discrepancy=True
pass_set=['NB1', 'NB2', 'NB3', 'NB4']
NB5 is UNKNOWN and is excluded from the pass set; see SOURCE_PRECEDENCE.md section 7.
RESULT: NB1-NB4 PASS, NB5 UNKNOWN and unchanged
exit=0
```

NB5 remains UNKNOWN. The script does not decide which list is authoritative; it pins the divergence to exactly
`TRAINCAPSULE_FINAL_MASTER_PLAN.md` and exits 1 if that divergence ever changes, so drift fails loudly instead of
being absorbed. Raw capture: `raw/nb1_nb5_checker.txt`.

Falsification (mutation test): each check was independently forced to fail, proving the oracle is not a
constant-pass. Raw capture: `raw/nb_checker_negative_control.txt`.

| Mutation | Observed |
| --- | --- |
| Flip one digest in a copy of `final_bundle.sha256` | `NB1 FAIL` |
| Flip one digest in a copy of `manifest_copies.sha256` | `NB2 FAIL` |
| Supply a wrong `authority_order` | `NB3 FAIL` |
| Point the duplicate-pair list at two different files | `NB4 FAIL` |
| Change the recorded NB5 divergence | `NB5 FAIL`, return `False` |

The mutations were applied to temporary copies in `$TMPDIR` and to in-memory module constants only. No repository
file was modified by the mutation test.

## 4. Limitations

- Evidence covers byte-level integrity and internal consistency of repository documents only. It does not show
  that the documented product behavior is implemented, correct, or useful.
- `sha256sum -c` verifies content against digests recorded in this repository at this commit. It is not an
  independent third-party notarization or signature.
- NB5 is UNKNOWN and is excluded from the pass set. `verify_precedence.py` pins the divergence; it does not
  resolve which list is authoritative, which still requires an independently reviewed ADR.
- `verify_precedence.py` is evidence tooling under `docs/evidence/`, not a controller gate. `scripts/**` is a
  forbidden path for this stage, so the checker is not wired into `scripts/gates/`; it must be invoked explicitly
  or adopted by a later authorized task.
- The contract gate passed via its "no specification stage" branch; `specs/tasks/T001.md` does not exist and is a
  forbidden path for this stage, so frozen-specification content was not verified.
- No commercial, adoption, or willingness-to-pay evidence exists for this task; that remains
  EXTERNAL_VALIDATION_REQUIRED.
- Gate results were captured in this sandbox (linux WSL2, network denied). No remote CI run is attested here;
  `remote_ci_required` is satisfied by the controller, not by this record.
- The digest of `SOURCE_PRECEDENCE.md` in `docs/evidence/T001/manifest_copies.sha256` is self-recorded in this
  repository. It detects later drift in that file; it does not attest that the file was correct when recorded.
