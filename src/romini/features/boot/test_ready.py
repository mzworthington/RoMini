from dataclasses import dataclass, field

from romini.features.boot.ready import READY_EARCON_PATH, on_power_restored


@dataclass
class FakeEarconPlayer:
    plays: list[str] = field(default_factory=list)

    def play_earcon(self, path: str) -> None:
        self.plays.append(path)


@dataclass
class FakeBootLed:
    animated: bool = False
    steady: bool = False

    def animate(self) -> None:
        self.animated = True

    def become_steady(self) -> None:
        self.steady = True


def test_power_returns_with_no_figure_plays_ready_earcon() -> None:
    player = FakeEarconPlayer()
    led = FakeBootLed()

    on_power_restored(player=player, led=led, figure_present=False)

    assert led.animated is True
    assert player.plays == [READY_EARCON_PATH]
    assert led.steady is True
