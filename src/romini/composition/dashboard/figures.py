from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from romini.composition.dashboard.shared import DashboardCtx, notice
from romini.features.library.register_tag import name_tag
from romini.features.play_by_tag.sleep import next_sleep


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/figures", response_class=HTMLResponse)
    def figures_page(request: Request) -> HTMLResponse:
        return ctx.page(request, "figures.html", page="figures", page_title="Figures")

    @app.post("/present")
    async def present_figure(request: Request) -> RedirectResponse:
        if ctx.pad is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        uid = str(form["uid"]).strip()
        if not uid:
            return notice("/figures", "needed")
        ctx.pad.place(uid)
        ctx.note("present", f"Presented {uid}")
        return notice("/figures", "presented")

    @app.post("/register-mode")
    async def switch_register_mode(request: Request) -> RedirectResponse:
        if ctx.register is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        ctx.register.assign_mode = str(form.get("register")) == "on"
        key = "register-on" if ctx.register.assign_mode else "register-off"
        ctx.note("register", "Register on" if ctx.register.assign_mode else "Register off")
        return notice("/figures", key)

    @app.post("/tags/{uid}/name")
    async def name_registered_tag(uid: str, request: Request) -> RedirectResponse:
        if ctx.assign_catalog is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        name = str(form.get("name") or "")
        name_tag(uid=uid, name=name, catalog=ctx.assign_catalog)
        ctx.note("name", f"Named {uid} {name}".strip())
        return notice("/figures", "named")

    @app.post("/stop")
    def stop_and_eject() -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        ctx.player.stop()
        ctx.note("play", "Stopped")
        return notice("/figures", "stopped")

    @app.post("/sleep")
    async def sleep(request: Request) -> RedirectResponse:
        if ctx.settings is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        try:
            minutes = int(str(form.get("minutes") or "30"))
        except ValueError:
            return notice("/figures", "needed")
        if minutes < 1 or minutes > 180:
            return notice("/figures", "needed")
        extend = str(form.get("extend") or "") == "1"
        target = str(form.get("next") or "/figures")
        if target not in {"/", "/figures"}:
            target = "/figures"
        when = next_sleep(
            until=ctx.settings.sleep_until(),
            now=datetime.now(UTC),
            minutes=minutes,
            extend=extend,
        )
        ctx.settings.remember_sleep_until(when)
        ctx.note("sleep", f"Sleep at {when.strftime('%H:%M')}")
        return notice(target, "sleep")
