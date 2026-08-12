# TrainCapsule V3 execution state

- Starting SHA: `6b480232fa92b069103da44c475bd17bcb3e6bd1`
- Working/publication branch: `main` only
- Accepted implementation SHA: `f1fd8077fee001fa6751aa86b26f341f04d0d150`
- Safety ref: `safety/traincapsule-v3-pre-migration-20260811T212024Z`
- Bundle integrity: 30/30 declared files, 542907/542907 bytes, every declared SHA-256 matched
- Completed milestone: `M0_FACTORY_MIGRATED`, proven by the five tracked acceptance receipts under
  `docs/migrations/evidence/`; active engineering milestone: `M1_NATIVE_PREFLIGHT`
- Controller: safely stopped while the final runtime-path repair is published; Windows task
  disabled; durable `STOP` and `PAUSE` present
- Owner deviations: zero-human execution and exact-SHA main-only publication; non-main pushes and pull requests are forbidden
- External truth: GPU, customer, operator, payment, repeat-use, and commercial-support facts remain UNKNOWN or `WAITING_EXTERNAL`
- Current local proof: 555 tests pass, Ruff passes, strict Pyright reports 0 errors and 0 warnings,
  all generators/gates pass, and the clean independent-wheel installation journey passes
- Publication proof: `origin/main` resolved to the accepted implementation SHA and all eight required
  workflows passed at that exact SHA: Factory quality `31563636477`, Product unit `31563636487`,
  Product contract `31563636485`, Security `31563636472`, Source-of-truth integrity
  `31563636497`, Packaging install `31563636469`, Docs and schemas `31563636505`, and
  Source freshness `31563636499`
- GitHub-hosted jobs were initially blocked before runner assignment by the private account's
  billing/spending state. The repository used the already-provisioned online
  `traincapsule-wsl-local` runner through `TRAINCAPSULE_CI_RUNNER`; the workflows retain
  `ubuntu-latest` as their declared fallback. No new paid runner or model usage was created.
- Network use was limited to GitHub fetch/push, workflow verification, and existing package tooling;
  no model call, GPU run, paid API, customer action, or commercial claim was made
- Runtime preflight with the actual launcher environment now returns `ready: true` and
  `credentials: AUTHENTICATED`. The earlier `AUTH_EXPIRED` was a PATH/configuration false negative,
  not an expired Max subscription: the installed Claude CLI reports first-party `claude.ai` Max.
  Two V2-only environment overrides were removed, and private-gate discovery now uses its fixed
  controller-owned out-of-repository path. After this repair is exact-SHA hosted-green, remove
  `STOP`/`PAUSE`, enable the task, and observe one bounded V3 controller cycle.

## Rollback

Keep the controller stopped and preserve runtime files. Compare tracked changes with
`safety/traincapsule-v3-pre-migration-20260811T212024Z`. After publication, use ordinary `git revert`
commits on `main`; never force-push or rewrite published history. T002 remains preserved and paused.

The implementation acceptance SHA and exact hosted run identifiers above are immutable evidence.
Any later documentation-only handoff commit must independently pass the same required workflow set.
