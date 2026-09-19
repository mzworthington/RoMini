import sqlite3
from datetime import datetime
from pathlib import Path

from romini.adapters.sqlite.schema import ensure_schema, open_state
from romini.features.audit.record import KEEP, AuditEntry


class SqliteAudit:
    def __init__(self, source: Path | sqlite3.Connection) -> None:
        if isinstance(source, sqlite3.Connection):
            self._conn = source
            self._path: Path | None = None
        else:
            self._conn = None
            self._path = source
            conn = open_state(source)
            ensure_schema(conn)
            conn.close()

    def record(self, entry: AuditEntry) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO audit_log (happened_at, action, summary) VALUES (?, ?, ?)",
            (entry.happened_at.isoformat(), entry.action, entry.summary),
        )
        conn.execute(
            "DELETE FROM audit_log WHERE id NOT IN (SELECT id FROM audit_log ORDER BY id DESC LIMIT ?)",
            (KEEP,),
        )
        conn.commit()
        self._release(conn)

    def recent(self, *, limit: int = KEEP) -> list[AuditEntry]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT happened_at, action, summary FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        self._release(conn)
        return [
            AuditEntry(happened_at=datetime.fromisoformat(when), action=action, summary=summary)
            for when, action, summary in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        assert self._path is not None
        return open_state(self._path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()
