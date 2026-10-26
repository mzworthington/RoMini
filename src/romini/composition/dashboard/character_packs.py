from pathlib import Path

import yaml

from romini.composition.dashboard.pack_cursor import _remember_current, current_pack, story_slug


def list_saved_characters(root: Path | None) -> list[dict[str, str]]:
    if root is None or not root.is_dir():
        return []
    found: list[dict[str, str]] = []
    for path in sorted(root.iterdir()):
        row = _character_row(path)
        if row is not None:
            found.append(row)
    return found


def write_character(root: Path, *, name: str, background: str, slug: str = "") -> Path:
    target = slug or story_slug(name)
    pack = root / target if target else root
    pack.mkdir(parents=True, exist_ok=True)
    if target:
        _remember_current(root, target)
    (pack / "character.yaml").write_text(yaml.safe_dump({"name": name, "background": background}, sort_keys=True))
    return pack


def character_name_taken(root: Path, *, name: str, except_slug: str = "") -> bool:
    want = story_slug(name)
    folded = name.strip().casefold()
    if not want and not folded:
        return False
    return _name_matches(root, want=want, folded=folded, except_slug=except_slug)


def open_character_pack(root: Path, slug: str) -> None:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        return
    if not (root / slug / "character.yaml").is_file():
        return
    _remember_current(root, slug)


def load_open_character(root: Path | None) -> dict[str, str]:
    notes = {"name": "", "background": "", "slug": ""}
    if root is None:
        return notes
    pack = current_pack(root)
    path = pack / "character.yaml"
    if not path.is_file():
        return notes
    data = yaml.safe_load(path.read_text()) or {}
    notes["name"] = str(data.get("name") or "")
    notes["background"] = str(data.get("background") or "")
    notes["slug"] = pack.name if pack != root else ""
    return notes


def _character_row(path: Path) -> dict[str, str] | None:
    yaml_path = path / "character.yaml"
    if not path.is_dir() or not yaml_path.is_file():
        return None
    data = yaml.safe_load(yaml_path.read_text()) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    return {"name": name, "slug": path.name, "background": str(data.get("background") or "")}


def _name_matches(root: Path, *, want: str, folded: str, except_slug: str) -> bool:
    for item in list_saved_characters(root):
        if item["slug"] == except_slug:
            continue
        if item["slug"] == want or item["name"].casefold() == folded:
            return True
    return False
