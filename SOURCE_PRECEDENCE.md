# Source precedence

The immutable final bundle under `docs/source-of-truth/final-2026-08-09/` is the active product authority.
Task: T001 — Commit final source-of-truth bundle and precedence rules.

## 1. Authority order

1. `00_EXECUTIVE_BUILD_DECISION.md`
2. `03_PRODUCT_STRATEGY_AND_REQUIREMENTS.md`
3. `04_TECHNICAL_ARCHITECTURE.md`
4. `05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC.md`
5. `12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md`
6. `14_CLAUDE_CODE_MASTER_BUILD_PROMPT.md`
7. `08_ACQUISITION_THESIS.md`
8. `09_CAREER_AND_HIRING_THESIS.md`
9. `13_SOURCE_REGISTER.md`

This list is byte-identical to `authority_order` in `docs/source-of-truth/final-2026-08-09/FINAL_MANIFEST.json`
and to the locked copy at `.factory/source-locks/FINAL_MANIFEST.json`. The manifest is the machine-readable
form of this section; if the two ever differ, the manifest wins and the divergence is a stop condition
(rule 6 below).

Generated ledgers, implementation files, agent output, and historical material cannot override these
documents. A proposed source change must stop autonomous work and enter independent review.

## 2. Bundle files that carry no authority

The bundle contains 20 manifest-locked files. Only the nine files in section 1 are authority for product
behavior. The remainder are non-authoritative in the following declared classes:

- **Automation prompts** — `01_CODEX_MASTER_SETUP_PROMPT.md`, `02_CODEX_RESUME_AFTER_REBOOT_PROMPT.md`,
  `03_CODEX_POST_SETUP_AUDIT_PROMPT.md`. Installation and audit procedure only; they do not define product
  requirements.
- **Bundle metadata** — `README.md`, `BUNDLE_STATS.md`, `FINAL_AUDIT_REPORT.md`,
  `SUPERSESSION_AND_MIGRATION.md`. Navigation, integrity, and migration status only.
- **Consolidated narrative** — `TRAINCAPSULE_FINAL_MASTER_PLAN.md`. Present in the bundle and hash-locked,
  but absent from `authority_order`. See the recorded discrepancy in section 7.
- **Byte-identical duplicate copies** — `08_ACQUISITION_THESIS(1).md`, `09_CAREER_AND_HIRING_THESIS(1).md`,
  `12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT(1).md`. Each was verified SHA-256-equal to the file of the
  same number without the `(1)` suffix (evidence: `docs/evidence/T001/final_bundle.sha256`). A `(1)` copy is
  never cited as authority; cite the unsuffixed filename. If a future `(1)` copy ever diverges in hash from
  its base file, that is a stop condition.

`FINAL_MANIFEST.json` intentionally excludes itself from its own `files` map
(`manifest_excludes_itself: true`); its own integrity is recorded in `docs/evidence/T001/manifest_copies.sha256`.

## 3. Precedence outside the bundle

Applied in order, highest first:

1. The nine authority documents in section 1.
2. Accepted ADRs that cite a specific authority section.
3. Source locks under `.factory/source-locks/`.
4. The active task packet.
5. Everything else — generated ledgers, code, tests, agent output, historical material.

A lower tier never silently overrides a higher tier. It may only record that a conflict exists.

## 4. Superseded material

Per `SUPERSESSION_AND_MIGRATION.md` (bundle, non-authoritative status file) and `README.md` §Supersession:
only files in this bundle are active authority. Earlier executive decisions, product definitions,
architectures, trust specs, theses, roadmaps, and build prompts are historical input only. They must not
appear in the authority order, generate tasks, or override schemas or incident packs.

## 5. Precedence for external and empirical claims

Claims about third-party systems, vendors, papers, and market behavior are governed by
`13_SOURCE_REGISTER.md` §Research rules, quoted in effect:

- Primary official documentation and original papers outrank secondary summaries.
- Vendor documentation establishes public product capability and vendor claims, not independent performance.
- Preprints establish author-reported findings, not universal industry rates.
- Public absence does not prove internal absence.
- Strategic conclusions are labeled reasoned inferences.
- Commercial demand and price remain unproven until payment and repeat use.

No document in the bundle upgrades an external claim to verified. Such claims stay
`EXTERNAL_VALIDATION_REQUIRED` until real attributable behavior exists.

## 6. Conflict and stop rules

Stop autonomous work and report a non-pass truth state when any of the following holds:

- Two authority documents give contradictory normative instructions.
- `SOURCE_PRECEDENCE.md` section 1 and `FINAL_MANIFEST.authority_order` disagree.
- The two `FINAL_MANIFEST.json` copies disagree.
- A bundle file's SHA-256 differs from its manifest entry.
- A file is added to or removed from the bundle without a manifest update.

None of these may be resolved by editing the bundle. Resolution requires independent review and a
separately accepted ADR.

## 7. Recorded discrepancy (open, not resolved by this task)

`README.md` §"Read order" lists ten entries: the nine authority documents plus
`TRAINCAPSULE_FINAL_MASTER_PLAN.md` at position 10. `FINAL_MANIFEST.authority_order` lists only the nine.
`SUPERSESSION_AND_MIGRATION.md` §"Migration verification" requires that "source authority matches the final
read order", which does not disambiguate the two lists.

Truth state: **UNKNOWN**. This task does not resolve it. Until an independently reviewed ADR resolves it,
`TRAINCAPSULE_FINAL_MASTER_PLAN.md` is treated as non-authoritative consolidated narrative (section 2), and
any normative instruction found only in that file must not be acted on. `README.md` and
`SUPERSESSION_AND_MIGRATION.md` are themselves outside the authority order, so neither can raise a document
into it.

## 8. Machine-checkable verification

Run from the repository root:

```bash
# 1. Every manifest-locked bundle file matches its recorded digest (20 files, manifest excludes itself).
(cd docs/source-of-truth/final-2026-08-09 && sha256sum -c "$PWD/../../evidence/T001/final_bundle.sha256")

# 2. Manifest copies and this precedence file match their recorded digests.
sha256sum -c docs/evidence/T001/manifest_copies.sha256

# 3. Declared T001 outputs and static integration evidence are present.
bash scripts/gates/real_integration.sh T001

# 4. Re-runnable oracle for all five normative behaviors NB1-NB5 (read-only, no network).
python3 docs/evidence/T001/verify_precedence.py

# 5. Oracle for the evidence ledger itself: readings are current and no non-pass state is absorbed.
python3 docs/evidence/T001/verify_evidence_currency.py
python3 docs/evidence/T001/verify_evidence_currency.py --self-test
```

Check 4 is the machine-checkable form of sections 1, 2 and 7 of this file. It re-derives NB1 (bundle digests),
NB2 (manifest self-exclusion and copy equality), NB3 (section 1 order equals `authority_order`), NB4 (the three
`(1)` duplicates are byte-identical) and NB5 (the `README.md` read-order divergence). It exits 0 only when
NB1-NB4 measure PASS **and** the NB5 divergence is still exactly `TRAINCAPSULE_FINAL_MASTER_PLAN.md`.
NB5 is never reported as PASS; the script prints it as UNKNOWN and excludes it from the pass set, so a later
change to that divergence fails the check rather than being silently absorbed. The script's ability to fail was
mutation-tested: each of the five checks was independently forced to FAIL
(`docs/evidence/T001/raw/nb_checker_negative_control.txt`). Observed output:
`docs/evidence/T001/raw/nb1_nb5_checker.txt`.

Checks 1, 2 and 3 pass; the most recent re-measurement is recorded in `.factory/external-evidence/T001.json`
under `base_sha`, and check 5 (`EC1`, `EC2`) is what keeps that commit reference from going stale unnoticed.
Check 3 previously exited 1 with
`declared outputs are missing: .factory/external-evidence/T001.json` while that file was present, caused by a
path-normalization defect in the gate tooling (`scripts/gates/gate_common.py`, `lstrip("./")` strips the leading
dot of a dot-prefixed path). That defect was fixed under separate authorization in commit `e25777e`
(`removeprefix("./")`), which is an ancestor of this commit; the gate now exits 0 with
`PASS T001: declared outputs and static integration evidence are present`. No duplicate or substitute file was
created at any point to satisfy the broken matcher. Detail and raw measurement:
`docs/evidence/T001/verification.md` §2.

Check 5 covers the evidence ledger rather than the bundle. Checks 1-4 can pass while the ledger that reports them
has gone stale, which is how a set of true readings can end up describing a tree that has since moved. The checker
enforces five invariants: `EC1` the ledger's `base_sha` resolves and is `HEAD` or an ancestor of it; `EC2` every
path changed between `base_sha` and `HEAD` is evidence-only, so no normative artifact moved after the readings
were taken; `EC3` every declared output and raw evidence path exists; `EC4` the truth-state vocabulary is closed
and no gate claims PASS with a nonzero exit code; `EC5` no non-pass truth state is aggregated into a pass claim,
which is what keeps NB5 from being absorbed by a summary line. `--self-test` is its negative control: it applies
five targeted single-field mutations and requires each to break its own invariant. Observed output:
`docs/evidence/T001/raw/attempt6/evidence_currency.txt` and
`docs/evidence/T001/raw/attempt6/evidence_currency_negative_control.txt`.

Raw observed output and truth states: `.factory/external-evidence/T001.json` and `docs/evidence/T001/verification.md`.
Verbatim gate stdout: `docs/evidence/T001/raw/`; the most recent full re-measurement is
`docs/evidence/T001/raw/attempt6/`.

Neither this file nor the evidence ledger claims that the bundle's content is substantively correct or complete.
Every check above is byte-level integrity and internal consistency over repository bytes, measured locally in a
network-denied sandbox and self-recorded. Independent confirmation, including the remote CI run the task packet
requires, is outstanding and is not counted as a pass.
