import os
import sys
from collections.abc import Iterable
from pathlib import Path

from romini.composition.catalog import run_catalog_ticks
from romini.composition.dashboard import DiskStorage, PathCatalog, create_dashboard, start_dashboard
from romini.composition.http import start_sim_http
from romini.composition.inject import run_sim_lines
from romini.composition.nfc import Nfc, run_nfc_ticks
from romini.composition.sim import SimBox, load_sim_box_from_env
from romini.composition.sqlite_settings import SqliteSettings
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
        player=player if player is not None else SilentPlayer(),
        led=led if led is not None else SilentLed(),
    )
    if lines is not None:
        run_sim_lines(box, lines)
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
        )
        box.dashboard = start_dashboard(app, host="127.0.0.1", port=int(dash_port))
    if nfc is not None and ticks is not None:
        run_nfc_ticks(box, nfc, ticks)
    if catalog_ticks is not None:
        run_catalog_ticks(box, data_dir=Path(os.environ["ROMINI_DATA"]), ticks=catalog_ticks)
    return box


def run(*, player: Player | None = None, led: StatusLed | None = None) -> SimBox:
    return main(player=player, led=led, lines=sys.stdin)


if __name__ == "__main__":
    run()
