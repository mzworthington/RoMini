import sqlite3
from pathlib import Path

from romini.adapters.sqlite.schema import ensure_schema, open_state


class SqliteStore:
    """Open a state file, migrate it once, and hand out short-lived connections."""

    def __init__(self, source: Path | sqlite3.Connection) -> None:
        if isinstance(source, sqlite3.Connection):
            self._conn: sqlite3.Connection | None = source
            self._path: Path | None = None
            return
        self._conn = None
        self._path = source
        conn = open_state(source)
        ensure_schema(conn)
        conn.close()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        assert self._path is not None
        return open_state(self._path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()
