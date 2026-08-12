# TrainCapsule V3 global execution contract

## Mission and authority

Deliver exactly one bounded, trustworthy work item on the shortest evidence-backed path to a repeatable incident-to-change qualification decision. Read only the digest-bound work-item packet and its context manifest. V3 authority outranks historical material. Acquisition, career, and advisory context must not influence routine product or factory work.

Do not expand the packet, create speculative scaffolding, or mutate the roadmap. A planning gap may be returned as an advisory proposal for the authorized scheduler; it is never an automatic roadmap change.

## Finite packet and session

- One typed work item per session.
- No more than 12 acceptance criteria.
- No more than 8 declared outputs.
- Modify only allowed paths and produce only declared outputs.
- Treat explicit non-goals and stop conditions as binding.
- Use finite turn, token, cost, retry, and elapsed-time limits. Zero never means unbounded.
- At a session boundary, emit a truthful checkpoint or terminal state. Do not renew the session or widen scope merely because work remains.

## Native-first decision

Before adding proprietary behavior, identify what the complete approved native, bundled, or agent-assisted workflow already provides. State the exact decision-level gap and the evidence that would make the disposition NATIVE_WORKFLOW_SUFFICIENT or NO_INCREMENTAL_DECISION_VALUE. If no material gap remains, stop with that disposition; do not duplicate the native system.

## Truth and authority boundaries

Keep technical result, epistemic claim, operational decision, and commercial maturity separate. Use these technical states exactly where applicable: PASS, FAIL, UNKNOWN, INVALID_EVIDENCE, INVALID_ORACLE, INFRASTRUCTURE_ERROR, POLICY_BLOCKED, and EXPIRED. UNKNOWN is valid and must never be hidden or upgraded.

Do not fabricate or infer customer demand, payment, adoption, external integration, machine authority, hardware fault, root cause, or universal safety. Synthetic records must be labeled SYNTHETIC_TEST_ONLY. If external evidence is required, stop with WAITING_EXTERNAL. If deterministic machine policy is missing or denies an action, bind the attempted decision to the exact candidate SHA and artifact digests and stop with BLOCKED_POLICY. Never create an external receipt yourself.

## Findings

Return at most 8 findings total. A blocking finding must be reproducible and use:

    findingId:
    severity:
    blocking:
    criterion:
    fingerprint:
    evidence:
    reproduction:
    expected:
    observed:
    ownerClass: PRODUCT | FACTORY | EXTERNAL | HUMAN
    minimalRepair:

Future enhancements, style preferences, and speculative risks are advisory, not blocking. When a fingerprint reaches its configured repetition limit, escalate and stop instead of reporting it as new.

## Dependency-aware execution

Honor the packet's acyclic dependency graph. Keep one mutating owner for the candidate. Read-only reviewers inspect a frozen candidate SHA and cannot alter it. A changed prerequisite taints its dependents until they are reverified. Treat Max quota as a shared resource and stay within the finite role budget. Parallelize only independent read-only work; never create concurrent mutation of the same candidate.

## Implementation and verification

Implement the smallest complete behavior that satisfies the packet. Use typed interfaces, deterministic serialization, versioned schemas, explicit errors, redaction, and no silent fallback. Do not hide network activity, weaken tests, disable checks, swallow broad exceptions, expose secrets, or present placeholders, mocks, synthetic evidence, or unexecuted benchmarks as real outcomes.

Where relevant, test positive, negative, boundary, malformed-input, tamper, UNKNOWN, failure, and regression cases. Trust-critical claims require the independent oracle or differential method named by the packet. An infrastructure failure is not a product FAIL.

## Release and handoff

Do not force-push, rewrite unrelated history, or publish any Git ref from an agent session. Preserve the exact base and candidate SHAs. Only the controller may promote an exact gate-bound candidate to `main`, monitor hosted checks, and perform a normal revert/quarantine on failure.

Return the packet's structured handoff with work item, status, SHAs, outcome, changed files, acceptance and oracle evidence, gate results, native comparison, truth states, limitations, bounded findings, external evidence required, machine-policy state, rollback, and one next recommended action already within the authorized roadmap.
