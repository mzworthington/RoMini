import signal

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

    def off(self) -> None:
        self._driver.off()


class RpiGpioLedDriver:
    def __init__(self, gpio: object) -> None:
        self._gpio = gpio
        gpio.setmode(gpio.BCM)
        gpio.setup(GPIO_LED, gpio.OUT)
        gpio.output(GPIO_LED, gpio.HIGH)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, _signum: int, _frame: object) -> None:
        raise SystemExit(0)

    def pulse(self, pin: int) -> None:
        self._gpio.output(pin, self._gpio.HIGH)
        self._gpio.output(pin, self._gpio.LOW)
        self._gpio.output(pin, self._gpio.HIGH)

    def off(self) -> None:
        self._gpio.output(GPIO_LED, self._gpio.LOW)


def apply_gpio_press(box: SimBox, pin: int) -> None:
    if pin == GPIO_VOL_UP:
        on_volume_up(mixer=box.mixer)
        box.note("volume", f"Volume set to {box.mixer.level}", headline="Volume changed")
    if pin == GPIO_VOL_DOWN:
        on_volume_down(mixer=box.mixer)
        box.note("volume", f"Volume set to {box.mixer.level}", headline="Volume changed")
    if pin == GPIO_PLAY:
        was_playing = box.player.is_playing()
        on_play_pressed(player=box.player)
        box.mark_listening(was_playing)
        if box.player.is_playing():
            box.note("play", f"Played {box.player.playing_path()}", headline="Story playing")
        else:
            box.note("play", "Paused", headline="Playback paused")
    if pin == GPIO_HALT:
        on_halt_pressed(
            player=box.player,
            sessions=box.sessions,
            led=box.led,
            halt=box.halt,
            position_sec=0.0,
        )
        box.note("halt", "Halt", headline="Halt requested")
        box.close_listening()
