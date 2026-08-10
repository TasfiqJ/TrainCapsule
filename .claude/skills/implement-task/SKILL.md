---
name: implement-task
description: Implement one bounded task rigorously, using real interfaces and executable verification without weakening tests.
allowed-tools: Read Grep Glob Bash Write Edit
---
Inspect the task packet and current candidate first. Implement only allowed paths. Run the cheapest deterministic gates before broad tests. Never replace real integration with a mock, lower a threshold, edit protected expectations, or turn UNKNOWN/SKIPPED into PASS. Leave the tree coherent and report exact evidence.
