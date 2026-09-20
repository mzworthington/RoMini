import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from romini.__main__ import main, run
from romini.composition.nfc import FakeNfc
from romini.composition.pi import MpvPlayer
from romini.fakes import (
    FROG_UID,
    FakeLed,
    FakePlayer,
    frog_story_path,
    write_empty_data,
    write_frog_data,
)


@dataclass
class FakeBattery:
    percent: int


def test_romini_core_main_does_not_start_http_unless_port_set(tmp_path: Path, monkeypatch) -> None:
    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        assert getattr(box, "http", None) is None
        assert getattr(box, "dashboard", None) is None
    finally:
        http = getattr(box, "http", None)
        if http is not None:
            http.close()
        dashboard = getattr(box, "dashboard", None)
        if dashboard is not None:
            dashboard.close()


def test_romini_core_main_loads_sim_from_env(tmp_path: Path, monkeypatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    box = main(player=player, led=led)
    box.place(FROG_UID)

    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_romini_core_main_runs_sim_lines(tmp_path: Path, monkeypatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    main(player=player, led=led, lines=["place 04aabbccddeeff", "quit"])

    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_romini_core_run_reads_stdin(tmp_path: Path, monkeypatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setattr(
        "romini.__main__.sys.stdin",
        StringIO("place 04aabbccddeeff\nquit\n"),
    )
    player = FakePlayer()
    led = FakeLed()

    run(player=player, led=led)

    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_romini_core_main_starts_sim_http(tmp_path: Path, monkeypatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_HTTP_PORT", "0")
    player = FakePlayer()
    led = FakeLed()

    box = main(player=player, led=led)
    try:
        status = box.http.post("/place/04aabbccddeeff")
    finally:
        box.http.close()

    assert status == 204
    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_romini_core_starts_sim_http_before_stdin_lines(tmp_path: Path, monkeypatch) -> None:
    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_HTTP_PORT", "0")
    order: list[str] = []

    def start_http(box, *, host: str, port: int):
        order.append("http")

        class Listener:
            port = 0

            def close(self) -> None:
                return

        return Listener()

    def lines() -> object:
        order.append("lines")
        yield "quit"

    monkeypatch.setattr("romini.__main__.start_sim_http", start_http)
    main(player=FakePlayer(), led=FakeLed(), lines=lines())

    assert order == ["http", "lines"]


def test_romini_core_main_starts_dashboard(tmp_path: Path, monkeypatch) -> None:
    import json
    from urllib.request import urlopen

    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/storage") as resp:
            body = json.loads(resp.read().decode())
    finally:
        box.dashboard.close()

    assert "free_bytes" in body


def test_romini_core_dashboard_place_starts_the_track(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import Request, urlopen

    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    player = FakePlayer()

    box = main(player=player, led=FakeLed())
    try:
        req = Request(f"http://127.0.0.1:{box.dashboard.port}/place/04aabbccddeeff", method="POST", data=b"")
        with urlopen(req) as resp:
            status = resp.status
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert status == 200
    assert "Place" in body
    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_romini_core_main_runs_nfc_ticks(tmp_path: Path, monkeypatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    main(
        player=player,
        led=led,
        nfc=FakeNfc(uid=FROG_UID),
        ticks=[None],
    )

    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_romini_core_main_runs_catalog_ticks(tmp_path: Path, monkeypatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    def ticks() -> object:
        yield None
        (data / "catalog.yaml").write_text("tracks: []\n")
        yield None

    box = main(player=player, led=led, catalog_ticks=ticks())
    box.place(FROG_UID)

    assert player.plays == []


def test_romini_core_main_nfc_ticks_poll_catalog(tmp_path: Path, monkeypatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    def ticks() -> object:
        yield None
        (data / "catalog.yaml").write_text("tracks: []\n")
        yield None

    box = main(player=player, led=led, nfc=FakeNfc(), ticks=ticks())
    box.place(FROG_UID)

    assert player.plays == []


def test_romini_core_main_pi_profile_defaults_mpv_player(tmp_path: Path, monkeypatch) -> None:
    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")

    box = main(led=FakeLed())

    assert isinstance(box.player, MpvPlayer)


def test_romini_core_main_pi_dashboard_binds_lan(tmp_path: Path, monkeypatch) -> None:
    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    hosts: list[str] = []

    class Listener:
        port = 80

        def close(self) -> None:
            return

    def start(app, *, host: str, port: int) -> Listener:
        hosts.append(host)
        return Listener()

    monkeypatch.setattr("romini.__main__.start_dashboard", start)
    main(led=FakeLed())

    assert hosts == ["0.0.0.0"]


def test_romini_core_main_pi_defaults_gpio_led(tmp_path: Path, monkeypatch) -> None:
    from romini.composition.gpio import GpioLed

    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")

    class Gpio:
        BCM = 11
        OUT = 0
        HIGH = 1
        LOW = 0

        def setmode(self, mode: int) -> None:
            return

        def setup(self, pin: int, mode: int) -> None:
            return

        def output(self, pin: int, value: int) -> None:
            return

    monkeypatch.setattr("romini.__main__.load_rpi_gpio", lambda: Gpio())
    box = main()

    assert isinstance(box.led, GpioLed)


def test_romini_core_entry_on_pi_runs_nfc_ticks(tmp_path: Path, monkeypatch) -> None:
    from romini.__main__ import entry
    from romini.composition.nfc import FakeNfc

    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    monkeypatch.setattr("romini.__main__.default_nfc", lambda: FakeNfc(uid=FROG_UID))
    monkeypatch.setattr("romini.__main__.default_ticks", lambda: [None])
    player = FakePlayer()

    entry(player=player, led=FakeLed())

    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_romini_core_entry_keeps_serving_after_stdin_eof(tmp_path: Path, monkeypatch) -> None:
    from threading import Event, Thread
    from time import sleep

    from romini.__main__ import entry
    from romini.composition.http import start_sim_http

    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_HTTP_PORT", "0")
    monkeypatch.setattr("romini.__main__.sys.stdin", StringIO(""))

    ready = Event()
    listeners: list = []

    def start(box, *, host: str, port: int):
        listener = start_sim_http(box, host=host, port=port)
        listeners.append(listener)
        ready.set()
        return listener

    monkeypatch.setattr("romini.__main__.start_sim_http", start)
    worker = Thread(target=lambda: entry(player=FakePlayer(), led=FakeLed()), daemon=True)
    worker.start()
    assert ready.wait(timeout=2)
    sleep(0.2)

    assert worker.is_alive()
    listeners[0].close()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_romini_core_dashboard_has_register_form(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import urlopen

    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/figures") as resp:
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert 'action="/register-mode"' in body


def test_romini_core_dashboard_has_volume_form(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import urlopen

    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/settings") as resp:
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert "<h2>Volume</h2>" in body
    assert 'action="/volume"' in body
    assert "of 100" in body


def test_romini_core_dashboard_shows_play_in_the_audit_log(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import urlopen

    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        box.place(FROG_UID)
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/settings") as resp:
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert "<h2>Audit log</h2>" in body
    assert f"Played {frog_story_path(data)}" in body


def test_romini_core_dashboard_shows_ups_hat_charge(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    monkeypatch.setattr("romini.__main__.open_ups_hat", lambda: FakeBattery(64))

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/") as resp:
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert "64% charged" in body


def test_romini_core_dashboard_keeps_story_notes(tmp_path: Path, monkeypatch) -> None:
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        payload = urlencode({"outline": "trains, then a station"}).encode()
        req = Request(
            f"http://127.0.0.1:{box.dashboard.port}/stories",
            data=payload,
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            urlopen(req)
        except HTTPError as error:
            if error.code not in {302, 303}:
                raise
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/write") as resp:
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert ">trains, then a station</textarea>" in body
    assert "<legend>Characters</legend>" in body


def test_romini_core_dashboard_reads_box_env_for_studio_keys(tmp_path: Path, monkeypatch) -> None:
    import romini.__main__ as core

    seen: dict[str, object] = {}
    real = core.create_dashboard

    def wrap(**kwargs: object):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(core, "create_dashboard", wrap)
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        assert box.dashboard is not None
    finally:
        box.dashboard.close()

    assert seen["secrets"] == data / "studio.env"
    assert seen["box_secrets"] == Path("/etc/romini/env")
    assert seen["stories"] == data / "stories"
    assert seen["characters"] == data / "characters"


def test_romini_core_dashboard_reads_the_live_player(tmp_path: Path, monkeypatch) -> None:
    import romini.__main__ as core

    seen: dict[str, object] = {}
    real = core.create_dashboard

    def wrap(**kwargs: object):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(core, "create_dashboard", wrap)
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    player = FakePlayer()

    box = main(player=player, led=FakeLed())
    try:
        assert box.dashboard is not None
    finally:
        box.dashboard.close()

    assert seen["player"] is player


def test_default_nfc_on_pi_uses_pn532_hat_spi(monkeypatch) -> None:
    from types import ModuleType

    from romini.__main__ import default_nfc
    from romini.composition.pi import Pn532Nfc

    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    monkeypatch.setitem(sys.modules, "nfc", ModuleType("nfc"))
    hat = ModuleType("romini.composition.pn532_hat")
    built: list[object] = []

    class PN532_SPI:
        def __init__(self, *, reset: int = 20, cs: int = 4, debug: bool = False) -> None:
            built.append({"reset": reset, "cs": cs, "debug": debug})

        def SAM_configuration(self) -> None:
            return None

        def read_passive_target(self, timeout: float | None = None) -> bytes | None:
            return None

    hat.PN532_SPI = PN532_SPI
    monkeypatch.setitem(sys.modules, "romini.composition.pn532_hat", hat)

    nfc = default_nfc()

    assert isinstance(nfc, Pn532Nfc)
    assert built == [{"reset": 20, "cs": 4, "debug": False}]
    assert nfc.read_uid() is None


def test_sim_silent_player_reports_playing_after_play() -> None:
    from romini.__main__ import SilentPlayer

    player = SilentPlayer()
    player.play("/library/frog.mp3", position_sec=14.0, uid="04aabbccddeeff")

    assert player.is_playing() is True
    assert player.playing_uid() == "04aabbccddeeff"
    assert player.playing_path() == "/library/frog.mp3"
    assert player.position_sec() == 14.0


def test_sim_silent_player_records_when_playback_started() -> None:
    from datetime import datetime

    from romini.__main__ import SilentPlayer

    player = SilentPlayer(clock=lambda: datetime(2026, 9, 19, 22, 33))
    player.play("/library/frog.mp3", position_sec=0.0, uid="04aabbccddeeff")

    assert player.started_at() == datetime(2026, 9, 19, 22, 33)


def test_sim_dashboard_home_shows_now_playing_after_place(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import urlopen

    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    monkeypatch.setenv("ROMINI_HTTP_PORT", "0")

    box = main(led=FakeLed())
    try:
        status = box.http.post("/place/04aabbccddeeff")
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/") as resp:
            body = resp.read().decode()
    finally:
        box.http.close()
        box.dashboard.close()

    assert status == 204
    assert 'aria-label="Now playing"' in body
    assert "The Frog Prince" in body
    assert ">Pause<" in body
    assert ">Play<" not in body.replace("start play", "")
