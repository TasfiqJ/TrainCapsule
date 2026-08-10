---
name: release-proof
description: Make a read-only release decision from exact candidate SHA, machine gates, hidden-gate verdict, value evidence, and reviewer reports.
allowed-tools: Read Grep Glob Bash
---
Do not fix code. Confirm the exact SHA, protected assets, deterministic results, value threshold, and unresolved statuses. PASS only when every required gate passes. BLOCK when authority or external evidence is missing.
