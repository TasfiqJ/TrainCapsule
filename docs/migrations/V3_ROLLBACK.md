# TrainCapsule V3 rollback

## Fixed rollback point

The pre-migration tracked tree is preserved by:

```text
safety/traincapsule-v3-pre-migration-20260811T212024Z
→ 6b480232fa92b069103da44c475bd17bcb3e6bd1
```

Runtime files remain in place and are not part of the Git rollback. Their baseline metadata and hashes are in `V3_RUNTIME_SNAPSHOT_METADATA.json`.

## Rollback procedure

1. Disable the Windows autopilot task and stop any V3 controller.
2. Preserve new V3 artifacts, logs, and any later user work outside the rollback operation.
3. Confirm the target safety ref resolves to the SHA above.
4. For unpublished changes, remove only migration-owned work after reviewing the diff.
5. For published migration commits, revert the migration commits on `main` in reverse order; never force-push or reset published history.
6. Verify the resulting tracked tree matches the safety ref for the intended paths.
7. Verify the V2 deterministic baseline tests.
8. Keep V2 queued work stopped; do not automatically resume T002.
9. Document the rollback cause before another migration attempt.

## Exact review and published-history commands

Review the complete migration delta without changing state:

```bash
git diff --stat safety/traincapsule-v3-pre-migration-20260811T212024Z..main
git log --oneline safety/traincapsule-v3-pre-migration-20260811T212024Z..main
tcfactory migrate-roadmap --from-v2 --dry-run
```

If the migration has been published, preserve later operator work and create ordinary revert commits
on `main`; never reset or force-push published history:

```bash
git switch main
git revert --no-commit safety/traincapsule-v3-pre-migration-20260811T212024Z..main
git status --short
# Review and test the exact revert, then commit and push main normally.
```

Before a tracked rollback, copy `factory/state/MIGRATION_COMPLETE_V3.json` and any new runtime logs or
artifacts to an operator-selected evidence directory. Keep `factory/state/STOP` present. The ignored
V2 queue archive is a non-resuming copy; the original T001/T002 queue files remain the recovery
authority.

## Disposable rehearsal

The final acceptance rehearsal uses a detached disposable worktree at the fixed safety ref, verifies
the historical authority and baseline suite there, and then removes only that explicitly created
worktree. The exact result is recorded in `V3_TEST_MATRIX.md`; it does not alter `main` or runtime
state.

## Rollback acceptance

- Source files match the intended baseline.
- Historical/runtime evidence remains available.
- No candidate branch or worktree was deleted.
- The controller remains stopped until an operator explicitly enables it.
- The baseline factory suite and authority gate pass.
