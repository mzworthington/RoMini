from fastapi import FastAPI

from romini.adapters.cloudflare.bindings import load_objects, load_settings_rows
from romini.composition.demo_app import create_demo_app


async def app_for_env(env: object) -> FastAPI:
    rows = await load_settings_rows(getattr(env, "DB"))
    objects = await load_objects(getattr(env, "LIBRARY"))
    return create_demo_app(
        settings_rows=rows,
        objects=objects,
        base_url=str(getattr(env, "LIBRARY_BASE_URL")),
    )


class Default:
    async def fetch(self, request: object) -> object:
        # workers is the Cloudflare runtime package. It is not installed on the Pi.
        from workers import asgi

        app = getattr(self, "_app", None)
        if app is None:
            app = await app_for_env(self.env)
            self._app = app
        return await asgi.fetch(app, request, self.env)
