---
name: source-audit
description: Pin official primary sources, exact versions, hashes, and claim boundaries for TrainCapsule research tasks.
allowed-tools: Read Grep Glob Bash WebFetch WebSearch Write Edit
---
Prefer official documentation, registries, repositories, papers, standards, and issue records. Record exact URLs or repository paths, versions, UTC/offset timestamps, sanitized reproduction commands, query shapes, raw artifact paths, SHA-256 digests, licenses, and whether each statement is normative, empirical, incident-level, inferred, or UNKNOWN.

For every negative/absence claim, preserve the raw target result and prove the endpoint with a same-shape positive control. Add a negative/error control when filtering semantics could otherwise be ambiguous. A blocked, malformed, stale, uncontrolled, or zero-only query is UNKNOWN. Maintain stable finding IDs and a machine-readable evidence manifest so an independent role can reproduce the claim without trusting the research prose.
