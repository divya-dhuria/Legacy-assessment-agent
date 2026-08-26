"""SQLite connection management and the migration runner.

No ORM, no Alembic — the schema is a client-facing artifact and must stay
readable by someone who did not write it. Migrations are numbered `.sql`
files in `migrations/`, applied in order, each in its own transaction.
"""

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_NAME_RE = re.compile(r"^(\d+)_.*\.sql$")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _discover_migrations() -> list[tuple[int, Path]]:
    migrations: list[tuple[int, Path]] = []
    for path in _MIGRATIONS_DIR.glob("*.sql"):
        match = _MIGRATION_NAME_RE.match(path.name)
        if match is not None:
            migrations.append((int(match.group(1)), path))
    return sorted(migrations, key=lambda item: item[0])


def _split_statements(sql_text: str) -> list[str]:
    """Split a migration file into individual statements. Migrations are
    authored in-repo as plain DDL with no semicolons inside string or
    comment content, so a naive split on ';' is sufficient and avoids
    depending on `executescript`'s implicit transaction handling."""
    return [statement.strip() for statement in sql_text.split(";") if statement.strip()]


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        migrate(conn)
    except Exception:
        conn.close()
        raise
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if exists is None:
        return 0
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_version").fetchone()
    return int(row["version"])


def migrate(conn: sqlite3.Connection) -> int:
    migrations = _discover_migrations()
    known_max = migrations[-1][0] if migrations else 0
    version = current_version(conn)

    if version > known_max:
        raise RuntimeError(
            f"database schema is at version {version}, but the highest migration "
            f"on disk is {known_max}; refusing to open a database from a newer "
            "version of this tool"
        )

    for migration_version, path in migrations:
        if migration_version <= version:
            continue
        sql_text = path.read_text(encoding="utf-8")
        conn.execute("BEGIN")
        try:
            for statement in _split_statements(sql_text):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (migration_version, _utc_now_iso()),
            )
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
        version = migration_version

    return version
