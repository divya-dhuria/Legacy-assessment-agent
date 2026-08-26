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

## F-03 — Persistence layer
Completed: 2026-08-24
Deviations from spec, both discussed and agreed before implementation:
1. `Run`, `StageExecution`, `CostEvent` — referenced by `RunRepo`/`StageRepo`/`CostRepo`'s
   given signatures but never defined anywhere in F-01's directory tree or F-02's domain
   models. Defined as plain Pydantic models local to `laa/store/repositories.py` rather
   than under `laa/domain/`: they're pipeline-execution bookkeeping (the runner's
   concern, formalized in F-05 — `Run` in particular overlaps conceptually with
   `RunContext`), not the business-rule domain F-02 scoped `domain/` to, and F-01's tree
   was deliberately exhaustive about what belongs in `domain/`.
2. `RuleRepo.upsert_extraction`'s given signature is `(candidate: Rule) -> Rule`, but it
   must call F-02's `next_rule_id(module_prefix, existing_ids)` to allocate an ID on no
   match, and nothing anywhere defines a `Rule.module` -> `module_prefix` mapping.
   Changed the signature to `upsert_extraction(candidate: Rule, module_prefix: str) ->
   Rule` — an explicit, caller-supplied prefix rather than a derived guess, since ID
   allocation is exactly the kind of decision the task itself warns must be deliberate.
Implementation-detail choices not fully pinned down by the spec text, applied
consistently:
3. `StageExecution.status` reuses `RunStatus` (pending/running/completed/failed/halted)
   rather than a new enum — CLAUDE.md's original layout sketch mentions a `StageStatus`
   that F-02 didn't end up implementing, and stage-level states are the same shape as
   run-level ones.
4. `rule.object_id` is always written as `NULL` by `RuleRepo`. The domain `Rule` model
   has no `object_id` field to supply one (see the spec's own note: "rules arrive in
   Epic 3, objects in Epic 1"), so there's nothing to link yet; backfilling it is later
   epics' job.
5. `RuleRepo.disposition`'s `reviewer_note` is set directly to the `note` argument
   (including clearing it to `NULL` if `note=None`) rather than preserving the prior
   note when omitted — each disposition call is treated as fully specifying the current
   review annotation, distinct from `statement`, which *is* left unchanged when omitted
   because editing wording is a separate action from just changing review state.
6. `SourceRepo.upsert` reads back `object_id` via a follow-up `SELECT` after the
   `INSERT ... ON CONFLICT`, rather than using SQLite's `RETURNING` clause — avoids
   depending on a minimum bundled-SQLite version (`RETURNING` needs 3.35+) across
   whatever Python 3.11+ build eventually runs this.
7. Migration files are split into statements with a plain `;`-split rather than a real
   SQL parser or `executescript` — safe because migrations are authored in-repo with no
   semicolons inside string/comment content, and avoids `executescript`'s implicit
   auto-commit-before-run semantics interfering with wrapping each migration in its own
   explicit transaction.
Follow-ups raised: none
