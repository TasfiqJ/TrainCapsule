# 02 — Codex Resume Prompt

Resume the interrupted TrainCapsule Claude-only factory setup from durable state. Do not restart from zero.

1. Locate `codex-setup-state/CODEX_SETUP_STATE.json`.
2. Read:
   - `CODEX_SETUP_STATE.json`
   - `CODEX_RESUME.md`
   - `CODEX_SETUP_LOG.md`
   - `01_CODEX_MASTER_SETUP_PROMPT.md`
   - `FINAL_MANIFEST.json`
3. Verify the final source bundle still matches its recorded hashes.
4. Inspect Windows, WSL, the live repository, Git, scheduled tasks, and any active installer/controller before running commands.
5. Resume at the first incomplete phase and reuse valid completed work.
6. Never replace `/home/<user>/projects/traincapsule` without a verified backup and explicit authorization.
7. Do not create API keys, enable paid fallback, weaken sandboxing, expose hidden gates, lower truth/value thresholds, or bypass failed checks.
8. Ask only for an unavoidable credential/UAC/browser action. Credentials must be entered directly into the browser or hidden terminal prompt.
9. Continue until the factory is verified and active, legitimately waiting for quota, or a precise `CODEX_BLOCKER.md` is written.
10. At completion, update `CODEX_FINAL_REPORT.md` and `CODEX_VERIFICATION.json`.
