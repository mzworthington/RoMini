import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3

_MIGRATIONS = {
    1: """
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            uid TEXT PRIMARY KEY,
            position_sec REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mixer (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            level INTEGER NOT NULL
        );
        INSERT OR IGNORE INTO mixer (id, level) VALUES (1, 0);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS catalog (
            uid TEXT PRIMARY KEY,
            path TEXT NOT NULL
        );
        """,
    2: """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            happened_at TEXT NOT NULL,
            action TEXT NOT NULL,
            summary TEXT NOT NULL
        );
        """,
    3: """
        ALTER TABLE audit_log ADD COLUMN headline TEXT NOT NULL DEFAULT '';
        """,
}


def open_state(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
    )
    row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    current = 0 if row is None else int(row[0])
    for version in range(current + 1, SCHEMA_VERSION + 1):
        conn.executescript(_MIGRATIONS[version])
        conn.execute(
            "INSERT INTO schema_version (id, version) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET version = excluded.version",
            (version,),
        )
    conn.commit()
