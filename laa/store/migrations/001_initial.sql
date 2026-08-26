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
