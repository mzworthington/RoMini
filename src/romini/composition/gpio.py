from romini.composition.sim import SimBox
from romini.features.play_by_tag.place_figure import (
    on_halt_pressed,
    on_play_pressed,
    on_volume_down,
    on_volume_up,
)

GPIO_HALT = 17
GPIO_VOL_DOWN = 22
GPIO_VOL_UP = 23
GPIO_PLAY = 24
GPIO_LED = 27


class GpioLed:
    def __init__(self, driver: object) -> None:
        self._driver = driver

    def pulse(self) -> None:
        self._driver.pulse(GPIO_LED)

    def flash(self) -> None:
        self._driver.pulse(GPIO_LED)


def apply_gpio_press(box: SimBox, pin: int) -> None:
    if pin == GPIO_VOL_UP:
        on_volume_up(mixer=box.mixer)
    if pin == GPIO_VOL_DOWN:
        on_volume_down(mixer=box.mixer)
    if pin == GPIO_PLAY:
        on_play_pressed(player=box.player)
    if pin == GPIO_HALT:
        on_halt_pressed(
            player=box.player,
            sessions=box.sessions,
            led=box.led,
            halt=box.halt,
            position_sec=0.0,
        )
