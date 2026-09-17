import os
import sys
from collections.abc import Iterable
from pathlib import Path

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.catalog import run_catalog_ticks
from romini.composition.dashboard import DiskStorage, PathCatalog, create_dashboard, start_dashboard
from romini.composition.gpio import GpioLed, RpiGpioLedDriver
from romini.composition.http import start_sim_http
from romini.composition.inject import run_sim_lines
from romini.composition.loop import run_core_ticks
from romini.composition.nfc import FakeNfc, Nfc
from romini.composition.pi import MpvPlayer, Pn532Nfc
from romini.composition.sim import SimBox, load_sim_box_from_env
from romini.features.play_by_tag.place_figure import Player, StatusLed


class SilentPlayer:
    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        return

    def select(self, uid: str, path: str) -> None:
        return

    def selected_track(self) -> tuple[str, str] | None:
        return None

    def pause(self) -> None:
        return

    def stop(self) -> None:
        return

    def is_playing(self) -> bool:
        return False

    def playing_uid(self) -> str | None:
        return None

    def playing_path(self) -> str | None:
        return None


class SilentLed:
    def pulse(self) -> None:
        return

    def flash(self) -> None:
        return


def load_rpi_gpio() -> object:
    import RPi.GPIO as GPIO

    return GPIO


def default_led() -> StatusLed:
    if os.environ.get("ROMINI_PROFILE", "sim") != "pi":
        return SilentLed()
    try:
        gpio = load_rpi_gpio()
    except ImportError:
        return SilentLed()
    return GpioLed(RpiGpioLedDriver(gpio))


def default_nfc() -> Nfc:
    if os.environ.get("ROMINI_PROFILE", "sim") != "pi":
        return FakeNfc()
    try:
        from nfc import PN532_SPI
    except ImportError:
        try:
            from romini.composition.pn532_hat import PN532_SPI
        except ImportError:
            return FakeNfc()
    try:
        return Pn532Nfc(PN532_SPI(reset=20, cs=4))
    except Exception:
        return FakeNfc()


def default_ticks():
    while True:
        yield None


def serve_until_stopped(box: SimBox) -> None:
    http = getattr(box, "http", None)
    if http is not None:
        http.wait()
        return
    dashboard = getattr(box, "dashboard", None)
    if dashboard is not None:
        dashboard.wait()


def entry(*, player: Player | None = None, led: StatusLed | None = None) -> None:
    if os.environ.get("ROMINI_PROFILE", "sim") == "pi":
        main(player=player, led=led, nfc=default_nfc(), ticks=default_ticks())
        return
    box = run(player=player, led=led)
    serve_until_stopped(box)


def main(
    *,
    player: Player | None = None,
    led: StatusLed | None = None,
    lines: Iterable[str] | None = None,
    nfc: Nfc | None = None,
    ticks: Iterable[object] | None = None,
    catalog_ticks: Iterable[object] | None = None,
) -> SimBox:
    box = load_sim_box_from_env(
        player=player
        if player is not None
        else (MpvPlayer() if os.environ.get("ROMINI_PROFILE", "sim") == "pi" else SilentPlayer()),
        led=led if led is not None else default_led(),
    )
    port = os.environ.get("ROMINI_HTTP_PORT")
    if port is not None:
        box.http = start_sim_http(box, host="127.0.0.1", port=int(port))
    dash_port = os.environ.get("ROMINI_DASHBOARD_PORT")
    if dash_port is not None:
        data = Path(os.environ["ROMINI_DATA"])
        app = create_dashboard(
            storage=DiskStorage(data / "library"),
            assign_catalog=PathCatalog(data / "catalog.yaml"),
            settings=SqliteSettings(box.state),
            pad=box if os.environ.get("ROMINI_PROFILE", "sim") == "sim" else None,
            register=box,
            mixer=box.mixer,
        )
        box.dashboard = start_dashboard(
            app,
            host="0.0.0.0" if os.environ.get("ROMINI_PROFILE", "sim") == "pi" else "127.0.0.1",
            port=int(dash_port),
        )
    if lines is not None:
        run_sim_lines(box, lines)
    if nfc is not None and ticks is not None:
        run_core_ticks(box, nfc, data_dir=Path(os.environ["ROMINI_DATA"]), ticks=ticks)
    if catalog_ticks is not None:
        run_catalog_ticks(box, data_dir=Path(os.environ["ROMINI_DATA"]), ticks=catalog_ticks)
    return box


def run(*, player: Player | None = None, led: StatusLed | None = None) -> SimBox:
    return main(player=player, led=led, lines=sys.stdin)


if __name__ == "__main__":
    entry()
