from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from romini.composition.sqlite_settings import SqliteSettings
from romini.features.library.add_track import Catalog, Notices, Storage, add_track
from romini.features.library.assign import CatalogFile, confirm_assign
from romini.features.play_by_tag.place_figure import PlayMode


def create_dashboard(
    *,
    storage: Storage,
    notices: Notices | None = None,
    catalog: Catalog | None = None,
    assign_catalog: CatalogFile | None = None,
    settings: SqliteSettings | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.get("/storage")
    def storage_info() -> dict[str, int]:
        return {"free_bytes": storage.free_bytes}

    @app.post("/tracks", status_code=201)
    async def upload_track(file: UploadFile = File()) -> dict[str, bool]:
        class Quiet:
            def tell(self, message: str) -> None:
                return

        audio = await file.read()
        stored = add_track(
            audio=audio,
            filename=file.filename or "track.bin",
            storage=storage,
            notices=notices if notices is not None else Quiet(),
            catalog=catalog,
        )
        return {"stored": stored}

    class AssignBody(BaseModel):
        uid: str
        path: str
        title: str

    @app.post("/assign", status_code=204)
    def assign_tag(body: AssignBody) -> None:
        if assign_catalog is None:
            raise HTTPException(status_code=404)
        confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=assign_catalog)

    class PlayModeBody(BaseModel):
        play_mode: PlayMode

    @app.put("/play-mode", status_code=204)
    def switch_play_mode(body: PlayModeBody) -> None:
        if settings is None:
            raise HTTPException(status_code=404)
        settings.remember_play_mode(body.play_mode)

    return app
