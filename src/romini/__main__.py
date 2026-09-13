import sys
from collections.abc import Iterable

from romini.composition.inject import run_sim_lines
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


def main(
    *,
    player: Player | None = None,
    led: StatusLed | None = None,
    lines: Iterable[str] | None = None,
) -> SimBox:
    box = load_sim_box_from_env(
        player=player if player is not None else SilentPlayer(),
        led=led if led is not None else SilentLed(),
    )
    if lines is not None:
        run_sim_lines(box, lines)
    return box


def run(*, player: Player | None = None, led: StatusLed | None = None) -> SimBox:
    return main(player=player, led=led, lines=sys.stdin)


if __name__ == "__main__":
    run()
