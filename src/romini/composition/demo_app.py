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
    posthog_token: str = "",
    posthog_host: str = "",
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
        posthog_token=posthog_token,
        posthog_host=posthog_host,
    )


def _copy_writable(source: str, dest: str) -> str:
    shutil.copyfile(source, dest)
    _allow_write(Path(dest))
    return dest


def _allow_write(path: Path) -> None:
    try:
        path.chmod(0o755 if path.is_dir() else 0o644)
    except OSError:
        return


def _writable_studio(content: Path) -> Path:
    root = Path(tempfile.mkdtemp(prefix="romini-demo-"))
    for name in ("stories", "characters"):
        source = content / name
        dest = root / name
        if source.is_dir():
            shutil.copytree(source, dest, copy_function=_copy_writable)
            _allow_write(dest)
            for path in dest.rglob("*"):
                if path.is_dir():
                    _allow_write(path)
        else:
            dest.mkdir()
    return root
