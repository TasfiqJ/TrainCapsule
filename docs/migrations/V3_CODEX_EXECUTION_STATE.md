# TrainCapsule V3 execution state

- Starting SHA: `6b480232fa92b069103da44c475bd17bcb3e6bd1`
- Working/publication branch: `main` only
- Current pre-publication parent: `4b3cd93a8884846d82fa3eeeb4471bdcc3036264`
- Safety ref: `safety/traincapsule-v3-pre-migration-20260811T212024Z`
- Bundle integrity: 30/30 declared files, 542907/542907 bytes, every declared SHA-256 matched
- Completed milestone: `M0_FACTORY_MIGRATED`, proven by the five tracked acceptance receipts under
  `docs/migrations/evidence/`; active engineering milestone: `M1_NATIVE_PREFLIGHT`
- Controller: intentionally stopped; Windows task disabled; durable `STOP` and `PAUSE` preserved until final publication and exact-SHA marker creation
- Owner deviations: zero-human execution and exact-SHA main-only publication; non-main pushes and pull requests are forbidden
- External truth: GPU, customer, operator, payment, repeat-use, and commercial-support facts remain UNKNOWN or `WAITING_EXTERNAL`
- Current local proof: 552 tests pass, Ruff passes, strict Pyright reports 0 errors and 0 warnings,
  all generators/gates pass, and the clean independent-wheel installation journey passes
- Model/network/paid use during migration verification: none
- Next action: regenerate exact inventories, run final clean-install and gate matrix, commit to `main`, create the ignored exact-SHA marker, push only that SHA to `origin/main`, verify hosted workflows, then remove runtime stops and observe the real V3 controller

## Rollback

Keep the controller stopped and preserve runtime files. Compare tracked changes with
`safety/traincapsule-v3-pre-migration-20260811T212024Z`. After publication, use ordinary `git revert`
commits on `main`; never force-push or rewrite published history. T002 remains preserved and paused.

No old commit list is treated as acceptance evidence for this final tree. The exact final commit and
hosted results are recorded only after publication succeeds.
