## F-01 — Repo scaffold, CLI, logging
Completed: 2026-08-23
Deviations from spec:
1. The task's `laa/cli.py` code sample shows `engagement: str` as a bare parameter,
   which Typer would expose as a positional argument. The acceptance criteria
   explicitly require `laa status --engagement demo`, so `engagement` (and the other
   command parameters) are declared as explicit `typer.Option`s instead of bare
   parameters. Behavior matches the acceptance criteria; only the Typer wiring differs
   from the literal sample.
2. The directory tree lists `engagements/.gitkeep` under this task, but the task's own
   closing note says F-01 creates the repo structure once and F-04's `scaffold()`
   creates `engagements/<id>/` at runtime. Read literally, `engagements/` is gitignored
   and not pre-created — its own `.gitkeep` couldn't be committed under that ignore
   rule anyway (`!engagements/.gitkeep` does not un-ignore a file inside a fully
   ignored parent directory). Followed the closing note: `.gitignore` excludes
   `engagements/`, but the directory itself is left for F-04 to create at runtime.
Follow-ups raised: none

## F-02 — Rule record schema
Completed: 2026-08-24
Deviations from spec: none. Two implementation-detail choices not fully pinned down
by the spec text, applied consistently:
1. "the rule was reviewed" (for `merge_extraction`'s statement/original_statement
   handling) is read as `matched.review_state != ReviewState.PENDING`.
2. `is_stale` is fully recomputed on every merge (`True` iff `source_hash` differs,
   `False` otherwise) rather than a one-way flag that only ever turns `True`.
Follow-ups raised: none
