from pathlib import Path
from shutil import disk_usage


class DiskStorage:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def free_bytes(self) -> int:
        return int(disk_usage(self._root).free)

    @property
    def total_bytes(self) -> int:
        return int(disk_usage(self._root).total)

    def put(self, filename: str, audio: bytes) -> None:
        target = self._root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio)

    def paths(self) -> list[str]:
        files: list[str] = []
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            files.append(path.relative_to(self._root).as_posix())
        return files

    def get(self, filename: str) -> bytes | None:
        target = self._file(filename)
        if target is None:
            return None
        return target.read_bytes()

    def size(self, filename: str) -> int | None:
        marked = self.stamp(filename)
        if marked is None:
            return None
        return marked[0]

    def stamp(self, filename: str) -> tuple[int, int] | None:
        target = self._file(filename)
        if target is None:
            return None
        info = target.stat()
        return info.st_size, info.st_mtime_ns

    def delete(self, filename: str) -> None:
        target = self._file(filename)
        if target is not None:
            target.unlink()

    def public_url(self, filename: str) -> str:
        return ""

    def _file(self, filename: str) -> Path | None:
        target = (self._root / filename).resolve()
        try:
            target.relative_to(self._root.resolve())
        except ValueError:
            return None
        if not target.is_file():
            return None
        return target
