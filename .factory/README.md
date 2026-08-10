# Durable factory state

`roadmap.json` is mechanically generated from the protected 124-task roadmap. Per-task state belongs under `tasks/`; bounded handoffs, gate outcomes, external evidence, source locks, costs, sessions, and checkpoints use their matching directories.

The ledger does not grant activation. The factory controller may queue T001 only after subscription OAuth, role calibration, hidden-gate isolation, recovery controls, and private release routing are verified.
