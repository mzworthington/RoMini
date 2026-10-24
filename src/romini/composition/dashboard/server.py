from os import environ
from threading import Thread
from time import sleep

import uvicorn
from fastapi import FastAPI

_RETRY_SEC = 5.0


class DashboardListener:
    def __init__(self, app: FastAPI, host: str, port: int) -> None:
        self._app = app
        self._host = host
        self._port = port
        self.port = port
        self._server: uvicorn.Server | None = None
        self._thread: Thread | None = None
        self._retry_at = 0.0
        self._ipv6: DashboardListener | None = None

    def ensure_serving(self, *, now: float, wait: bool = False) -> None:
        self._ensure(now, wait=wait)
        self._ensure_ipv6(now, wait=wait)

    def wait(self) -> None:
        if self._thread is not None:
            self._thread.join()

    def close(self) -> None:
        ipv6 = self._ipv6
        self._ipv6 = None
        if ipv6 is not None:
            ipv6.close()
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _ensure(self, now: float, *, wait: bool) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if now < self._retry_at:
            return
        self._retry_at = now + _RETRY_SEC
        self._open(wait=wait)

    def _ensure_ipv6(self, now: float, *, wait: bool) -> None:
        ipv6 = self._ipv6
        if ipv6 is None:
            return
        self._read_port()
        if self.port == 0:
            return
        ipv6._port = self.port
        ipv6._ensure(now, wait=wait)
        serving = self._server is not None and self._server.started
        ipv6_died = ipv6._thread is not None and not ipv6._thread.is_alive()
        if serving and ipv6_died:
            self._ipv6 = None

    def _open(self, *, wait: bool) -> None:
        config = uvicorn.Config(self._app, host=self._host, port=self._port, log_level="error")
        server = uvicorn.Server(config)
        thread = Thread(target=server.run, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        if not wait:
            return
        for _ in range(50):
            if server.started:
                break
            sleep(0.05)
        self._read_port()

    def _read_port(self) -> None:
        server = self._server
        if server is None or not server.started:
            return
        servers = getattr(server, "servers", None)
        if not servers or not servers[0].sockets:
            return
        bound = int(servers[0].sockets[0].getsockname()[1])
        self.port = bound
        self._port = bound


def start_dashboard(app: FastAPI, *, host: str, port: int) -> DashboardListener:
    if environ.get("ROMINI_PROFILE", "sim") == "sim" and host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("dashboard binds localhost only")

    listener = DashboardListener(app, host, port)
    if host == "0.0.0.0":
        listener._ipv6 = DashboardListener(app, "::", port)
    listener.ensure_serving(now=0, wait=True)
    return listener
