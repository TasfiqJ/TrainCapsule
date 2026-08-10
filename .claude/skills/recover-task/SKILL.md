---
name: recover-task
description: Recover an interrupted bounded task from durable Git/checkpoint evidence in a fresh session.
allowed-tools: Read Grep Glob Bash Write Edit
---
Start from candidate SHA, handoff, stage result, and machine logs. Preserve valid partial work. Re-run the interrupted stage only. Never rely on old chat memory, weaken evidence, or duplicate a completed stage.
