from typing import Protocol

READY_EARCON_PATH = "romini/ready.wav"


class EarconPlayer(Protocol):
    def play_earcon(self, path: str) -> None: ...


class BootLed(Protocol):
    def animate(self) -> None: ...

    def become_steady(self) -> None: ...


def on_power_restored(*, player: EarconPlayer, led: BootLed, figure_present: bool) -> None:
    led.animate()
    player.play_earcon(READY_EARCON_PATH)
    led.become_steady()
    if figure_present:
        return
