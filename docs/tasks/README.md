# Epic 0 — Foundations

Place these in `docs/tasks/`. `CLAUDE.md` goes at the repo root.

## Workflow

**One task per Claude Code session.** Each file is self-contained. Read `CLAUDE.md`
first, then the task file, then implement.

Do not start the next task while the previous one has failing tests.

## Order

| Task | File | Depends on |
|---|---|---|
| F-01 | `F-01-scaffold.md` | — |
| F-02 | `F-02-rule-schema.md` | F-01 |
| F-03 | `F-03-persistence.md` | F-02 |
| F-04 | `F-04-engagement-config.md` | F-01, F-03 |
| F-05 | `F-05-run-harness.md` | F-03, F-04 |

F-02 before F-03 is deliberate: the domain model defines the schema, not the reverse.

## Progress

Maintain `docs/tasks/PROGRESS.md`. After completing a task, append:

```
## F-0X — <title>
Completed: <date>
Deviations from spec: <none | description and reason>
Follow-ups raised: <none | list>
```

If a spec is wrong or ambiguous, **stop and flag it** rather than guessing. These
documents encode decisions taken deliberately; silent deviation is worse than a blocked
task.

## Epic 0 done when

- [ ] `laa init` → `laa run` → `laa status` works end-to-end against the `noop` stage
- [ ] Rule schema implemented, validated, stability-tested under re-run
- [ ] SQLite schema applies clean and re-opens without error
- [ ] Resume works after a forced mid-stage kill
- [ ] `ruff check`, `mypy laa/`, `pytest` all clean
- [ ] `CLAUDE.md` "Current state" updated

## Out of scope for the whole epic

No Oracle connection, no parsing, no model calls, no review UI, no report generation.
If a task appears to require any of these, the task is wrong — stop and flag it.
