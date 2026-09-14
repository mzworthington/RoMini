import sqlite3
from pathlib import Path

from romini.adapters.sqlite.schema import ensure_schema, open_state


class SqliteMixer:
    def __init__(self, source: Path | sqlite3.Connection, *, ceiling: int = 100) -> None:
        self.ceiling = ceiling
        if isinstance(source, sqlite3.Connection):
            self._conn = source
            self._path: Path | None = None
        else:
            self._conn = None
            self._path = source
            conn = open_state(source)
            ensure_schema(conn)
            conn.close()

    @property
    def level(self) -> int:
        conn = self._connect()
        row = conn.execute("SELECT level FROM mixer WHERE id = 1").fetchone()
        self._release(conn)
        if row is None:
            return 0
        return int(row[0])

    def set_level(self, level: int) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO mixer (id, level) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET level = excluded.level",
            (level,),
        )
        conn.commit()
        self._release(conn)

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        assert self._path is not None
        return open_state(self._path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()
