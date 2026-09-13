from collections.abc import Iterable

from romini.composition.sim import SimBox


def apply_sim_line(box: SimBox, line: str) -> None:
    command, _, rest = line.strip().partition(" ")
    if command == "place":
        box.place(rest.strip())
        return
    if command == "lift":
        uid = box.player.playing_uid()
        if uid is None:
            return
        box.lift(uid, elapsed_sec=2.1, position_sec=0.0)


def run_sim_lines(box: SimBox, lines: Iterable[str]) -> None:
    for line in lines:
        if line.strip() == "quit":
            return
        apply_sim_line(box, line)
