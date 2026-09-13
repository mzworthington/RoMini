"""Flask web app that serves the RoMini magic storyteller."""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from . import __version__
from .story import DEFAULT_THEME, available_themes, generate_story


def create_app() -> Flask:
    """Application factory so tests can spin up isolated instances."""

    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html",
            themes=available_themes(),
            version=__version__,
        )

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok", version=__version__)

    @app.post("/api/story")
    def api_story():
        payload = request.get_json(silent=True) or {}
        hero = payload.get("hero", "Romy")
        theme = payload.get("theme", DEFAULT_THEME)
        seed = payload.get("seed")
        try:
            seed = int(seed) if seed is not None and seed != "" else None
        except (TypeError, ValueError):
            seed = None

        story = generate_story(hero=hero, theme=theme, seed=seed)
        return jsonify(story.to_dict())

    return app


app = create_app()


def main() -> None:
    """Entry point for ``python -m romini`` / the ``romini`` console script."""

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    main()
