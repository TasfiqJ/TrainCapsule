# Unresolved Requirements Extract

Generated from the 158-row matrix. The CSV is canonical.

### Authority & migration

#### `A006` — Run the V3 migration on an isolated branch and draft PR.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Create a safety tag/ref now, stop direct migration on main, and use a hardening branch plus automated PR/merge queue going forward.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A007` — Do not let the current factory autonomously rewrite its governing rules.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Create a new V3.1-ZH source bundle explicitly approved as owner policy; do not shadow the original bundle with higher-precedence runtime files.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A008` — Keep the active authority internally non-contradictory.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Rewrite every affected active document coherently as V3.1-ZH, regenerate the manifest, update context routing, and archive V3 unchanged.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A009` — Route every active governing directive into role context.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Make the active source bundle itself authoritative; remove hidden override dependence. Ensure context manifests include the active policy digest.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A010` — Use a canonical active-source pointer and reject mixed authority generations.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Add active_generation metadata and fail closed when active contexts mix V3 and V3.1-ZH normative generations.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A011` — Record an actual safety ref and rollback path before migration.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Create an immutable tag at the pre-hardening SHA and rehearse exact rollback in a disposable clone.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A012` — Make source-monitor findings create STALE/ADR/wedge-review requests rather than silent rewrites.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Wire freshness receipts into context construction and create deterministic STALE work-item transitions.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A013` — Defer T002 from the product critical path while preserving legacy traceability.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Add a deterministic migration assertion that T002 is DEFERRED_NON_BLOCKING and cannot block any V3 milestone.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A014` — Preserve all 124 legacy entries, statuses, packets, and specs.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Add a manifest of all 124 source entries and deterministic count/hash/mapping tests.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A017` — Bind migration evidence to the exact candidate SHA and actual execution mode.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Separate SIMULATED, CONTROLLED_VALIDATED, and LIVE_VALIDATED evidence; do not let simulation satisfy live migration criteria.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `A018` — Keep original V3 documents as an immutable review artifact after adopting a new owner policy.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Archive V3 as historical review generation and activate a new complete V3.1-ZH manifest.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Zero-human semantics

#### `B001` — No routine founder/operator intervention after bootstrap.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Define ZERO_FOUNDER_INTERVENTION_AFTER_BOOTSTRAP and prove a live canary through task selection, model execution, recovery, release, and next-task scheduling.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B003` — Allow product/factory lanes to continue while market evidence waits.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Run a live test where market items wait while product/competitor/trust items continue.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B005` — If human trust approval is removed, disclose that this is a plan amendment rather than full V3 conformance.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Publish V3.1-ZH with explicit rationale, compensating controls, residual risk, and non-claim that it matches original V3.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B006` — Machine approval must be independent of the candidate-writing agent.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Use a separate root-owned/off-repo verifier with signed scoped receipts, policy version, issuer, expiry, candidate SHA, oracle IDs, and raw evidence hashes.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B008` — A technically valid native duplicate must fail product value.

- **Audit verdict:** `PARTIAL`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement and require NativeSubstituteBenchmark before NATIVE_ADVANTAGE_DEMONSTRATED or commercial promotion.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `B010` — Market actions must be executable without founder orchestration where legally authorized.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Add an explicitly authorized MarketOperationsBackend, consent/identity controls, and attributable inbound/outbound event receipts, or accept external_wait.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Product strategy

#### `C002` — First serious offer is Incident-to-Change Qualification Pilot.

- **Audit verdict:** `PARTIAL`
- **Severity:** `INFO`
- **Required remediation:** Keep as hypothesis and collect external receipts.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C007` — Identity lock must be deterministic and candidate-bound.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Prove golden vectors with an independently implemented verifier, not the production serializer.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C012` — Customer-local execution/security is retained in architecture.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Build a controlled isolated runner and later obtain external customer-local evidence.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C013` — Complete-substitute comparison starts early and repeats.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Enable allowlisted current-source research and make native differential a recurring promotion gate.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `C014` — Commercially support only surfaces that change real decisions.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Create signed external value receipt transition and block COMMERCIALLY_SUPPORTED without it.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### V3 model & roadmap

#### `D002` — Typed work lifecycle includes external/human/technical/value dispositions.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** For V3.1-ZH, replace WAITING_HUMAN with WAITING_MACHINE_AUTHORITY, not with implicit approval.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D005` — M0 completion must reflect actual evidence, not rewritten criteria.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Define V3.1-ZH M0 criteria first, then recompute from independent evidence; do not rewrite requirements during ledger generation.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D007` — External waits are non-blocking to unrelated lanes.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Add integration test and live canary.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D008` — Completion proposals cannot mutate authoritative roadmap directly.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Integrate proposal generation, deterministic validation, machine-authority acceptance, and bounded expansion.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D009` — Milestone completion is evaluated from evidence.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Invoke it at every idle/no-ready transition and after work-item completion.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D010` — Milestone advancement occurs automatically when gates pass.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement atomic transition, event, source digest, next milestone activation, and rollback.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D011` — Roadmap expansion is finite and cannot be silently accepted.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Implement one bounded proposal round and machine-authority acceptance/rejection.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D013` — Work items bind source/context/candidate/evidence.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Populate source groups, output contracts, evidence requirements, and candidate digest in every packet.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `D014` — Static roadmap status cannot substitute for runtime state.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Create one authoritative runtime state store and derive dashboards from it.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Scheduler & recovery

#### `E003` — Task lease is renewed during long execution.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Add heartbeat/lease-renewal coroutine and ownership token; abort if renewal fails.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E004` — Expired work resumes from durable candidate/session state rather than restarting ambiguously.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Persist backend-neutral SessionRef and resume token; recover candidate worktree/checkpoint exactly.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E005` — Quota limits create QUOTA_WAIT and automatic resume.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Propagate typed quota/auth dispositions to scheduler, persist resume_at, and retry after reset.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E006` — Authentication expiry creates AUTH_EXPIRED wait and automatic recheck.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Add typed auth wait and credential refresh without exposing token.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E007` — Finite candidate repair cycles are actually executed.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement repair sessions, candidate preservation, exact findings, and rerun independent checks.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E008` — At most two re-specifications, then terminal disposition.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Implement bounded packet recompile with requirement digest and terminal NARROW/DEFER/REJECT/MACHINE_REVIEW.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E009` — Repeated identical findings trigger no-progress handling.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Hash normalized finding+candidate and stop after configured repeat threshold.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E010` — Factory self-repair is finite and does not rewrite product truth.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Route only controller defects to one bounded repair, with independent gate and no requirement changes.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E011` — Restart policy uses finite exponential backoff and HARD_STUCK.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Run kill-loop test and verify exact backoff/HARD_STUCK persistence.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E012` — Single-instance lock governs all launcher paths.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Test Windows scheduled task plus manual duplicate launch against same lock.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E014` — autonomy.enabled must be authoritative.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Refuse run when disabled unless an explicit one-shot simulation flag is used.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E015` — Runtime root may live outside repository safely.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Use URI/absolute runtime references and a safe display helper; route all state/worktrees/artifacts through runtime root.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E016` — Queue CLI/status and controller use the same queue root.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Centralize path resolution in one config object and regression-test every command.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `E017` — Interrupted mutating candidates are salvaged automatically.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Add crash-at-each-phase tests and automatic candidate transplant/quarantine behavior.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Backend & execution

#### `F002` — Claude is first backend, not durable state model.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Persist neutral session references and implement actual resume semantics.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F003` — Backend capability report is truthful.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Report resume=False until implemented, then add crash/restart tests before enabling.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F004` — Mutating roles receive Write/Edit only when authorized by work item.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Derive tools from mutability and allowed paths, not role string.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F006` — Role-specific network policy supports current research without broad network.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement allowlisted HTTPS source adapters for research/market/competitor lanes; keep product/trust default deny.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F007` — Finite wall-clock timeout is enforced.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Wrap stage query in cancellable timeout and persist typed TIMEOUT disposition.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F008` — Bash allowlist is enforced.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Gate commands at hook/controller boundary and reject undeclared executable/arguments.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F009` — Transcripts are redacted and retained by policy.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Store structured event summaries, redact prompt/source/private payloads, and enforce retention expiry.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F010` — Task packets name required outputs.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Generate stable output IDs/paths/schemas and fail if required outputs are missing.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F011` — Agent reports conform to a strict V3 schema.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Use versioned AgentExecutionReport with verdict, findings, owner, evidence, changed files, commands, limits, next action.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F012` — Candidate manifests preserve findings and external evidence.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Fan in validated role reports and external receipts; never drop non-pass evidence.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F013` — Handoffs are backend-neutral and durable.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Persist schema-versioned handoffs independent of transcript/session implementation.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F014` — Source path references in packets exist.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Use manifest-resolved source IDs; startup must reject any missing source before claiming a task.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F015` — Market lane can write account/interview/evidence artifacts.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Create lane-specific writable roots and task-specific output paths.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F016` — Competitor lane can write capability/source registers.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Authorize exact research output roots; protect normative docs from direct mutation.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F017` — Trust lane can write test/evidence artifacts but not authority.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Declare trust evidence paths and external verifier ownership.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F018` — Context routing is lane/task specific.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Add deterministic lane+task context selectors and tests preventing advisory/acquisition leakage.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `F019` — Current-fact freshness receipts are supplied.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Implement a source-retrieval service that records source URL/version/time/hash/control and passes receipt IDs.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Trust, value & release

#### `G002` — Observed boundary remains distinct from causal mechanism.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Maintain in first incident pack and independent oracle tests.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G005` — Machine policy approval is evaluated before release.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Make signed machine receipt a mandatory pre-release gate for all standard/integration/trust work.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G006` — Machine policy verifier is external and immutable to candidate agents.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Move verifier and private oracle out of repository/agent access; root-own it and sign receipts.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G007` — Receipt is scope-bound, expiring, attributable, and revocable.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Add policy_id/version, issuer key ID, allowed claims, work item, risk, candidate, expiry, nonce, revocation status, oracle identities.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G009` — Value/native disposition is applied to work-item maturity.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Run value evaluator after technical pass and before maturity/release transition.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G010` — Complete-substitute benchmark is a required promotion gate.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Create benchmark schema/executor and require evidence for native-advantage state.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G012` — Release does not put an unverified candidate on main.

- **Audit verdict:** `CONTRADICTS_BUNDLE`
- **Severity:** `CRITICAL`
- **Required remediation:** Use automated PR + required checks + merge queue/auto-merge; zero human involvement does not require direct-main push.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G013` — Server-side branch protection/required checks enforce release policy.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Enable branch protection/ruleset, required workflows, no force/deletion, and merge queue or equivalent.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G014` — Private gate is mandatory where risk requires it.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Fail closed when required private runner/receipt is absent; test with hidden mutations.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G016` — GPU validation is separate and truthful.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Do not elevate GPU maturity; require signed exact-SHA runner evidence when available.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `G018` — Green CI cannot certify policy that rewrites the requirements being audited.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Separate conformance tests from policy implementation; test against immutable V3.1-ZH manifest and external verifier.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Live autonomy & operations

#### `H001` — Controller is enabled and running only after migration gates pass.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Do not start until P0 defects are fixed; then run observation/canary and enable via signed activation receipt.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H002` — A real Claude-backed work item completes unattended.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Run a harmless mechanical canary with real Claude, exact artifacts, restart, and automatic next selection.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H003` — A live controller survives process kill and resumes the same work item.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `CRITICAL`
- **Required remediation:** Kill during planning, execution, gate, publication, and verify idempotent recovery each time.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H004` — A quota event pauses and resumes without human action.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement typed pause/resume and run injected plus real-reset canaries.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H005` — A failed CI release is contained before main.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Move to pre-merge required checks and test a deliberately failing candidate.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H006` — A repeated product defect stops finitely rather than loops.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Run deterministic repeated counterexample canary and verify terminal disposition.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H007` — A waiting external item does not stall product work.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Create concurrent lane fixture and live no-network canary.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H008` — Milestone advances automatically after evidence gates.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Implement and canary M1→M2 in a disposable roadmap.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H009` — Status shows authoritative milestone, lane, retry budget, blockers, candidate, CI, and release.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Unify runtime state and add stale/mismatch tests.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H010` — Portable Windows/WSL startup has no hardcoded personal paths.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Run install/start/status/stop in a fresh user/path and WSL distribution.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H013` — Automatic publication is idempotent across crash/restart.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Test crash before push, after push, during checks, before merge, after merge, and during rollback.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H014` — Supervisor preflight reads V3 queue/checkpoint/runtime locations.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Route preflight through the same V3 PathConfig and enumerate active leases/checkpoints.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H015` — Controller cannot operate when source integrity or machine authority is missing.

- **Audit verdict:** `DEFECT`
- **Severity:** `CRITICAL`
- **Required remediation:** Make both mandatory before claim/merge; refuse any publication without signed activation/policy receipt.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `H016` — Runtime events distinguish simulation, controlled validation, live validation, and external validation.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Add evidence_class enum and prevent lower classes from satisfying higher gates.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Product implementation

#### `I012` — Real GPU behavior is exact-SHA and environment-bound.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Add environment digest, runner identity, raw logs, and signed receipt when run.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

### Research & market lanes

#### `J001` — Reachable-account map is generated from attributable sources.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Fix lane execution; use public/company/contact sources and label uncertainty.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J002` — Interview guide and pilot qualification artifacts are created.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `MEDIUM`
- **Required remediation:** Declare and generate versioned artifacts with evidence/source boundaries.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J008` — Competitor/source register is current and freshness-bound.

- **Audit verdict:** `PARTIAL`
- **Severity:** `HIGH`
- **Required remediation:** Enable allowlisted adapters and scheduled source-monitor work items.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J009` — Teyon/Harbor/TrainCheck/TrainVerify/TTrace/Clockwork are tracked.

- **Audit verdict:** `PARTIAL`
- **Severity:** `MEDIUM`
- **Required remediation:** Add source-specific checks and last-verified timestamps.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J010` — TrainCheck differential is explicitly tested against incident-derived contracts.

- **Audit verdict:** `NOT_PROVEN`
- **Severity:** `HIGH`
- **Required remediation:** Create a controlled healthy-invariant versus incident-derived qualification comparison.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J011` — Trust lane independently attacks false green, identity, evidence, and release.

- **Audit verdict:** `PARTIAL`
- **Severity:** `CRITICAL`
- **Required remediation:** Use off-repo hidden verifier and real adversarial canaries.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.

#### `J012` — Research process distinguishes CLEAR/CONFLICT/UNKNOWN and preserves raw controls.

- **Audit verdict:** `DEFECT`
- **Severity:** `HIGH`
- **Required remediation:** Integrate V3 research tasks with preregistered query/evidence manifest policy.
- **Completion evidence required:** exact changed files, exact candidate SHA, deterministic test or live canary, artifact digest, and before/after matrix status.
