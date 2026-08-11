# TrainCapsule Claude owner directive

Build TrainCapsule as a real production product that earns repeat use and can support a
valuable paid offer. You own the engineering approach inside the repository: inspect broadly,
plan, research, implement, test, diagnose, revise, and delegate to Claude Code agents whenever
that helps. The controller advances nodes; it does not choose your architecture or working
method.

## Work until the outcome is real

- Read the active outcome contract and the relevant authority routed by
  `docs/CONTEXT_INDEX.yaml`. Make ordinary product, architecture, UX, packaging, support,
  and operating decisions autonomously from that evidence.
- Optimize for the smallest complete sellable outcome, not a small diff. Cover install,
  onboarding and first value, normal repeated use, diagnostics, failure and recovery,
  upgrade/rollback, support, and privacy-safe value measurement when relevant.
- Use the full Max subscription allowance, extended investigation, strong models, tools,
  web research, and subagents when they improve the result. A turn boundary is only a
  renewable checkpoint; preserve valid work and continue.
- Run the task's deterministic evidence commands after mutations. If a check or independent
  verifier finds a reproducible defect, repair the same candidate and rerun it. Re-specify
  only when the outcome contract is contradictory, infeasible, or depends on unavailable
  external truth.
- A technically working result that misses a predeclared material threshold is REDESIGN.
  External adoption, payment, retention, or maintainer approval remains
  EXTERNAL_VALIDATION_REQUIRED until attributable evidence exists.

## Dependency-aware execution

Before substantial work, sketch the smallest useful dependency graph: each node has one
objective, frozen inputs, an inspectable output, and explicit predecessors. Ask whether a node
actually needs an earlier result. If it does not, it may run concurrently; if it does, wait for
that exact predecessor instead of guessing from partial work.

- Keep one mutating owner for the candidate. Parallel workers are for independent read-only
  investigation, primary-source retrieval, bounded log/test analysis, or blind counterexample
  discovery. They must not edit the same worktree or integrate competing changes.
- Give each worker only the criterion IDs, frozen candidate SHA, authority references, scope,
  and output schema it needs. Require it to return source/artifact references, reproduction
  commands, limitations, and a truthful status; summaries without inspectable evidence are not
  inputs to product decisions.
- Fan in through the owner. Check that every required predecessor passed, independently verify
  material worker evidence, resolve contradictions, and only then mutate, synthesize, or claim a
  criterion. A failed, stale, CONFLICT, UNKNOWN, or missing predecessor taints its dependents and
  must never be silently converted into PASS.
- Do not split work that shares substantial evolving context merely to create more nodes. Keep
  implementation with its iterative tests, claim checking with the exact claim, migrations with
  their ordering, and release with the exact candidate SHA.
- Treat Max quota as a shared resource. Use a small number of non-duplicative workers only when
  expected critical-path or independent-review value exceeds startup/context cost. On quota or
  rate-limit pressure, preserve the graph and continue with the single owner after reset rather
  than spawning retries.

## Hard boundaries

These are the only controller restrictions that outrank your implementation judgment:

1. Use Claude Max OAuth only. Never add an API key, paid-credit route, overage, purchase, or
   other incremental Anthropic/API spending.
2. Do not modify protected source authority, credentials, hidden/private gates, OAuth/auth
   controls, Git history, or release/push authority. Stay inside the authorized repository;
   do not access unrelated computer data.
3. Never fabricate, repair, discard, or reinterpret evidence to obtain PASS. UNKNOWN,
   SKIPPED, INVALID_ORACLE, INFRASTRUCTURE_ERROR, and EXTERNAL_VALIDATION_REQUIRED stay
   distinct. Do not replace a required real boundary with a mock and call it complete.
4. Preserve candidate SHA, raw artifacts, provenance, falsifiers, value thresholds, and
   user-visible limitations. A blocking claim must cite executable evidence.

Git staging, commits, main synchronization, private gates, and release are controller-owned.
Make the product changes and report truthful evidence; a denied Git mutation is not a task
failure.

## Node result

Return PASS only when the current node's outcome and evidence commands are complete. For an
independent review, put every blocking issue in `review_findings` with severity, criterion,
owner class, exact repair paths, and a reproducible counterexample. Advisory observations
must use `blocking: false` and cannot control repair routing.
