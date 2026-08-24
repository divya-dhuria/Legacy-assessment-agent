# F-03 — Persistence layer

**Depends on:** F-02
**Goal:** SQLite store with a transparent, migratable schema.

No ORM. No Alembic. The schema is a client-facing artifact — it must be readable by
someone who did not write it.

---

## `laa/store/db.py`

### Connection

Every connection sets:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

Row factory returns `sqlite3.Row`.

### Migration runner

- Migrations are `NNN_name.sql` in `laa/store/migrations/`, discovered and sorted numerically
- On connect: read `schema_version`; apply each migration with a higher number, in order,
  **each in its own transaction**, recording the version on success
- If the DB version exceeds the highest known migration, raise a clear error naming both
  versions. Do not open it.
- A fresh DB (no `schema_version` table) applies everything from 001

```python
def connect(db_path: Path) -> sqlite3.Connection: ...
def current_version(conn: sqlite3.Connection) -> int: ...
def migrate(conn: sqlite3.Connection) -> int: ...
```

---

## `laa/store/migrations/001_initial.sql`

All timestamps stored as ISO-8601 UTC text. Booleans as `INTEGER` 0/1. Lists as JSON text.

```sql
CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE engagement (
    engagement_id TEXT PRIMARY KEY,
    client_name   TEXT NOT NULL,
    system_name   TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    stack         TEXT NOT NULL,
    config_hash   TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE run (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    status       TEXT NOT NULL,
    config_hash  TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    git_sha      TEXT
);

CREATE TABLE stage_execution (
    run_id       TEXT NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    stage_name   TEXT NOT NULL,
    status       TEXT NOT NULL,
    started_at   TEXT,
    ended_at     TEXT,
    error        TEXT,
    items_total  INTEGER NOT NULL DEFAULT 0,
    items_done   INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, stage_name)
);

-- Item-level checkpointing. Without this, a failure at object 340 of 378
-- re-runs all 340.
CREATE TABLE stage_item (
    run_id     TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    item_key   TEXT NOT NULL,
    status     TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, stage_name, item_key),
    FOREIGN KEY (run_id, stage_name)
        REFERENCES stage_execution(run_id, stage_name) ON DELETE CASCADE
);

-- Evidence behind §2.2 of the deliverable. Every coverage figure the report
-- publishes is bounded by what this records.
CREATE TABLE access_probe (
    run_id                TEXT PRIMARY KEY REFERENCES run(run_id) ON DELETE CASCADE,
    account_name          TEXT NOT NULL,
    has_dba               INTEGER NOT NULL,
    has_select_catalog    INTEGER NOT NULL,
    readable_views        TEXT NOT NULL,   -- JSON object: view -> bool
    db_version            TEXT,
    nls_characterset      TEXT,
    schemas_requested     INTEGER NOT NULL,
    schemas_visible       INTEGER NOT NULL,
    objects_visible       INTEGER NOT NULL,
    objects_inferred_only INTEGER NOT NULL,
    probed_at             TEXT NOT NULL
);

CREATE TABLE source_object (
    object_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_name      TEXT NOT NULL,
    object_name      TEXT NOT NULL,
    object_type      TEXT NOT NULL,
    visibility       TEXT NOT NULL,
    inferred_from    TEXT,
    line_count       INTEGER,
    source_available INTEGER NOT NULL DEFAULT 0,
    status           TEXT,
    module           TEXT,
    content_hash     TEXT,
    UNIQUE (schema_name, object_name, object_type)
);

CREATE INDEX idx_source_object_module     ON source_object(module);
CREATE INDEX idx_source_object_visibility ON source_object(visibility);

CREATE TABLE rule (
    rule_id            TEXT PRIMARY KEY,
    natural_key        TEXT NOT NULL,
    object_id          INTEGER REFERENCES source_object(object_id),
    statement          TEXT NOT NULL,
    original_statement TEXT NOT NULL,
    rule_type          TEXT NOT NULL,
    module             TEXT NOT NULL,
    schema_name        TEXT NOT NULL,
    source_object      TEXT NOT NULL,
    source_unit        TEXT,
    line_start         INTEGER NOT NULL,
    line_end           INTEGER NOT NULL,
    source_hash        TEXT NOT NULL,
    data_elements      TEXT NOT NULL DEFAULT '[]',
    confidence         TEXT NOT NULL,
    extraction_run_id  TEXT NOT NULL,
    model_id           TEXT NOT NULL,
    review_state       TEXT NOT NULL DEFAULT 'pending',
    reviewer           TEXT,
    reviewed_at        TEXT,
    reviewer_note      TEXT,
    is_stale           INTEGER NOT NULL DEFAULT 0,
    duplicate_of       TEXT REFERENCES rule(rule_id)
);

CREATE INDEX idx_rule_module       ON rule(module);
CREATE INDEX idx_rule_review_state ON rule(review_state);
CREATE INDEX idx_rule_confidence   ON rule(confidence);
CREATE INDEX idx_rule_object       ON rule(source_object);
CREATE UNIQUE INDEX idx_rule_natkey ON rule(natural_key, source_object);

-- Append-only. The audit trail behind the report's claim that every rule was
-- reviewed by a named engineer. duration_ms feeds the review-hours metric.
CREATE TABLE review_event (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     TEXT NOT NULL REFERENCES rule(rule_id) ON DELETE CASCADE,
    from_state  TEXT NOT NULL,
    to_state    TEXT NOT NULL,
    reviewer    TEXT NOT NULL,
    note        TEXT,
    occurred_at TEXT NOT NULL,
    duration_ms INTEGER
);

CREATE INDEX idx_review_event_rule ON review_event(rule_id);

CREATE TABLE cost_event (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    stage_name    TEXT NOT NULL,
    item_key      TEXT,
    model_id      TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd      REAL NOT NULL,
    occurred_at   TEXT NOT NULL
);

CREATE INDEX idx_cost_event_run ON cost_event(run_id, stage_name);
```

`object_id` on `rule` is nullable: rules arrive in Epic 3, objects in Epic 1, and a
nullable FK avoids ordering constraints while preserving integrity where the link exists.
`schema_name` and `source_object` are denormalized onto `rule` deliberately — the register
export must be readable standalone.

---

## `laa/store/repositories.py`

Pydantic models in and out. No `sqlite3.Row` escapes this layer.

```python
class RunRepo:
    def create(self, run: Run) -> None: ...
    def finish(self, run_id: str, status: RunStatus) -> None: ...
    def latest(self) -> Run | None: ...

class StageRepo:
    def upsert_execution(self, ...) -> None: ...
    def get_execution(self, run_id: str, stage: str) -> StageExecution | None: ...
    def mark_item(self, run_id: str, stage: str, item_key: str,
                  status: ItemStatus, error: str | None = None) -> None: ...
    def pending_items(self, run_id: str, stage: str,
                      all_keys: list[str]) -> list[str]: ...

class SourceRepo:
    def upsert(self, obj: SourceObject) -> int: ...
    def by_visibility(self, v: Visibility) -> list[SourceObject]: ...

class RuleRepo:
    def upsert_extraction(self, candidate: Rule) -> Rule: ...
    def disposition(self, rule_id: str, to_state: ReviewState, reviewer: str,
                    statement: str | None, note: str | None,
                    duration_ms: int | None) -> Rule: ...
    def by_module(self, module: str) -> list[Rule]: ...
    def counts_by_state(self) -> dict[ReviewState, int]: ...

class CostRepo:
    def record(self, event: CostEvent) -> None: ...
    def total_usd(self, run_id: str) -> float: ...
```

### Two methods that must be transactional

**`upsert_extraction`** — loads existing rules for the object, applies
`match_existing` and `merge_extraction` from F-02, allocates a new ID only on no match,
writes. All in one transaction.

**`disposition`** — writes the `rule` update **and** the `review_event` row in a single
transaction. These must never diverge: the rule's current state and its audit trail are
the same fact recorded twice.

---

## Acceptance

- [ ] Fresh DB applies all migrations, reports correct version
- [ ] Re-opening applies nothing, does not error
- [ ] A DB with a version above the highest known migration raises a clear error
- [ ] `disposition()` writes rule and event together, and rolls back both on failure
- [ ] Every repo round-trips all fields, including JSON columns and timezone-aware datetimes
- [ ] `upsert_extraction()` passes the same stability tests as F-02: reused `rule_id`,
      preserved review state, `is_stale` set only on source change
- [ ] `source_object` round-trips all three `Visibility` states
- [ ] An `INFERRED_ONLY` row persists without `line_count` or `content_hash`
- [ ] `pending_items` returns only keys not already `DONE` for that run and stage

## Tests

Use `tmp_path` fixtures. No shared DB between tests. No Oracle.

## Out of scope

No CLI wiring, no config loading, no pipeline.
