import fcntl
import os
from collections.abc import Callable
from pathlib import Path


class PathCatalog:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def read_text(self) -> str:
        return self._path.read_text()

    def write_text(self, text: str) -> None:
        self.exclusive(lambda _current: text)

    def exclusive(self, change: Callable[[str], str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = Path(str(self._path) + ".lock")
        handle = lock_path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            current = self._path.read_text() if self._path.is_file() else ""
            updated = change(current)
            if updated != current:
                temporary = Path(f"{self._path}.{os.getpid()}.tmp")
                temporary.write_text(updated)
                os.replace(temporary, self._path)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
