from __future__ import annotations

from pathlib import Path

import pytest

from laa.store import db


def test_fresh_db_applies_all_migrations_and_reports_version(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "engagement.db")
    try:
        assert db.current_version(conn) == 1
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "schema_version",
            "engagement",
            "run",
            "stage_execution",
            "stage_item",
            "access_probe",
            "source_object",
            "rule",
            "review_event",
            "cost_event",
        } <= tables
    finally:
        conn.close()


def test_reopening_applies_nothing_and_does_not_error(tmp_path: Path) -> None:
    db_path = tmp_path / "engagement.db"
    conn = db.connect(db_path)
    conn.close()

    conn2 = db.connect(db_path)
    try:
        assert db.current_version(conn2) == 1
    finally:
        conn2.close()


def test_connection_pragmas_are_set(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "engagement.db")
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_row_factory_returns_sqlite_row(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "engagement.db")
    try:
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1
    finally:
        conn.close()


def test_version_above_highest_known_migration_raises_clear_error(tmp_path: Path) -> None:
    db_path = tmp_path / "engagement.db"
    conn = db.connect(db_path)
    conn.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
        (999, "2026-01-01T00:00:00+00:00"),
    )
    conn.close()

    with pytest.raises(RuntimeError, match=r"999.*1|1.*999"):
        db.connect(db_path)


def test_migrate_is_idempotent_when_called_directly(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "engagement.db")
    try:
        assert db.migrate(conn) == 1
        assert db.migrate(conn) == 1
    finally:
        conn.close()
