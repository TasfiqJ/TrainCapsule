# 03 — Codex Post-Setup Audit Prompt

Act as a read-mostly independent installation auditor. Do not redesign TrainCapsule and do not implement product tasks.

Read:

1. `01_CODEX_MASTER_SETUP_PROMPT.md`
2. the final TrainCapsule source-of-truth documents
3. `codex-setup-state/CODEX_FINAL_REPORT.md`
4. `codex-setup-state/CODEX_VERIFICATION.json`

Audit the live WSL repository at `/home/<linux-user>/projects/traincapsule`.

Verify independently:

- Claude subscription OAuth only; no API/gateway/paid fallback.
- Live repository is under `/home`, not `/mnt/c`.
- Git tree is clean and identity is configured.
- Final document hashes match `FINAL_MANIFEST.json`.
- Active authority contains Close–Qualify–Exchange, the two initial packs, and build-first doctrine.
- No superseded product definition or task ledger remains active.
- Public tests, lint, type, schemas, shell, and private gates pass.
- Calibration proves distinct specification, research, product, builder, integration, adversary, performance/security, value, audit, and read-only release sessions.
- Builders cannot access hidden tests or modify protected expected evidence.
- Negative controls are rejected.
- Private GitHub exists, is private, points to the verified SHA, and required Actions pass.
- Windows recovery task exists.
- Controller heartbeat is fresh or quota wait is legitimate.
- Pause/resume and single-instance locking work.
- Public incident corpus, native/bundled matrix, backend absorption register, Wedge Discovery Ledger, and monthly wedge-review machinery exist.
- External demand/payment/adoption claims remain `EXTERNAL_VALIDATION_REQUIRED`.
- Truth rules, contract expiry, recovery limits, security policy, and build-order prohibitions are intact.
- No secret, OAuth token, hidden fixture, or private gate is tracked by Git.
- First dependency-ready task is queued, active, or legitimately waiting.

Write:

- `codex-setup-state/CODEX_INDEPENDENT_AUDIT.md`
- `codex-setup-state/CODEX_INDEPENDENT_AUDIT.json`

Final verdict must be exactly one of:

```text
AUDIT PASS — FACTORY RUNNING
AUDIT PASS — FACTORY WAITING FOR QUOTA
AUDIT FAIL — REMEDIATION REQUIRED
```
