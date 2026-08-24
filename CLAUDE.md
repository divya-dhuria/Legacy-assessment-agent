# Legacy Assessment Agent

Internal delivery accelerator. Produces fixed-fee legacy system assessments for
modernization engagements. Target stack for V0 is **Oracle PL/SQL**, developed against Oracle 23ai Free in Docker (no licence cost).

The output is a client-facing report where **every business rule is traceable to a
source line and dispositioned by a named human reviewer**. Provenance and review are
not features — they are what makes the deliverable saleable.

## Non-negotiable constraints

1. **Deterministic before probabilistic.** Object inventory, dependency graph, data
   model, and call paths come from the Oracle catalogue and the parser. Never from a
   model. If a fact could be derived deterministically, it must be.
2. **No rule ships unreviewed.** Every rule carries a review state, a named reviewer,
   and a timestamp. A rule that has not been dispositioned by a human never appears in
   a client deliverable.
3. **Provenance is mandatory.** Every rule cites `source_object`, `source_unit`, and a
   line range. Citations are validated against actual source, not trusted.
4. **Never report a count as a total when it is a floor.** What the supplied database
   credentials could see bounds every figure in the deliverable. An object that is known
   to exist but was not readable must be recorded as such, never omitted. Silently
   under-counting is the worst failure mode this tool has.
5. **Everything is resumable.** Runs process hundreds of objects and will fail partway.
   Stage-level and item-level checkpointing is required, not optional.
6. **Instrument from the start.** Token cost and human review time are the metrics that
   determine whether this accelerator is economic. Capture them from commit one.

## Tech decisions (settled — do not relitigate)

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Packaging | `uv` + `pyproject.toml` |
| CLI | Typer |
| Config | Pydantic v2 models, YAML source |
| Logging | `structlog`, JSON to file + human-readable console |
| Persistence | SQLite via stdlib `sqlite3`, one DB file per engagement |
| Migrations | Numbered `.sql` files + `schema_version` table. **No ORM, no Alembic.** |
| Domain models | Pydantic v2, thin repository layer over raw SQL |
| Testing | `pytest` |
| Lint / format | `ruff` |
| Types | `mypy`, strict on `laa/domain` and `laa/store` |

Rationale for raw SQL over an ORM: the schema *is* the product. It needs to be readable
by someone who did not write it, and exportable to a client without translation.

## Layout

```
laa/
  cli.py                    Typer entrypoint
  logging.py                structlog configuration
  config/
    models.py               EngagementConfig and friends
    loader.py               YAML load, validate, hash
  domain/
    enums.py                RuleType, Confidence, ReviewState, StageStatus
    rule.py                 Rule model
    source.py               SourceObject, SourceUnit
    ids.py                  Rule ID assignment and natural-key matching
  store/
    db.py                   Connection, migration runner
    migrations/
      001_initial.sql
    repositories.py         RuleRepo, RunRepo, SourceRepo
  runner/
    pipeline.py             Stage registry, dependency resolution
    stage.py                Stage protocol, checkpointing
    context.py              RunContext
tests/
engagements/                Gitignored. One directory per engagement.
```

## Working conventions

- Engagement data lives in `engagements/<engagement_id>/` — never in the repo.
  This directory is gitignored and may contain client source. Treat it as confidential.
- All timestamps UTC, ISO 8601.
- Log lines always carry `engagement_id`, `run_id`, `stage`.
- Any function that touches client source must accept a path, never a hardcoded location.
- Tests must not require a live Oracle connection. Fixtures only.

## Current state

Epic 0 (Foundations) in progress. See `docs/epic-0-foundations.md`.
Epics 1–6 not started. Full backlog in `docs/v0-backlog.md`.
