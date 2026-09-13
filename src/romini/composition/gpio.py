from romini.composition.sim import SimBox
from romini.features.play_by_tag.place_figure import on_volume_up

GPIO_VOL_UP = 23


def apply_gpio_press(box: SimBox, pin: int) -> None:
    if pin == GPIO_VOL_UP:
        on_volume_up(mixer=box.mixer)
