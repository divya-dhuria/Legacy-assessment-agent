"""Pydantic models in and out. No `sqlite3.Row` escapes this layer.

`Run`, `StageExecution`, and `CostEvent` are defined here rather than in
`laa.domain` — they are pipeline-execution bookkeeping (the runner's
concern, formalized in F-05), not the business-rule domain F-02 scoped that
package to. Keeping them local to the layer that persists them keeps the
footprint small and easy to move later if F-05 wants to share them.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from laa.domain.enums import Confidence, ItemStatus, ReviewState, RuleType, RunStatus, Visibility
from laa.domain.ids import match_existing, merge_extraction, next_rule_id
from laa.domain.rule import Rule
from laa.domain.source import SourceObject


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value


def _to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _from_text(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class Run(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    run_id: str
    started_at: datetime
    ended_at: datetime | None = None
    status: RunStatus
    config_hash: str
    tool_version: str
    git_sha: str | None = None

    @field_validator("started_at", "ended_at")
    @classmethod
    def _timestamps_utc(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value)


class StageExecution(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    run_id: str
    stage_name: str
    status: RunStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error: str | None = None
    items_total: int = 0
    items_done: int = 0
    items_failed: int = 0

    @field_validator("started_at", "ended_at")
    @classmethod
    def _timestamps_utc(cls, value: datetime | None) -> datetime | None:
        return _ensure_utc(value)


class CostEvent(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    event_id: int | None = None
    run_id: str
    stage_name: str
    item_key: str | None = None
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def _timestamp_utc(cls, value: datetime) -> datetime:
        result = _ensure_utc(value)
        assert result is not None
        return result


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        run_id=row["run_id"],
        started_at=_from_text(row["started_at"]),  # type: ignore[arg-type]
        ended_at=_from_text(row["ended_at"]),
        status=RunStatus(row["status"]),
        config_hash=row["config_hash"],
        tool_version=row["tool_version"],
        git_sha=row["git_sha"],
    )


def _row_to_stage_execution(row: sqlite3.Row) -> StageExecution:
    return StageExecution(
        run_id=row["run_id"],
        stage_name=row["stage_name"],
        status=RunStatus(row["status"]),
        started_at=_from_text(row["started_at"]),
        ended_at=_from_text(row["ended_at"]),
        error=row["error"],
        items_total=row["items_total"],
        items_done=row["items_done"],
        items_failed=row["items_failed"],
    )


def _row_to_source_object(row: sqlite3.Row) -> SourceObject:
    return SourceObject(
        schema_name=row["schema_name"],
        object_name=row["object_name"],
        object_type=row["object_type"],
        visibility=Visibility(row["visibility"]),
        inferred_from=row["inferred_from"],
        line_count=row["line_count"],
        source_available=bool(row["source_available"]),
        status=row["status"],
        module=row["module"],
        content_hash=row["content_hash"],
    )


def _row_to_rule(row: sqlite3.Row) -> Rule:
    return Rule(
        rule_id=row["rule_id"],
        natural_key=row["natural_key"],
        statement=row["statement"],
        original_statement=row["original_statement"],
        rule_type=RuleType(row["rule_type"]),
        module=row["module"],
        schema_name=row["schema_name"],
        source_object=row["source_object"],
        source_unit=row["source_unit"],
        line_start=row["line_start"],
        line_end=row["line_end"],
        source_hash=row["source_hash"],
        data_elements=json.loads(row["data_elements"]),
        confidence=Confidence(row["confidence"]),
        extraction_run_id=row["extraction_run_id"],
        model_id=row["model_id"],
        review_state=ReviewState(row["review_state"]),
        reviewer=row["reviewer"],
        reviewed_at=_from_text(row["reviewed_at"]),
        reviewer_note=row["reviewer_note"],
        is_stale=bool(row["is_stale"]),
        duplicate_of=row["duplicate_of"],
    )


class RunRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, run: Run) -> None:
        self._conn.execute(
            """
            INSERT INTO run (run_id, started_at, ended_at, status, config_hash,
                              tool_version, git_sha)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                _to_text(run.started_at),
                _to_text(run.ended_at),
                run.status.value,
                run.config_hash,
                run.tool_version,
                run.git_sha,
            ),
        )

    def finish(self, run_id: str, status: RunStatus) -> None:
        self._conn.execute(
            "UPDATE run SET status = ?, ended_at = ? WHERE run_id = ?",
            (status.value, _utc_now_text(), run_id),
        )

    def latest(self) -> Run | None:
        row = self._conn.execute("SELECT * FROM run ORDER BY started_at DESC LIMIT 1").fetchone()
        return _row_to_run(row) if row is not None else None


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat()


class StageRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert_execution(
        self,
        run_id: str,
        stage_name: str,
        status: RunStatus,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        error: str | None = None,
        items_total: int = 0,
        items_done: int = 0,
        items_failed: int = 0,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO stage_execution
                (run_id, stage_name, status, started_at, ended_at, error,
                 items_total, items_done, items_failed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (run_id, stage_name) DO UPDATE SET
                status = excluded.status,
                started_at = excluded.started_at,
                ended_at = excluded.ended_at,
                error = excluded.error,
                items_total = excluded.items_total,
                items_done = excluded.items_done,
                items_failed = excluded.items_failed
            """,
            (
                run_id,
                stage_name,
                status.value,
                _to_text(started_at),
                _to_text(ended_at),
                error,
                items_total,
                items_done,
                items_failed,
            ),
        )

    def get_execution(self, run_id: str, stage: str) -> StageExecution | None:
        row = self._conn.execute(
            "SELECT * FROM stage_execution WHERE run_id = ? AND stage_name = ?",
            (run_id, stage),
        ).fetchone()
        return _row_to_stage_execution(row) if row is not None else None

    def mark_item(
        self,
        run_id: str,
        stage: str,
        item_key: str,
        status: ItemStatus,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO stage_item
                (run_id, stage_name, item_key, status, attempts, error, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT (run_id, stage_name, item_key) DO UPDATE SET
                status = excluded.status,
                attempts = stage_item.attempts + 1,
                error = excluded.error,
                updated_at = excluded.updated_at
            """,
            (run_id, stage, item_key, status.value, error, _utc_now_text()),
        )

    def pending_items(self, run_id: str, stage: str, all_keys: list[str]) -> list[str]:
        done_rows = self._conn.execute(
            "SELECT item_key FROM stage_item WHERE run_id = ? AND stage_name = ? AND status = ?",
            (run_id, stage, ItemStatus.DONE.value),
        ).fetchall()
        done_keys = {row["item_key"] for row in done_rows}
        return [key for key in all_keys if key not in done_keys]


class SourceRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, obj: SourceObject) -> int:
        self._conn.execute(
            """
            INSERT INTO source_object
                (schema_name, object_name, object_type, visibility, inferred_from,
                 line_count, source_available, status, module, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (schema_name, object_name, object_type) DO UPDATE SET
                visibility = excluded.visibility,
                inferred_from = excluded.inferred_from,
                line_count = excluded.line_count,
                source_available = excluded.source_available,
                status = excluded.status,
                module = excluded.module,
                content_hash = excluded.content_hash
            """,
            (
                obj.schema_name,
                obj.object_name,
                obj.object_type,
                obj.visibility.value,
                obj.inferred_from,
                obj.line_count,
                int(obj.source_available),
                obj.status,
                obj.module,
                obj.content_hash,
            ),
        )
        row = self._conn.execute(
            """
            SELECT object_id FROM source_object
            WHERE schema_name = ? AND object_name = ? AND object_type = ?
            """,
            (obj.schema_name, obj.object_name, obj.object_type),
        ).fetchone()
        return int(row["object_id"])

    def by_visibility(self, v: Visibility) -> list[SourceObject]:
        rows = self._conn.execute(
            "SELECT * FROM source_object WHERE visibility = ?", (v.value,)
        ).fetchall()
        return [_row_to_source_object(row) for row in rows]


class RuleRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert_extraction(self, candidate: Rule, module_prefix: str) -> Rule:
        """Load existing rules for the object, apply F-02's matching and merge,
        allocate a new rule_id only when nothing matches, and write — all in one
        transaction. `module_prefix` is required explicitly: nothing in F-01/F-02
        defines a `Rule.module` -> id-prefix mapping, and that mapping is exactly
        the kind of decision that must be deliberate, not derived."""
        self._conn.execute("BEGIN")
        try:
            existing = self._by_source_object(candidate.source_object)
            matched = match_existing(candidate, existing)
            if matched is not None:
                result = merge_extraction(candidate, matched)
            else:
                new_id = next_rule_id(module_prefix, self._all_rule_ids())
                result = Rule.model_validate({**candidate.model_dump(), "rule_id": new_id})
            self._write(result)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")
        return result

    def disposition(
        self,
        rule_id: str,
        to_state: ReviewState,
        reviewer: str,
        statement: str | None,
        note: str | None,
        duration_ms: int | None,
    ) -> Rule:
        """Write the rule update and its review_event row in a single
        transaction — the rule's current state and its audit trail are the
        same fact recorded twice and must never diverge."""
        self._conn.execute("BEGIN")
        try:
            row = self._conn.execute(
                "SELECT * FROM rule WHERE rule_id = ?", (rule_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"no rule with rule_id {rule_id!r}")
            current = _row_to_rule(row)
            now = datetime.now(UTC)
            merged = current.model_dump()
            merged.update(
                review_state=to_state,
                reviewer=reviewer,
                reviewed_at=now,
                reviewer_note=note,
                statement=statement if statement is not None else current.statement,
            )
            updated = Rule.model_validate(merged)
            self._write(updated)
            self._conn.execute(
                """
                INSERT INTO review_event
                    (rule_id, from_state, to_state, reviewer, note, occurred_at, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    current.review_state.value,
                    to_state.value,
                    reviewer,
                    note,
                    _to_text(now),
                    duration_ms,
                ),
            )
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")
        return updated

    def by_module(self, module: str) -> list[Rule]:
        rows = self._conn.execute("SELECT * FROM rule WHERE module = ?", (module,)).fetchall()
        return [_row_to_rule(row) for row in rows]

    def counts_by_state(self) -> dict[ReviewState, int]:
        rows = self._conn.execute(
            "SELECT review_state, COUNT(*) AS n FROM rule GROUP BY review_state"
        ).fetchall()
        return {ReviewState(row["review_state"]): row["n"] for row in rows}

    def _by_source_object(self, source_object: str) -> list[Rule]:
        rows = self._conn.execute(
            "SELECT * FROM rule WHERE source_object = ?", (source_object,)
        ).fetchall()
        return [_row_to_rule(row) for row in rows]

    def _all_rule_ids(self) -> list[str]:
        rows = self._conn.execute("SELECT rule_id FROM rule").fetchall()
        return [row["rule_id"] for row in rows]

    def _write(self, rule: Rule) -> None:
        self._conn.execute(
            """
            INSERT INTO rule (
                rule_id, natural_key, statement, original_statement, rule_type,
                module, schema_name, source_object, source_unit, line_start,
                line_end, source_hash, data_elements, confidence,
                extraction_run_id, model_id, review_state, reviewer,
                reviewed_at, reviewer_note, is_stale, duplicate_of
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (rule_id) DO UPDATE SET
                natural_key = excluded.natural_key,
                statement = excluded.statement,
                original_statement = excluded.original_statement,
                rule_type = excluded.rule_type,
                module = excluded.module,
                schema_name = excluded.schema_name,
                source_object = excluded.source_object,
                source_unit = excluded.source_unit,
                line_start = excluded.line_start,
                line_end = excluded.line_end,
                source_hash = excluded.source_hash,
                data_elements = excluded.data_elements,
                confidence = excluded.confidence,
                extraction_run_id = excluded.extraction_run_id,
                model_id = excluded.model_id,
                review_state = excluded.review_state,
                reviewer = excluded.reviewer,
                reviewed_at = excluded.reviewed_at,
                reviewer_note = excluded.reviewer_note,
                is_stale = excluded.is_stale,
                duplicate_of = excluded.duplicate_of
            """,
            (
                rule.rule_id,
                rule.natural_key,
                rule.statement,
                rule.original_statement,
                rule.rule_type.value,
                rule.module,
                rule.schema_name,
                rule.source_object,
                rule.source_unit,
                rule.line_start,
                rule.line_end,
                rule.source_hash,
                json.dumps(rule.data_elements),
                rule.confidence.value,
                rule.extraction_run_id,
                rule.model_id,
                rule.review_state.value,
                rule.reviewer,
                _to_text(rule.reviewed_at),
                rule.reviewer_note,
                int(rule.is_stale),
                rule.duplicate_of,
            ),
        )


class CostRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, event: CostEvent) -> None:
        self._conn.execute(
            """
            INSERT INTO cost_event
                (run_id, stage_name, item_key, model_id, input_tokens,
                 output_tokens, cost_usd, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.run_id,
                event.stage_name,
                event.item_key,
                event.model_id,
                event.input_tokens,
                event.output_tokens,
                event.cost_usd,
                _to_text(event.occurred_at),
            ),
        )

    def total_usd(self, run_id: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_event WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return float(row["total"])
