from romini.features.audit.record import KEEP, AuditEntry


class MemoryAuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self._entries.insert(0, entry)
        del self._entries[KEEP:]

    def recent(self, *, limit: int = KEEP) -> list[AuditEntry]:
        return list(self._entries[:limit])
