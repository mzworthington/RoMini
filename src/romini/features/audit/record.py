from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

KEEP = 1000


@dataclass(frozen=True)
class AuditEntry:
    happened_at: datetime
    action: str
    summary: str


class AuditLog(Protocol):
    def record(self, entry: AuditEntry) -> None: ...

    def recent(self, *, limit: int = KEEP) -> list[AuditEntry]: ...


def record_event(
    log: AuditLog,
    *,
    action: str,
    summary: str,
    clock: Callable[[], datetime],
) -> None:
    log.record(AuditEntry(happened_at=clock(), action=action, summary=summary))
