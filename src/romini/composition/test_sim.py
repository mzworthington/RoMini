from dataclasses import dataclass, field
from pathlib import Path

import pytest

from romini.adapters.sqlite.catalog import SqliteCatalog
from romini.adapters.sqlite.sessions import SqliteSessions
from romini.composition.catalog import poll_catalog, run_catalog_ticks
from romini.composition.gpio import (
    GPIO_HALT,
    GPIO_LED,
    GPIO_PLAY,
    GPIO_VOL_DOWN,
    GPIO_VOL_UP,
    GpioLed,
    apply_gpio_press,
)
from romini.composition.halt import LoggingHalt
from romini.composition.http import apply_sim_http, start_sim_http
from romini.composition.inject import apply_sim_line, run_sim_lines
from romini.composition.loop import run_core_ticks
from romini.composition.nfc import NFC_POLL_SEC, FakeNfc, poll_nfc, run_nfc_ticks
from romini.composition.pi import SystemdHalt
from romini.composition.sim import SimBox, load_sim_box, load_sim_box_from_env
from romini.features.play_by_tag.place_figure import PlayMode


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
class FakeLedDriver:
    pins: list[int] = field(default_factory=list)

    def pulse(self, pin: int) -> None:
        self.pins.append(pin)


def test_sim_place_plays_mapped_catalog_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )

    box.place("04aabbccddeeff")

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]
    assert led.pulses == 1


@dataclass
class FakeSessions:
    positions: dict[str, float] = field(default_factory=dict)

    def remember(self, uid: str, position_sec: float) -> None:
        self.positions[uid] = position_sec

    def position_for(self, uid: str) -> float | None:
        return self.positions.get(uid)


def test_sim_lift_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    box.place("04aabbccddeeff")
    box.lift("04aabbccddeeff", elapsed_sec=2.1, position_sec=14.5)

    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 14.5}


def test_load_sim_box_from_romini_data(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led)
    box.place("04aabbccddeeff")

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_load_sim_box_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box_from_env(player=player, led=led)
    box.place("04aabbccddeeff")

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_load_pi_box_from_env_uses_systemd_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")

    box = load_sim_box_from_env(player=FakePlayer(), led=FakeLed())

    assert isinstance(box.halt, SystemdHalt)


def test_sim_line_place_starts_the_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )

    apply_sim_line(box, "place 04aabbccddeeff")

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_line_lift_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift")

    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_sim_lines_stop_at_quit() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    run_sim_lines(box, ["place 04aabbccddeeff", "quit", "lift"])

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]
    assert player.pauses == 0


@dataclass
class FakeMixer:
    level: int
    ceiling: int

    def set_level(self, level: int) -> None:
        self.level = level


def test_sim_line_vol_up_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )
    box.mixer = mixer

    apply_sim_line(box, "vol up")

    assert mixer.level == 11


def test_sim_line_vol_down_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )
    box.mixer = mixer

    apply_sim_line(box, "vol down")

    assert mixer.level == 9


@dataclass
class FakeHalt:
    poweroffs: int = 0

    def poweroff(self) -> None:
        self.poweroffs += 1


def test_sim_line_halt_flashes_and_powers_off() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    halt = FakeHalt()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )
    box.halt = halt

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "halt")

    assert led.flashes == 1
    assert halt.poweroffs == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_sim_line_remove_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "remove")

    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_load_sim_box_vol_up_uses_mixer(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    mixer = FakeMixer(level=10, ceiling=100)
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led, mixer=mixer)
    apply_sim_line(box, "vol up")

    assert mixer.level == 11


def test_sim_http_place_starts_the_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )

    status = apply_sim_http(box, "POST", "/place/04aabbccddeeff")

    assert status == 204
    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_http_remove_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/remove")

    assert status == 204
    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_sim_http_vol_up_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        mixer=mixer,
    )

    status = apply_sim_http(box, "POST", "/vol/up")

    assert status == 204
    assert mixer.level == 11


def test_sim_http_vol_down_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        mixer=mixer,
    )

    status = apply_sim_http(box, "POST", "/vol/down")

    assert status == 204
    assert mixer.level == 9


def test_sim_http_halt_flashes_and_powers_off() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    halt = FakeHalt()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )
    box.halt = halt

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/halt")

    assert status == 204
    assert led.flashes == 1
    assert halt.poweroffs == 1


def test_sim_halt_logs_instead_of_powering_off() -> None:
    halt = LoggingHalt()

    halt.poweroff()

    assert halt.logs == ["halt"]


def test_load_sim_box_halt_logs_by_default(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()

    box = load_sim_box(data_dir=data, player=player, led=led, sessions=sessions)
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "halt")

    assert box.halt.logs == ["halt"]


def test_sim_http_listen_place_starts_the_track(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    led = FakeLed()
    box = load_sim_box(data_dir=data, player=player, led=led)
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        status = listener.post("/place/04aabbccddeeff")
    finally:
        listener.close()

    assert status == 204
    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_sim_http_listen_get_root_is_ok(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            status = resp.status
    finally:
        listener.close()

    assert status == 200


def test_sim_http_page_has_nfc_tag_input_and_on_plate_toggle(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            html = resp.read().decode()
    finally:
        listener.close()

    assert '<label for="nfc-uid">NFC tag</label>' in html
    assert '<input id="nfc-uid" name="uid" type="text"' in html
    assert '<label for="nfc-present">On plate</label>' in html
    assert '<input id="nfc-present" type="checkbox"' in html


def test_sim_http_page_uses_romini_brand(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            html = resp.read().decode()
    finally:
        listener.close()

    assert 'lang="en"' in html
    assert "<main" in html
    assert "<h1" in html
    assert "--story-coral: #FF6B6B" in html
    assert "Nunito" in html
    assert "Quicksand" in html


def test_sim_http_page_groups_figure_and_box_buttons(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            html = resp.read().decode()
    finally:
        listener.close()

    figure = html.index("<h2>Figure on the plate</h2>")
    buttons = html.index("<h2>Box buttons</h2>")
    assert figure < buttons
    assert 'id="nfc-uid"' in html[figure:buttons]
    assert 'id="nfc-present"' in html[figure:buttons]
    assert ">Lift<" in html[buttons:]
    assert ">Quieter<" in html[buttons:]
    assert ">Louder<" in html[buttons:]
    assert ">Play<" in html[buttons:]
    assert ">Halt<" in html[buttons:]
    assert 'action="/remove"' in html[buttons:]
    assert 'action="/vol/down"' in html[buttons:]
    assert 'action="/vol/up"' in html[buttons:]
    assert 'action="/play"' in html[buttons:]
    assert 'action="/halt"' in html[buttons:]


def test_sim_http_page_requires_a_uid_before_placing(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            html = resp.read().decode()
    finally:
        listener.close()

    script = html[html.index("<script>") : html.index("</script>")]
    assert "value.trim()" in script
    assert "if(this.checked&&!uid)" in script
    assert "this.checked=false" in script


def test_sim_http_page_tucks_http_injectors_into_details(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            html = resp.read().decode()
    finally:
        listener.close()

    assert "<details" in html
    assert "<summary>HTTP injectors</summary>" in html
    assert "POST /place/" in html
    assert html.index("<h2>Box buttons</h2>") < html.index("<details")


def test_sim_http_page_shows_the_storybox_mark(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            html = resp.read().decode()
    finally:
        listener.close()

    assert 'src="/mark.svg"' in html
    assert 'alt=""' in html
    assert 'href="/favicon.svg"' in html


def test_sim_http_serves_mark_and_favicon(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/mark.svg") as mark:
            mark_body = mark.read()
            mark_type = mark.headers.get_content_type()
        with urlopen(f"http://127.0.0.1:{listener.port}/favicon.svg") as icon:
            icon_body = icon.read()
            icon_type = icon.headers.get_content_type()
    finally:
        listener.close()

    assert mark_type == "image/svg+xml"
    assert icon_type == "image/svg+xml"
    assert mark_body.startswith(b"<svg")
    assert icon_body.startswith(b"<svg")


def test_sim_http_page_box_buttons_stay_on_the_page(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            html = resp.read().decode()
    finally:
        listener.close()

    assert "data-inject" in html
    assert "preventDefault" in html
    assert "fetch(form.action" in html


def test_sim_http_refuses_non_localhost(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    with pytest.raises(ValueError, match="localhost"):
        start_sim_http(box, host="0.0.0.0", port=0)


def test_sim_http_refuses_pi_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    with pytest.raises(ValueError, match="sim"):
        start_sim_http(box, host="127.0.0.1", port=0)


def test_load_sim_box_remembers_lift_by_default(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led)
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift")

    assert player.pauses == 1


def test_load_sim_box_vol_up_works_by_default(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    apply_sim_line(box, "vol up")

    assert box.mixer.level == 1


def test_sim_place_after_lift_resumes_remembered_position(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift 14.5")
    apply_sim_line(box, "place 04aabbccddeeff")

    path = str(stories / "frog-prince.mp3")
    assert player.plays == [(path, 0.0), (path, 14.5)]


def test_load_sim_box_persists_position_in_sqlite(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift 14.5")

    player2 = FakePlayer()
    box2 = load_sim_box(data_dir=data, player=player2, led=FakeLed())
    apply_sim_line(box2, "place 04aabbccddeeff")

    path = str(stories / "frog-prince.mp3")
    assert player2.plays == [(path, 14.5)]


def test_load_sim_box_persists_volume_in_sqlite(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    apply_sim_line(box, "vol up")

    box2 = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert box2.mixer.level == 1


def test_load_sim_box_applies_volume_to_mpv_player(tmp_path: Path) -> None:
    from romini.composition.pi import MpvPlayer

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    sent: list[str] = []
    player = MpvPlayer(ipc=sent.append)
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())
    apply_sim_line(box, "vol up")

    assert player.mixer is box.mixer
    assert sent == ['{"command":["set_property","volume",1]}']


def test_load_sim_box_persists_play_mode_in_sqlite(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    load_sim_box(
        data_dir=data,
        player=FakePlayer(),
        led=FakeLed(),
        play_mode=PlayMode.TAP,
    )

    box2 = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert box2.play_mode is PlayMode.TAP


def test_load_sim_box_writes_state_sqlite(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert (data / "state.sqlite").is_file()
    assert not (data / "sessions.db").exists()


def test_load_sim_box_applies_schema_version(tmp_path: Path) -> None:
    import sqlite3

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    conn = sqlite3.connect(data / "state.sqlite")
    assert conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone() == (1,)


def test_load_sim_box_unmaps_removed_yaml_uid_and_keeps_position(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    db = data / "state.sqlite"
    assert SqliteCatalog(db).track_for("04aabbccddeeff") == str(stories / "frog-prince.mp3")
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift 14.5")
    (data / "catalog.yaml").write_text("tracks: []\n")
    load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert SqliteCatalog(db).track_for("04aabbccddeeff") is None
    assert SqliteSessions(db).position_for("04aabbccddeeff") == 14.5


def test_catalog_mtime_tick_unmaps_uid_without_restart(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())
    previous_mtime = (data / "catalog.yaml").stat().st_mtime
    (data / "catalog.yaml").write_text("tracks: []\n")
    poll_catalog(box, data_dir=data, previous_mtime=previous_mtime)
    apply_sim_line(box, "place 04aabbccddeeff")

    assert player.plays == []


def test_catalog_ticks_unmaps_after_yaml_change(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())

    def ticks() -> object:
        yield None
        (data / "catalog.yaml").write_text("tracks: []\n")
        yield None

    run_catalog_ticks(box, data_dir=data, ticks=ticks())
    apply_sim_line(box, "place 04aabbccddeeff")

    assert player.plays == []


def test_gpio_vol_up_steps_the_mixer() -> None:
    mixer = FakeMixer(level=10, ceiling=100)
    box = SimBox(
        catalog_yaml="tracks: []\n",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: False,
        player=FakePlayer(),
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        mixer=mixer,
    )

    apply_gpio_press(box, GPIO_VOL_UP)

    assert mixer.level == 11


def test_gpio_vol_down_steps_the_mixer() -> None:
    mixer = FakeMixer(level=10, ceiling=100)
    box = SimBox(
        catalog_yaml="tracks: []\n",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: False,
        player=FakePlayer(),
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        mixer=mixer,
    )

    apply_gpio_press(box, GPIO_VOL_DOWN)

    assert mixer.level == 9


def test_gpio_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=FakeLed(),
        play_mode=PlayMode.TAP,
        assign_mode=False,
    )
    box.place("04aabbccddeeff")

    apply_gpio_press(box, GPIO_PLAY)

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_gpio_halt_flashes_and_powers_off() -> None:
    led = FakeLed()
    halt = FakeHalt()
    box = SimBox(
        catalog_yaml="tracks: []\n",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: False,
        player=FakePlayer(),
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        halt=halt,
    )

    apply_gpio_press(box, GPIO_HALT)

    assert led.flashes == 1
    assert halt.poweroffs == 1


def test_gpio_led_pulses_on_pin_27() -> None:
    driver = FakeLedDriver()
    led = GpioLed(driver)

    led.pulse()

    assert GPIO_LED == 27
    assert driver.pins == [27]


def test_core_ticks_sleep_nfc_poll_interval(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    sleeps: list[float] = []

    run_core_ticks(
        box,
        FakeNfc(),
        data_dir=data,
        ticks=[None, None],
        sleep=sleeps.append,
    )

    assert sleeps == [NFC_POLL_SEC, NFC_POLL_SEC]


def test_sim_line_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=FakeLed(),
        play_mode=PlayMode.TAP,
        assign_mode=False,
    )

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "play")

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_http_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=FakeLed(),
        play_mode=PlayMode.TAP,
        assign_mode=False,
    )

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/play")

    assert status == 204
    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_line_play_long_restarts_the_track() -> None:
    player = FakePlayer()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "play long")

    assert player.plays == [
        ("/var/lib/romini/library/stories/frog-prince.mp3", 0.0),
        ("/var/lib/romini/library/stories/frog-prince.mp3", 0.0),
    ]


def test_nfc_poll_places_when_uid_appears() -> None:
    player = FakePlayer()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )
    nfc = FakeNfc(uid="04aabbccddeeff")

    poll_nfc(box, nfc)

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_nfc_poll_lifts_when_uid_disappears() -> None:
    player = FakePlayer()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )
    nfc = FakeNfc(uid="04aabbccddeeff")

    seen = poll_nfc(box, nfc)
    nfc.clear()
    poll_nfc(box, nfc, previous_uid=seen)

    assert player.pauses == 1


def test_nfc_ticks_lift_after_uid_clears() -> None:
    player = FakePlayer()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )
    nfc = FakeNfc(uid="04aabbccddeeff")

    def ticks() -> None:
        yield None
        nfc.clear()
        yield None

    run_nfc_ticks(box, nfc, ticks())

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]
    assert player.pauses == 1


def test_nfc_poll_interval_is_250_ms() -> None:
    assert NFC_POLL_SEC == 0.25


def test_sim_place_in_register_mode_lists_tag_and_does_not_play(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    led = FakeLed()
    box = load_sim_box(data_dir=data, player=player, led=led, assign_mode=True)

    box.place("04deadbeef0001")

    assert player.plays == []
    assert led.pulses == 1
    catalog = (data / "catalog.yaml").read_text()
    assert "04deadbeef0001" in catalog
    assert "tags:" in catalog


def test_core_ticks_leave_register_mode_after_idle(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed(), assign_mode=True)

    run_core_ticks(
        box,
        FakeNfc(),
        data_dir=data,
        ticks=[None] * 240,
        sleep=lambda _: None,
    )

    assert box.assign_mode is False
