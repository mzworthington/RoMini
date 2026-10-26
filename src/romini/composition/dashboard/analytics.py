from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from romini.composition.dashboard.ctx import DashboardDeps
from romini.features.analytics.posthog import resolve_public_posthog_config

_PRIVACY = Path(__file__).resolve().parent / "templates" / "privacy.html"


def mount(app: FastAPI, deps: DashboardDeps) -> None:
    if not deps.demo:
        return

    @app.get("/posthog-config.json")
    def posthog_config() -> JSONResponse:
        body = resolve_public_posthog_config(deps.posthog_token, deps.posthog_host)
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @app.get("/privacy")
    def privacy() -> HTMLResponse:
        return HTMLResponse(_PRIVACY.read_text(encoding="utf-8"))
