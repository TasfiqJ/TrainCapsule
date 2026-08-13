# Start Here — TrainCapsule Codex V3.1-ZH Remediation Package

## What to give Codex

Give Codex this entire extracted folder or the ZIP that contains it, and give Codex access to the actual `TasfiqJ/TrainCapsule` repository.

Do not send isolated old prompts, duplicate source documents, or the previous chat as separate authority. This package already contains the immutable original V3 review bundle, the audit, the matrix, the acceptance contract, and the execution prompt.

## Recommended launch

1. Open Codex in the repository root.
2. Attach or extract this package outside the tracked repository, or place it under a temporary ignored directory.
3. Paste the contents of `08_LAUNCHER_PROMPT.txt`.
4. Confirm Codex can read `01_CODEX_MASTER_EXECUTION_PROMPT.md` and the `source/` folder.
5. Let Codex execute. It must create a safety ref and hardening branch before mutations.

## Inputs

Required:

- the current TrainCapsule repository, including `.git` history and remote access;
- this package;
- existing Claude Max/Claude Code authentication available to the runtime;
- existing GitHub CLI/authentication for repository/ruleset/PR/check operations;
- one-time administrator or sudo authority where needed to install the separate verifier service account and root-owned trust roots.

The last three are bootstrap capabilities, not files. Never place their secrets in this package or repository.

## Important

The prompt intentionally keeps the controller stopped until all critical hardening and canaries pass. It does not authorize Codex to manufacture customer facts or to claim full original-V3 conformance after the zero-human amendment.
