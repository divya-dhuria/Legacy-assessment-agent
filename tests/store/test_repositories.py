from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from laa.domain.enums import Confidence, ItemStatus, ReviewState, RuleType, RunStatus, Visibility
from laa.domain.rule import Rule
from laa.domain.source import SourceObject
from laa.store import db
from laa.store.repositories import (
    CostEvent,
    CostRepo,
    RuleRepo,
    Run,
    RunRepo,
    SourceRepo,
    StageRepo,
)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(tmp_path / "engagement.db")
    try:
        yield connection
    finally:
        connection.close()


def make_rule(**overrides: object) -> Rule:
    defaults: dict[str, object] = dict(
        rule_id="BR-RATE-0001",
        natural_key="key-" + str(overrides.get("_disambiguator", "1")),
        statement="Apply the surcharge when the policy is lapsed.",
        original_statement="Apply the surcharge when the policy is lapsed.",
        rule_type=RuleType.CALCULATION,
        module="rating",
        schema_name="RATING",
        source_object="PKG_RATING_ENGINE",
        source_unit="PRC_APPLY_LOADINGS",
        line_start=10,
        line_end=20,
        source_hash="b" * 64,
        data_elements=["policy.status"],
        confidence=Confidence.HIGH,
        extraction_run_id="run-1",
        model_id="claude-sonnet-5",
    )
    overrides.pop("_disambiguator", None)
    defaults.update(overrides)
    return Rule(**defaults)  # type: ignore[arg-type]


def make_source(**overrides: object) -> SourceObject:
    defaults: dict[str, object] = dict(
        schema_name="RATING",
        object_name="PKG_RATING_ENGINE",
        object_type="PACKAGE BODY",
        visibility=Visibility.VISIBLE_WITH_SOURCE,
    )
    defaults.update(overrides)
    return SourceObject(**defaults)  # type: ignore[arg-type]


def seed_run(conn: sqlite3.Connection, run_id: str = "run-1") -> None:
    """stage_execution and cost_event both carry a foreign key to run — tests
    exercising them in isolation need a parent row first."""
    RunRepo(conn).create(
        Run(
            run_id=run_id,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            status=RunStatus.RUNNING,
            config_hash="abc123",
            tool_version="0.1.0",
        )
    )


# --- RunRepo ----------------------------------------------------------------


def test_run_create_and_latest_round_trip(conn: sqlite3.Connection) -> None:
    repo = RunRepo(conn)
    run = Run(
        run_id="run-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        status=RunStatus.RUNNING,
        config_hash="abc123",
        tool_version="0.1.0",
        git_sha="deadbeef",
    )
    repo.create(run)

    latest = repo.latest()
    assert latest == run


def test_run_finish_updates_status_and_ended_at(conn: sqlite3.Connection) -> None:
    repo = RunRepo(conn)
    run = Run(
        run_id="run-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        status=RunStatus.RUNNING,
        config_hash="abc123",
        tool_version="0.1.0",
    )
    repo.create(run)

    repo.finish("run-1", RunStatus.COMPLETED)

    latest = repo.latest()
    assert latest is not None
    assert latest.status == RunStatus.COMPLETED
    assert latest.ended_at is not None


def test_run_latest_returns_none_when_empty(conn: sqlite3.Connection) -> None:
    assert RunRepo(conn).latest() is None


# --- StageRepo ----------------------------------------------------------------


def test_stage_upsert_and_get_execution_round_trip(conn: sqlite3.Connection) -> None:
    seed_run(conn)
    repo = StageRepo(conn)
    repo.upsert_execution(
        run_id="run-1",
        stage_name="inventory",
        status=RunStatus.RUNNING,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        items_total=10,
    )

    execution = repo.get_execution("run-1", "inventory")
    assert execution is not None
    assert execution.status == RunStatus.RUNNING
    assert execution.items_total == 10

    repo.upsert_execution(
        run_id="run-1",
        stage_name="inventory",
        status=RunStatus.COMPLETED,
        items_total=10,
        items_done=10,
    )
    updated = repo.get_execution("run-1", "inventory")
    assert updated is not None
    assert updated.status == RunStatus.COMPLETED
    assert updated.items_done == 10


def test_get_execution_returns_none_when_missing(conn: sqlite3.Connection) -> None:
    assert StageRepo(conn).get_execution("run-1", "inventory") is None


def test_mark_item_and_pending_items(conn: sqlite3.Connection) -> None:
    seed_run(conn)
    repo = StageRepo(conn)
    repo.upsert_execution(run_id="run-1", stage_name="inventory", status=RunStatus.RUNNING)
    all_keys = ["obj-1", "obj-2", "obj-3"]

    repo.mark_item("run-1", "inventory", "obj-1", ItemStatus.DONE)
    repo.mark_item("run-1", "inventory", "obj-2", ItemStatus.FAILED, error="boom")

    pending = repo.pending_items("run-1", "inventory", all_keys)
    assert pending == ["obj-2", "obj-3"]


def test_mark_item_increments_attempts_on_reattempt(conn: sqlite3.Connection) -> None:
    seed_run(conn)
    repo = StageRepo(conn)
    repo.upsert_execution(run_id="run-1", stage_name="inventory", status=RunStatus.RUNNING)
    repo.mark_item("run-1", "inventory", "obj-1", ItemStatus.FAILED, error="first")
    repo.mark_item("run-1", "inventory", "obj-1", ItemStatus.DONE)

    row = conn.execute(
        "SELECT attempts, status FROM stage_item WHERE run_id = ? AND stage_name = ? "
        "AND item_key = ?",
        ("run-1", "inventory", "obj-1"),
    ).fetchone()
    assert row["attempts"] == 2
    assert row["status"] == "done"


# --- SourceRepo -----------------------------------------------------------------


def test_source_upsert_is_stable_and_updates_on_conflict(conn: sqlite3.Connection) -> None:
    repo = SourceRepo(conn)
    first_id = repo.upsert(make_source(line_count=100))
    second_id = repo.upsert(make_source(line_count=150))

    assert first_id == second_id
    [row] = repo.by_visibility(Visibility.VISIBLE_WITH_SOURCE)
    assert row.line_count == 150


def test_source_by_visibility_filters(conn: sqlite3.Connection) -> None:
    repo = SourceRepo(conn)
    repo.upsert(make_source(object_name="PKG_A", visibility=Visibility.VISIBLE_WITH_SOURCE))
    repo.upsert(
        make_source(
            object_name="PKG_B",
            visibility=Visibility.INFERRED_ONLY,
            inferred_from="dependency:PKG_A",
        )
    )

    visible = repo.by_visibility(Visibility.VISIBLE_WITH_SOURCE)
    inferred = repo.by_visibility(Visibility.INFERRED_ONLY)
    assert [o.object_name for o in visible] == ["PKG_A"]
    assert [o.object_name for o in inferred] == ["PKG_B"]


@pytest.mark.parametrize(
    "source",
    [
        make_source(
            visibility=Visibility.VISIBLE_WITH_SOURCE, line_count=10, source_available=True
        ),
        make_source(visibility=Visibility.VISIBLE_NO_SOURCE),
        make_source(visibility=Visibility.INFERRED_ONLY, inferred_from="dependency:PKG_A"),
    ],
)
def test_source_round_trips_all_visibility_states(
    conn: sqlite3.Connection, source: SourceObject
) -> None:
    repo = SourceRepo(conn)
    repo.upsert(source)
    [persisted] = repo.by_visibility(source.visibility)
    assert persisted == source


def test_inferred_only_persists_without_line_count_or_content_hash(
    conn: sqlite3.Connection,
) -> None:
    repo = SourceRepo(conn)
    repo.upsert(
        make_source(visibility=Visibility.INFERRED_ONLY, inferred_from="dependency:PKG_A")
    )
    [persisted] = repo.by_visibility(Visibility.INFERRED_ONLY)
    assert persisted.line_count is None
    assert persisted.content_hash is None
    assert persisted.source_available is False


# --- RuleRepo -------------------------------------------------------------------


def test_upsert_extraction_allocates_new_id_when_no_match(conn: sqlite3.Connection) -> None:
    repo = RuleRepo(conn)
    candidate = make_rule(rule_id="BR-RATE-0001", natural_key="key-a")

    result = repo.upsert_extraction(candidate, module_prefix="RATE")

    assert result.rule_id == "BR-RATE-0001"
    [row] = repo.by_module("rating")
    assert row.rule_id == "BR-RATE-0001"


def test_upsert_extraction_second_new_rule_gets_next_id(conn: sqlite3.Connection) -> None:
    repo = RuleRepo(conn)
    repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0001", natural_key="key-a"), module_prefix="RATE"
    )
    second = repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0002", natural_key="key-b", line_start=30, line_end=40),
        module_prefix="RATE",
    )

    assert second.rule_id == "BR-RATE-0002"


def test_upsert_extraction_reuses_id_and_preserves_review_state_on_natural_key_match(
    conn: sqlite3.Connection,
) -> None:
    repo = RuleRepo(conn)
    first = repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0001", natural_key="key-a"), module_prefix="RATE"
    )

    reviewed = repo.disposition(
        rule_id=first.rule_id,
        to_state=ReviewState.ACCEPTED,
        reviewer="jane",
        statement=None,
        note="looks right",
        duration_ms=1200,
    )
    assert reviewed.review_state == ReviewState.ACCEPTED

    re_extracted = make_rule(
        rule_id="BR-RATE-9999",
        natural_key="key-a",
        line_start=15,
        line_end=25,
        source_hash="b" * 64,
        extraction_run_id="run-2",
    )
    merged = repo.upsert_extraction(re_extracted, module_prefix="RATE")

    assert merged.rule_id == first.rule_id
    assert merged.review_state == ReviewState.ACCEPTED
    assert merged.reviewer == "jane"
    assert merged.is_stale is False


def test_upsert_extraction_sets_is_stale_on_source_change(conn: sqlite3.Connection) -> None:
    repo = RuleRepo(conn)
    repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0001", natural_key="key-a", source_hash="a" * 64),
        module_prefix="RATE",
    )
    changed = repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-9999", natural_key="key-a", source_hash="c" * 64),
        module_prefix="RATE",
    )

    assert changed.is_stale is True


def test_disposition_writes_rule_and_review_event_together(conn: sqlite3.Connection) -> None:
    repo = RuleRepo(conn)
    rule = repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0001", natural_key="key-a"), module_prefix="RATE"
    )

    repo.disposition(
        rule_id=rule.rule_id,
        to_state=ReviewState.ACCEPTED,
        reviewer="jane",
        statement=None,
        note="fine as-is",
        duration_ms=500,
    )

    persisted = repo.by_module("rating")[0]
    assert persisted.review_state == ReviewState.ACCEPTED
    assert persisted.reviewer == "jane"

    events = conn.execute(
        "SELECT * FROM review_event WHERE rule_id = ?", (rule.rule_id,)
    ).fetchall()
    assert len(events) == 1
    assert events[0]["to_state"] == "accepted"
    assert events[0]["duration_ms"] == 500


def test_disposition_rolls_back_both_on_failure(conn: sqlite3.Connection) -> None:
    repo = RuleRepo(conn)
    rule = repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0001", natural_key="key-a"), module_prefix="RATE"
    )

    # EDITED requires statement != original_statement; passing no new statement
    # on a never-edited rule violates that invariant and must fail atomically.
    with pytest.raises(ValidationError):
        repo.disposition(
            rule_id=rule.rule_id,
            to_state=ReviewState.EDITED,
            reviewer="jane",
            statement=None,
            note=None,
            duration_ms=None,
        )

    persisted = repo.by_module("rating")[0]
    assert persisted.review_state == ReviewState.PENDING
    assert persisted.reviewer is None

    events = conn.execute(
        "SELECT * FROM review_event WHERE rule_id = ?", (rule.rule_id,)
    ).fetchall()
    assert len(events) == 0


def test_by_module_filters(conn: sqlite3.Connection) -> None:
    repo = RuleRepo(conn)
    repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0001", natural_key="key-a", module="rating"),
        module_prefix="RATE",
    )
    repo.upsert_extraction(
        make_rule(
            rule_id="BR-CLAIM-0001",
            natural_key="key-b",
            module="claims",
            source_object="PKG_CLAIMS_ENGINE",
        ),
        module_prefix="CLAIM",
    )

    assert [r.rule_id for r in repo.by_module("claims")] == ["BR-CLAIM-0001"]


def test_counts_by_state(conn: sqlite3.Connection) -> None:
    repo = RuleRepo(conn)
    rule = repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0001", natural_key="key-a"), module_prefix="RATE"
    )
    repo.upsert_extraction(
        make_rule(rule_id="BR-RATE-0002", natural_key="key-b", line_start=30, line_end=40),
        module_prefix="RATE",
    )
    repo.disposition(
        rule_id=rule.rule_id,
        to_state=ReviewState.ACCEPTED,
        reviewer="jane",
        statement=None,
        note=None,
        duration_ms=None,
    )

    counts = repo.counts_by_state()
    assert counts[ReviewState.ACCEPTED] == 1
    assert counts[ReviewState.PENDING] == 1


# --- CostRepo -------------------------------------------------------------------


def test_cost_record_and_total_usd(conn: sqlite3.Connection) -> None:
    seed_run(conn)
    repo = CostRepo(conn)
    repo.record(
        CostEvent(
            run_id="run-1",
            stage_name="extraction",
            item_key="obj-1",
            model_id="claude-sonnet-5",
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.05,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    repo.record(
        CostEvent(
            run_id="run-1",
            stage_name="extraction",
            item_key="obj-2",
            model_id="claude-sonnet-5",
            input_tokens=500,
            output_tokens=100,
            cost_usd=0.02,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    assert CostRepo(conn).total_usd("run-1") == pytest.approx(0.07)


def test_total_usd_zero_for_unknown_run(conn: sqlite3.Connection) -> None:
    assert CostRepo(conn).total_usd("no-such-run") == 0.0
