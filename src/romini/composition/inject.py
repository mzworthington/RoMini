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
    if command == "place":
        box.place(rest.strip())
        return
    if command in {"lift", "remove"}:
        uid = box.player.playing_uid()
        if uid is None:
            return
        position = float(rest) if rest.strip() else 0.0
        box.lift(uid, elapsed_sec=2.1, position_sec=position)
        return
    if command == "vol" and rest.strip() == "up":
        on_volume_up(mixer=box.mixer)
        box.note("volume", f"Volume set to {box.mixer.level}", headline="Volume changed")
        return
    if command == "vol" and rest.strip() == "down":
        on_volume_down(mixer=box.mixer)
        box.note("volume", f"Volume set to {box.mixer.level}", headline="Volume changed")
        return
    if command == "play" and rest.strip() == "long":
        was_playing = box.player.is_playing()
        on_play_long_pressed(player=box.player)
        box.mark_listening(was_playing)
        box.note("play", "Restarted track", headline="Story restarted")
        return
    if command == "play":
        was_playing = box.player.is_playing()
        on_play_pressed(player=box.player)
        box.mark_listening(was_playing)
        if box.player.is_playing():
            box.note("play", f"Played {box.player.playing_path()}", headline="Story playing")
        else:
            box.note("play", "Paused", headline="Playback paused")
        return
    if command == "halt":
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


def run_sim_lines(box: SimBox, lines: Iterable[str]) -> None:
    for line in lines:
        if line.strip() == "quit":
            return
        apply_sim_line(box, line)
