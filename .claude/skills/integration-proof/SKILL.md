---
name: integration-proof
description: Verify that a candidate executes the real pinned dependency path and that versions, imports, and protocol boundaries are reproducible.
allowed-tools: Read Grep Glob Bash ListAgents SendMessage
---
Trace imports and subprocesses to the real pinned implementation. Identify mocks, fallbacks, skipped required paths, shared oracle lineage, version drift, and non-reproducible environment assumptions. Cross-session messages must be concise, same-task, and mirrored in the final report.
