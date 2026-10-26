from pathlib import Path

import yaml

from romini.composition.dashboard.pack_cursor import current_pack


def list_saved_stories(root: Path | None) -> list[dict[str, str]]:
    if root is None or not root.is_dir():
        return []
    found: list[dict[str, str]] = []
    for path in sorted(root.iterdir()):
        row = _story_row(path)
        if row is not None:
            found.append(row)
    return found


def library_file_labels(
    root: Path | None,
    paths: list[str],
    catalog_titles: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    titles = _catalog_titles(_story_titles(root), catalog_titles)
    return [{"path": path, "label": _audition_label(path, titles)} for path in paths]


def spoken_file_name(root: Path | None) -> str:
    if root is None:
        return ""
    pack = current_pack(root)
    if not pack.is_dir():
        return ""
    names = _mp3_names(pack)
    if not names:
        return ""
    stem = pack.name if pack != root else ""
    return _preferred_mp3(names, stem)


def _story_row(path: Path) -> dict[str, str] | None:
    yaml_path = path / "story.yaml"
    if not path.is_dir() or not yaml_path.is_file():
        return None
    data = yaml.safe_load(yaml_path.read_text()) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return None
    return {"title": title, "slug": path.name}


def _story_titles(root: Path | None) -> dict[str, str]:
    titles: dict[str, str] = {}
    if root is None:
        return titles
    for story in list_saved_stories(root):
        _remember_story_paths(titles, root / story["slug"] / "story.yaml", story["title"])
    return titles


def _remember_story_paths(titles: dict[str, str], yaml_path: Path, title: str) -> None:
    data = yaml.safe_load(yaml_path.read_text()) if yaml_path.is_file() else {}
    data = data or {}
    for key in ("library_path", "spoken_file"):
        path = str(data.get(key) or "").strip()
        if path:
            titles[path] = title


def _catalog_titles(titles: dict[str, str], catalog_titles: dict[str, str] | None) -> dict[str, str]:
    merged = dict(titles)
    for path, title in (catalog_titles or {}).items():
        cleaned = title.strip()
        if path.strip() and cleaned:
            merged[path] = cleaned
    return merged


def _audition_label(path: str, titles: dict[str, str]) -> str:
    exact = titles.get(path, "").strip()
    if exact:
        return exact
    return _stem_title(path, titles)


def _stem_title(path: str, titles: dict[str, str]) -> str:
    name = Path(path).name
    for key, title in titles.items():
        cleaned = title.strip()
        if cleaned and Path(key).name == name:
            return cleaned
    return path


def _mp3_names(pack: Path) -> list[str]:
    return sorted(path.name for path in pack.iterdir() if path.is_file() and path.suffix.lower() == ".mp3")


def _preferred_mp3(names: list[str], stem: str) -> str:
    preferred = [name for name in names if stem and name.startswith(stem) and name.endswith(".mp3")]
    if preferred:
        return preferred[-1]
    return names[0]
