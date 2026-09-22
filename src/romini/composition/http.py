from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import environ
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from romini.composition.inject import apply_sim_line
from romini.composition.sim import SimBox

TEMPLATES_DIR = Path(__file__).resolve().parent / "dashboard" / "templates"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SIM_ASSETS = {
    "/favicon.svg": "image/svg+xml",
    "/mark.svg": "image/svg+xml",
    "/plus-jakarta-sans.woff2": "font/woff2",
}


def sim_home_page() -> bytes:
    css = (TEMPLATES_DIR / "dashboard.css").read_text() + (TEMPLATES_DIR / "sim.css").read_text()
    return (TEMPLATES_DIR / "sim.html").read_text().replace("{{ css }}", css).encode()


def sim_asset(path: str) -> tuple[bytes, str] | None:
    media_type = SIM_ASSETS.get(path)
    if media_type is None:
        return None
    file = ASSETS_DIR / path.lstrip("/")
    if not file.is_file():
        return None
    return file.read_bytes(), media_type


def apply_sim_http(box: SimBox, method: str, path: str) -> int:
    if method == "POST" and path.startswith("/place/"):
        box.place(path.removeprefix("/place/"))
        return 204
    if method == "POST" and path.startswith("/tap/"):
        box.place(path.removeprefix("/tap/"))
        return 204
    if method == "POST" and path == "/remove":
        apply_sim_line(box, "remove")
        return 204
    if method == "POST" and path == "/vol/up":
        apply_sim_line(box, "vol up")
        return 204
    if method == "POST" and path == "/vol/down":
        apply_sim_line(box, "vol down")
        return 204
    if method == "POST" and path == "/halt":
        apply_sim_line(box, "halt")
        return 204
    if method == "POST" and path == "/play":
        apply_sim_line(box, "play")
        return 204
    return 404


class SimHttpListener:
    def __init__(self, server: ThreadingHTTPServer, host: str) -> None:
        self._server = server
        self._host = host
        self._thread = Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return self._server.server_port

    def post(self, path: str) -> int:
        req = Request(f"http://{self._host}:{self.port}{path}", method="POST", data=b"")  # NOSONAR python:S5332
        try:
            with urlopen(req) as resp:
                return resp.status
        except HTTPError as exc:
            return exc.code

    def wait(self) -> None:
        self._thread.join()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


def start_sim_http(box: SimBox, *, host: str, port: int) -> SimHttpListener:
    if environ.get("ROMINI_PROFILE", "sim") != "sim":
        raise ValueError("sim HTTP is sim profile only")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("sim HTTP binds localhost only")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/":
                body = sim_home_page()
                media_type = "text/html; charset=utf-8"
            else:
                asset = sim_asset(path)
                if asset is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                body, media_type = asset
            self.send_response(200)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            status = apply_sim_http(box, "POST", self.path)
            self.send_response(status)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    return SimHttpListener(ThreadingHTTPServer((host, port), Handler), host)
