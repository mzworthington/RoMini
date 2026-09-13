class MemoryMixer:
    def __init__(self, *, level: int = 0, ceiling: int = 100) -> None:
        self.level = level
        self.ceiling = ceiling

    def set_level(self, level: int) -> None:
        self.level = level
