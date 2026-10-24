import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect

from romini.composition.dashboard.shared import DashboardCtx, notice
from romini.features.library.backup import restore_backup, write_backup


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/backup")
    def download_backup() -> FileResponse:
        handle = tempfile.NamedTemporaryFile(prefix="romini-backup-", suffix=".zip", delete=False)
        path = Path(handle.name)
        try:
            write_backup(
                handle,
                catalog=_catalog_path(ctx.assign_catalog),
                stories=ctx.stories,
                characters=ctx.characters,
                library=_library_root(ctx.storage),
            )
        except BaseException:
            handle.close()
            path.unlink(missing_ok=True)
            raise
        handle.close()
        return FileResponse(
            path,
            media_type="application/zip",
            filename="romini-backup.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    @app.post("/backup", response_model=None)
    async def import_backup(request: Request) -> RedirectResponse:
        try:
            form = await request.form()
        except ClientDisconnect:
            return RedirectResponse("/settings", status_code=303)
        upload = form.get("file")
        payload = getattr(upload, "file", None)
        if payload is None or not str(getattr(upload, "filename", "") or "").strip():
            return notice("/settings", "backup-needed")
        try:
            restore_backup(
                payload,
                catalog=_catalog_path(ctx.assign_catalog),
                stories=ctx.stories,
                characters=ctx.characters,
                library=_library_root(ctx.storage),
            )
        except (zipfile.BadZipFile, ValueError):
            return notice("/settings", "backup-needed")
        ctx.note("backup", "Restored stories and catalog", headline="Backup restored")
        return notice("/settings", "backup")


def _catalog_path(catalog: object) -> Path | None:
    path = getattr(catalog, "path", None)
    return path if isinstance(path, Path) else None


def _library_root(storage: object) -> Path | None:
    root = getattr(storage, "root", None)
    if callable(root):
        root = root()
    return root if isinstance(root, Path) else None
