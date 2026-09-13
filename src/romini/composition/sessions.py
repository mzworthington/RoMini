class MemorySessions:
    def __init__(self) -> None:
        self.positions: dict[str, float] = {}

    def remember(self, uid: str, position_sec: float) -> None:
        self.positions[uid] = position_sec

    def position_for(self, uid: str) -> float | None:
        return self.positions.get(uid)
