from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from romini.composition.dashboard.shared import DashboardCtx, notice
from romini.features.library.register_tag import name_tag


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
        ctx.note("present", f"Presented {uid}", headline="Figure presented")
        return notice("/figures", "presented")

    @app.post("/register-mode")
    async def switch_register_mode(request: Request) -> RedirectResponse:
        if ctx.register is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        ctx.register.assign_mode = str(form.get("register")) == "on"
        key = "register-on" if ctx.register.assign_mode else "register-off"
        label = "Register on" if ctx.register.assign_mode else "Register off"
        ctx.note("register", label, headline=label)
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
