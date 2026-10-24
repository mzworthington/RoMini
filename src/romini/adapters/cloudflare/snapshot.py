from datetime import datetime

from romini.features.play_by_tag.place_figure import PlayMode


class SnapshotCatalog:
    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self) -> str:
        return self._text

    def write_text(self, text: str) -> None:
        raise PermissionError("demo catalog is read only")


class SnapshotSettings:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def play_mode(self) -> PlayMode | None:
        raw = self._values.get("play_mode")
        if not raw:
            return None
        return PlayMode(raw)

    def sleep_at(self) -> datetime | None:
        return None

    def nfc_beep(self) -> bool:
        return self._values.get("nfc_beep", "on") != "off"


def snapshot_from_settings(rows: list[tuple[str, str]]) -> tuple[SnapshotCatalog, SnapshotSettings]:
    values = {key: value for key, value in rows}
    return SnapshotCatalog(values.get("catalog", "tracks: []\n")), SnapshotSettings(values)
