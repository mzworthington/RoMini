from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlopen

from romini.composition.http import start_sim_http
from romini.composition.sim import SimBox, load_sim_box
from romini.features.play_by_tag.place_figure import PlayMode

FROG_UID = "04aabbccddeeff"
FROG_REL_PATH = "stories/frog-prince.mp3"
FROG_TITLE = "The Frog Prince"
FROG_CATALOG_YAML = f'tracks:\n  - uid: "{FROG_UID}"\n    path: "{FROG_REL_PATH}"\n    title: "{FROG_TITLE}"\n'
EMPTY_CATALOG_YAML = "tracks: []\n"
SIM_LIBRARY_ROOT = "/var/lib/romini/library"


@dataclass
class FakePlayer:
    plays: list[tuple[str, float]] = field(default_factory=list)
    pauses: int = 0
    stops: int = 0
    selected: tuple[str, str] | None = None
    _playing: bool = False
    _uid: str | None = None
    _path: str | None = None

    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        self.plays.append((path, position_sec))
        self._playing = True
        self._uid = uid
        self._path = path

    def select(self, uid: str, path: str) -> None:
        self.selected = (uid, path)

    def selected_track(self) -> tuple[str, str] | None:
        return self.selected

    def pause(self) -> None:
        self.pauses += 1
        self._playing = False

    def stop(self) -> None:
        self.stops += 1
        self._playing = False
        self._uid = None

    def is_playing(self) -> bool:
        return self._playing

    def playing_uid(self) -> str | None:
        return self._uid

    def playing_path(self) -> str | None:
        return self._path


@dataclass
class FakeLed:
    pulses: int = 0
    flashes: int = 0

    def pulse(self) -> None:
        self.pulses += 1

    def flash(self) -> None:
        self.flashes += 1


@dataclass
class FakeSessions:
    positions: dict[str, float] = field(default_factory=dict)

    def remember(self, uid: str, position_sec: float) -> None:
        self.positions[uid] = position_sec

    def position_for(self, uid: str) -> float | None:
        return self.positions.get(uid)


@dataclass
class FakeMixer:
    level: int
    ceiling: int

    def set_level(self, level: int) -> None:
        self.level = level


@dataclass
class FakeHalt:
    poweroffs: int = 0

    def poweroff(self) -> None:
        self.poweroffs += 1


@dataclass
class FakeLedDriver:
    pins: list[int] = field(default_factory=list)

    def pulse(self, pin: int) -> None:
        self.pins.append(pin)


def write_empty_data(tmp_path: Path) -> Path:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text(EMPTY_CATALOG_YAML)
    return data


def write_frog_data(tmp_path: Path) -> Path:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(FROG_CATALOG_YAML)
    return data


def frog_story_path(data: Path) -> Path:
    return data / "library" / FROG_REL_PATH


def frog_sim_box(
    player: FakePlayer,
    led: FakeLed,
    *,
    sessions: FakeSessions | None = None,
    mixer: FakeMixer | None = None,
    halt: FakeHalt | None = None,
    play_mode: PlayMode = PlayMode.PRESENCE,
    assign_mode: bool = False,
    empty: bool = False,
) -> SimBox:
    catalog = EMPTY_CATALOG_YAML if empty else FROG_CATALOG_YAML
    exists = (lambda path: False) if empty else (lambda path: path == FROG_REL_PATH)
    return SimBox(
        catalog_yaml=catalog,
        library_root=SIM_LIBRARY_ROOT,
        audio_exists=exists,
        player=player,
        led=led,
        play_mode=play_mode,
        assign_mode=assign_mode,
        sessions=sessions,
        mixer=mixer,
        halt=halt,
    )


def load_empty_sim(tmp_path: Path) -> SimBox:
    return load_sim_box(data_dir=write_empty_data(tmp_path), player=FakePlayer(), led=FakeLed())


def fetch_sim_root_html(tmp_path: Path) -> str:
    listener = start_sim_http(load_empty_sim(tmp_path), host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            return resp.read().decode()
    finally:
        listener.close()
