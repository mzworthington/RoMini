from collections.abc import Iterable

from romini.composition.sim import SimBox
from romini.features.play_by_tag.place_figure import (
    on_halt_pressed,
    on_play_long_pressed,
    on_play_pressed,
    on_volume_down,
    on_volume_up,
)


def apply_sim_line(box: SimBox, line: str) -> None:
    command, _, rest = line.strip().partition(" ")
    handler = _COMMANDS.get(command)
    if handler is None:
        return
    handler(box, rest.strip())


def _place(box: SimBox, rest: str) -> None:
    box.place(rest)


def _lift(box: SimBox, rest: str) -> None:
    uid = box.player.playing_uid()
    if uid is None:
        return
    position = float(rest) if rest else 0.0
    box.lift(uid, elapsed_sec=2.1, position_sec=position)


def _volume(box: SimBox, rest: str) -> None:
    if rest == "up":
        on_volume_up(mixer=box.mixer)
    elif rest == "down":
        on_volume_down(mixer=box.mixer)
    else:
        return
    box.note("volume", f"Volume set to {box.mixer.level}", headline="Volume changed")


def _play(box: SimBox, rest: str) -> None:
    if rest == "long":
        _restart(box)
        return
    _toggle(box)


def _restart(box: SimBox) -> None:
    was_playing = box.player.is_playing()
    on_play_long_pressed(player=box.player)
    box.mark_listening(was_playing)
    box.note("play", "Restarted track", headline="Story restarted")


def _toggle(box: SimBox) -> None:
    was_playing = box.player.is_playing()
    on_play_pressed(player=box.player)
    box.mark_listening(was_playing)
    if box.player.is_playing():
        box.note("play", f"Played {box.player.playing_path()}", headline="Story playing")
        return
    box.note("play", "Paused", headline="Playback paused")


def _halt(box: SimBox, _rest: str) -> None:
    if box.sessions is None:
        return
    on_halt_pressed(
        player=box.player,
        sessions=box.sessions,
        led=box.led,
        halt=box.halt,
        position_sec=0.0,
    )
    box.note("halt", "Halt", headline="Halt requested")
    box.close_listening()


_COMMANDS = {
    "place": _place,
    "lift": _lift,
    "remove": _lift,
    "vol": _volume,
    "play": _play,
    "halt": _halt,
}


def run_sim_lines(box: SimBox, lines: Iterable[str]) -> None:
    for line in lines:
        if line.strip() == "quit":
            return
        apply_sim_line(box, line)
