from typing import Protocol


class Player(Protocol):
    def is_playing(self) -> bool: ...

    def playing_uid(self) -> str | None: ...

    def playing_path(self) -> str | None: ...

    def position_sec(self) -> float: ...

    def pause(self) -> None: ...

    def play(self, path: str, *, position_sec: float, uid: str) -> None: ...


class QuietHold:
    def __init__(self) -> None:
        self.quiet = False
        self._armed = False
        self._held: tuple[str, str, float] | None = None

    def follow(self, *, open_switch: bool, player: Player) -> None:
        if not open_switch:
            self._armed = True
            self.quiet = False
            return
        if not self._armed:
            self.quiet = False
            return
        self._pause(player)
        self.quiet = True

    def _pause(self, player: Player) -> None:
        if not player.is_playing():
            return
        uid = player.playing_uid()
        path = player.playing_path()
        if uid is None or path is None:
            player.pause()
            return
        self._held = (uid, path, player.position_sec())
        player.pause()

    def resume(self, *, player: Player, present_uid: str | None, require_present: bool) -> None:
        held = self._held
        if self.quiet or held is None:
            return
        uid, path, position = held
        self._held = None
        if require_present and present_uid != uid:
            return
        if player.is_playing():
            return
        player.play(path, position_sec=position, uid=uid)
