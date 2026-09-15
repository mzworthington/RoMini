from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import environ
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from romini.composition.inject import apply_sim_line
from romini.composition.sim import SimBox


def apply_sim_http(box: SimBox, method: str, path: str) -> int:
    if method == "POST" and path.startswith("/place/"):
        box.place(path.removeprefix("/place/"))
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
        req = Request(f"http://{self._host}:{self.port}{path}", method="POST", data=b"")
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
            if path != "/":
                self.send_response(404)
                self.end_headers()
                return
            body = (
                b"<!DOCTYPE html><title>RoMini sim</title>"
                b"<style>body{font:16px system-ui,sans-serif;color:#111;background:#fff;margin:1rem}"
                b"label{margin-right:.5rem}</style>"
                b'<label for="nfc-uid">NFC tag</label>'
                b'<input id="nfc-uid" name="uid" type="text" autocomplete="off" spellcheck="false">'
                b'<label for="nfc-present">On plate</label>'
                b'<input id="nfc-present" type="checkbox">'
                b"<script>"
                b"document.getElementById('nfc-present').addEventListener('change',function(){"
                b"var uid=document.getElementById('nfc-uid').value.trim();"
                b"fetch(this.checked?'/place/'+encodeURIComponent(uid):'/remove',{method:'POST'});"
                b"});"
                b"</script>"
                b"<p>POST /place/&lt;uid&gt; /remove /vol/up /vol/down /play /halt</p>"
                b'<form method="post" action="/remove"><button>remove</button></form>'
                b'<form method="post" action="/vol/up"><button>vol up</button></form>'
                b'<form method="post" action="/vol/down"><button>vol down</button></form>'
                b'<form method="post" action="/play"><button>play</button></form>'
                b'<form method="post" action="/halt"><button>halt</button></form>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
