---
name: adversarial-review
description: Review a candidate under the assumption that it is wrong, fake, over-normalized, or commercially immaterial until disproved.
allowed-tools: Read Grep Glob Bash
---
Try to falsify the task. Look for test weakening, circular authority, mocked real paths, status laundering, illegal transformations, unmeasured claims, hidden manual steps, security escapes, and regressions outside the diff. Return concrete commands or counterexamples, not general criticism.
