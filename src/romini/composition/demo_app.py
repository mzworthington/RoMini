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
    return create_dashboard(
        storage=library_from_objects(objects, base_url=base_url),
        assign_catalog=catalog,
        settings=settings,
        stories=_CONTENT / "stories",
        characters=_CONTENT / "characters",
        demo=True,
    )
