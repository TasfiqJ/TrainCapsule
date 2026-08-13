# Required Codex Final Report — TrainCapsule V3.1-ZH

Do not replace evidence with narrative. Use `NOT_PROVEN`, `EXTERNAL_WAIT`, or `BLOCKED` where proof is absent.

## 1. Executive disposition

- Final status: `ACTIVATED | NOT_ACTIVATED | PARTIALLY_REMEDIATED_BLOCKED`
- Exact final local SHA:
- Exact final remote `main` SHA:
- Active source generation:
- Active milestone:
- Controller running:
- Intervention mode:
- Unsupported claims that remain prohibited:

## 2. Starting state and preservation

- Starting local SHA:
- Starting remote SHA:
- Starting branch:
- Dirty/user work preservation:
- Safety tag/ref:
- Rollback bundle/artifact:
- Baseline test result:

## 3. Branch, PR, and commits

- Hardening branch:
- PR URL/number:
- Auto-merge/merge queue state:
- Commit table: SHA, subject, phase, tests.

## 4. Source authority migration

- Historical bundles and hash proof:
- V3.1-ZH directory:
- Manifest digest:
- Active pointer:
- Mixed-generation negative test:
- Shadow overrides retired:
- Residual-risk disclosure location:

## 5. External machine authority

- Installation path:
- Service account:
- Repository write permission: yes/no
- Push/merge permission: yes/no
- Public-key fingerprint:
- Policy ID/version:
- Receipt schema/version:
- GitHub check name:
- Activation receipt:
- Negative tests and artifacts:
- Secrets exposed: must be `no`.

## 6. GitHub release enforcement

- Ruleset/branch protection export:
- Required checks:
- Force-push setting:
- Deletion setting:
- Human approvals required:
- Auto-merge/merge queue:
- Direct-main push rejection evidence:
- Bad-candidate rejection evidence:
- Crash-idempotency evidence:

## 7. Controller/runtime remediation

Report exact evidence for source resolution, task outputs, scopes/tools, context/freshness, backend, leases, paths, supervisor, status, retry/repair/respec, quota/auth, findings/evidence, native/value, completion/milestones, and lane isolation.

## 8. Live canary table

Columns:

```text
canary
exact candidate SHA
command/event sequence
expected
observed
artifact paths
artifact hashes
verdict
```

Include every mandatory canary from the acceptance contract.

## 9. Test and CI table

Columns:

```text
command/workflow
scope
exact SHA
start/end time
exit/conclusion
artifact/log URL or path
digest
classification
```

## 10. 158-row conformance matrix

Provide updated CSV and summary counts by verdict. Every changed row needs implementation evidence and test/canary evidence.

## 11. Product preservation

- Product package tests:
- Install-to-preflight journey:
- Identity oracle:
- Flight Recorder import:
- Truth/UNKNOWN states:
- Claims/nonclaims review:

## 12. External waits and prohibited claims

List each external wait, dependent scope, unaffected lanes, and required attributable receipt. List all claims still unsupported.

## 13. Deviations and blockers

For each deviation:

```text
requirement ID
requested behavior
actual behavior
reason
risk
what remains
activation impact
```

## 14. Activation and operations

- Signed activation receipt identity:
- STOP/PAUSE transition:
- Scheduled service state:
- Reboot/restart observation:
- First autonomous cycle:
- Idle cycle:
- External-wait isolated cycle:

## 15. Rollback

Exact commands and artifacts needed to restore the starting state, disable the controller, revoke machine authority, close/disable auto-merge, and preserve evidence.
