import sqlite3
import threading
from pathlib import Path

SCHEMA_VERSION = 4

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
    4: """
        CREATE TABLE IF NOT EXISTS play_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT
        );
        """,
}


class _SnapshotCursor:
    def __init__(self, description: object, rows: list[tuple]) -> None:
        self.description = description
        self._rows = rows
        self._index = 0

    def fetchone(self) -> tuple | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[tuple]:
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return rows

    def __iter__(self) -> "_SnapshotCursor":
        return self

    def __next__(self) -> tuple:
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class _SerializedConnection(sqlite3.Connection):
    """One shared connection is used from the player thread and the dashboard pool.

    sqlite3 cursors are not safe to share. Overlapping execute/fetch on this
    connection raises InterfaceError and can yield empty rows.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._gate = threading.RLock()
        self._depth = 0

    def execute(self, sql: str, parameters: object = (), /) -> sqlite3.Cursor | _SnapshotCursor:
        self._gate.acquire()
        self._depth += 1
        try:
            cursor = sqlite3.Connection.execute(self, sql, parameters)
            if cursor.description is not None:
                snapshot = _SnapshotCursor(cursor.description, cursor.fetchall())
                self._drop()
                return snapshot
            return cursor
        except BaseException:
            self._abort()
            raise

    def executemany(self, sql: str, seq: object, /) -> sqlite3.Cursor:
        self._gate.acquire()
        self._depth += 1
        try:
            return sqlite3.Connection.executemany(self, sql, seq)
        except BaseException:
            self._abort()
            raise

    def executescript(self, sql: str, /) -> sqlite3.Cursor:
        self._gate.acquire()
        self._depth += 1
        try:
            return sqlite3.Connection.executescript(self, sql)
        finally:
            self._drop()

    def commit(self) -> None:
        if self._depth == 0:
            with self._gate:
                sqlite3.Connection.commit(self)
            return
        try:
            sqlite3.Connection.commit(self)
        except BaseException:
            self._rollback_quietly()
            raise
        finally:
            while self._depth:
                self._drop()

    def rollback(self) -> None:
        if self._depth == 0:
            with self._gate:
                sqlite3.Connection.rollback(self)
            return
        try:
            sqlite3.Connection.rollback(self)
        finally:
            while self._depth:
                self._drop()

    def close(self) -> None:
        try:
            sqlite3.Connection.close(self)
        finally:
            while self._depth:
                self._drop()

    def _drop(self) -> None:
        self._depth -= 1
        self._gate.release()

    def _abort(self) -> None:
        self._rollback_quietly()
        while self._depth:
            self._drop()

    def _rollback_quietly(self) -> None:
        try:
            sqlite3.Connection.rollback(self)
        except sqlite3.Error:
            pass


def open_state(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, factory=_SerializedConnection)
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
