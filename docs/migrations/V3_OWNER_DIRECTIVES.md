# V3 owner directives and explicit authority deviations

These repository-owner directives are later and more specific than the supplied V3 migration
bundle. They control the executable factory even where they conflict with that bundle.

## Unattended operation

The TrainCapsule factory must operate with zero human intervention. No reachable controller,
scheduler, recovery, release, approval, or completion state may require a person to resume normal
operation. Missing customer, GPU, market, or other external evidence remains `UNKNOWN` or a
scope-local external wait. It is never fabricated, and it must not stop unrelated lanes.

Machine-verifiable policy receipts and deterministic gates replace the bundle's qualified-human
approval records. This is an explicit owner override of the human-authority clauses; it is not
represented as compliance with those clauses.

## Main-only publication

The autonomous factory may push only `main`. It must not push candidate or release branches and
must not depend on pull-request creation, review, readiness, or merge. This explicitly overrides
the bundle's PR-first release policy.

Before promotion, the factory must bind all gate evidence to the exact candidate SHA and pass every
configured deterministic local and private gate. After pushing `main`, it must monitor required
hosted checks. A failed hosted result must automatically quarantine the candidate and create and
push a normal revert commit to `main`; history rewriting and force-pushes are forbidden. Retries
and recovery remain finite and circuit-breaker protected.

The machine-readable authority record is `config/owner_directives.yaml`.
