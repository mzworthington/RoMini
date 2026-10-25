import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI

from romini.adapters.cloudflare.library import library_from_objects
from romini.adapters.cloudflare.snapshot import snapshot_from_settings
from romini.composition.dashboard import create_dashboard

_CONTENT = Path(__file__).resolve().parent / "demo_content"


def create_demo_app(
    *,
    settings_rows: list[tuple[str, str]],
    objects: list[dict[str, object]],
    base_url: str,
) -> FastAPI:
    catalog, settings = snapshot_from_settings(settings_rows)
    studio = _writable_studio(_CONTENT)
    return create_dashboard(
        storage=library_from_objects(objects, base_url=base_url),
        assign_catalog=catalog,
        settings=settings,
        stories=studio / "stories",
        characters=studio / "characters",
        demo=True,
    )


def _writable_studio(content: Path) -> Path:
    root = Path(tempfile.mkdtemp(prefix="romini-demo-"))
    for name in ("stories", "characters"):
        source = content / name
        dest = root / name
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            dest.mkdir()
    return root
