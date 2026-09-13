class LoggingHalt:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def poweroff(self) -> None:
        self.logs.append("halt")
