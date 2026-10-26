import sqlite3
from datetime import datetime
from pathlib import Path

from romini.adapters.sqlite.store import SqliteStore
from romini.features.audit.record import KEEP, AuditEntry


class SqliteAudit(SqliteStore):
    def __init__(self, source: Path | sqlite3.Connection) -> None:
        super().__init__(source)

    def record(self, entry: AuditEntry) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO audit_log (happened_at, action, summary, headline) VALUES (?, ?, ?, ?)",
            (entry.happened_at.isoformat(), entry.action, entry.summary, entry.headline),
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
            "SELECT happened_at, action, summary, headline FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        self._release(conn)
        entries: list[AuditEntry] = []
        for when, action, summary, headline in rows:
            try:
                happened_at = datetime.fromisoformat(when)
            except ValueError:
                continue
            entries.append(AuditEntry(happened_at=happened_at, action=action, summary=summary, headline=headline))
        return entries
