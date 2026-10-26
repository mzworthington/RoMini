import sqlite3
from pathlib import Path

from romini.adapters.sqlite.store import SqliteStore


class SqliteMixer(SqliteStore):
    def __init__(self, source: Path | sqlite3.Connection, *, ceiling: int = 100) -> None:
        self.ceiling = ceiling
        super().__init__(source)

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
