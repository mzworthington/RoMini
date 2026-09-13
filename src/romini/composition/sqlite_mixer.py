import sqlite3
from pathlib import Path


class SqliteMixer:
    def __init__(self, path: Path, *, ceiling: int = 100) -> None:
        self.ceiling = ceiling
        self._path = path
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS mixer (id INTEGER PRIMARY KEY CHECK (id = 1), level INTEGER NOT NULL)"
            )
            conn.execute("INSERT OR IGNORE INTO mixer (id, level) VALUES (1, 0)")

    @property
    def level(self) -> int:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT level FROM mixer WHERE id = 1").fetchone()
        if row is None:
            return 0
        return int(row[0])

    def set_level(self, level: int) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO mixer (id, level) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET level = excluded.level",
                (level,),
            )
