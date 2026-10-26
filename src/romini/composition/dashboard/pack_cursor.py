from pathlib import Path

# The demo Worker ships this tree read-only. Remember the open pack when the file cannot be updated.
_OPEN: dict[Path, str | None] = {}


def story_slug(title: str) -> str:
    parts: list[str] = []
    for ch in title.lower():
        if ch.isalnum():
            parts.append(ch)
        elif parts and parts[-1] != "-":
            parts.append("-")
    return "".join(parts).strip("-")


def open_story_pack(root: Path, slug: str) -> None:
    if not _safe_slug(slug):
        return
    if not (root / slug / "story.yaml").is_file():
        return
    _remember_current(root, slug)


def clear_current(root: Path) -> None:
    _remember_current(root, None)


def current_pack(root: Path) -> Path:
    remembered = _open_pack(root)
    if remembered is not None:
        return remembered
    return _pointer_pack(root)


def _safe_slug(slug: str) -> bool:
    if not slug or slug in {".", ".."}:
        return False
    return "/" not in slug and "\\" not in slug


def _remember_current(root: Path, slug: str | None) -> None:
    pointer = root / "current"
    try:
        _write_pointer(pointer, slug)
    except OSError:
        _OPEN[root] = slug
        return
    _OPEN.pop(root, None)


def _write_pointer(pointer: Path, slug: str | None) -> None:
    if slug is None:
        if pointer.is_file():
            pointer.unlink()
        return
    text = f"{slug}\n"
    if not pointer.is_file() or pointer.read_text() != text:
        pointer.write_text(text)


def _open_pack(root: Path) -> Path | None:
    if root not in _OPEN:
        return None
    slug = _OPEN[root] or ""
    if not slug:
        return root
    pack = root / slug
    if pack.is_dir():
        return pack
    return None


def _pointer_pack(root: Path) -> Path:
    pointer = root / "current"
    if not pointer.is_file():
        return root
    slug = pointer.read_text().strip()
    pack = root / slug
    if slug and pack.is_dir():
        return pack
    return root
