from collections.abc import Callable

from romini.features.play_by_tag.place_figure import Mixer


class MemoryMixer:
    def __init__(self, *, level: int = 0, ceiling: int = 100) -> None:
        self.level = level
        self.ceiling = ceiling

    def set_level(self, level: int) -> None:
        self.level = level


class LiveMixer:
    def __init__(self, inner: Mixer, apply: Callable[[int], None]) -> None:
        self._inner = inner
        self._apply = apply

    @property
    def level(self) -> int:
        return self._inner.level

    @property
    def ceiling(self) -> int:
        return self._inner.ceiling

    def set_level(self, level: int) -> None:
        self._inner.set_level(level)
        self._apply(level)
