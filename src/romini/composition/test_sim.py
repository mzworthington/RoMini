from pathlib import Path

import pytest

from romini.adapters.sqlite.catalog import SqliteCatalog
from romini.adapters.sqlite.schema import SCHEMA_VERSION
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
from romini.composition.nfc import NFC_ABSENT_TICKS, NFC_POLL_SEC, FakeNfc, poll_nfc, run_nfc_ticks
from romini.composition.pi import SystemdHalt
from romini.composition.sim import load_sim_box, load_sim_box_from_env
from romini.fakes import (
    FROG_REL_PATH,
    FROG_UID,
    SIM_LIBRARY_ROOT,
    FakeHalt,
    FakeLed,
    FakeLedDriver,
    FakeMixer,
    FakePlayer,
    FakeSessions,
    fetch_sim_root_html,
    frog_sim_box,
    frog_story_path,
    write_empty_data,
    write_frog_data,
)
from romini.features.play_by_tag.place_figure import PlayMode


def test_sim_place_plays_the_connect_chirp(tmp_path: Path) -> None:
    class ChirpPlayer(FakePlayer):
        def __init__(self) -> None:
            super().__init__()
            self.chirps: list[str] = []

        def play_earcon(self, path: str) -> None:
            self.chirps.append(path)

    player = ChirpPlayer()
    box = load_sim_box(data_dir=write_frog_data(tmp_path), player=player, led=FakeLed())

    box.place(FROG_UID)

    assert player.chirps == ["romini/connect.wav"]


def test_sim_place_skips_the_connect_chirp_when_nfc_beep_is_off(tmp_path: Path) -> None:
    class ChirpPlayer(FakePlayer):
        def __init__(self) -> None:
            super().__init__()
            self.chirps: list[str] = []

        def play_earcon(self, path: str) -> None:
            self.chirps.append(path)

    player = ChirpPlayer()
    box = load_sim_box(data_dir=write_frog_data(tmp_path), player=player, led=FakeLed())
    box.settings.remember_nfc_beep(False)

    box.place(FROG_UID)

    assert player.chirps == []
    assert player.plays


def test_sim_place_plays_mapped_catalog_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led)

    box.place(FROG_UID)

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]
    assert led.pulses == 1


def test_sim_place_records_the_audit_log() -> None:
    from romini.features.audit.memory import MemoryAuditLog

    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led)
    box.audit = MemoryAuditLog()

    box.place(FROG_UID)

    summaries = [entry.summary for entry in box.audit.recent()]
    assert summaries == [f"Played {SIM_LIBRARY_ROOT}/{FROG_REL_PATH}"]


def test_sim_place_opens_todays_listening_while_the_story_plays() -> None:
    from romini.features.listening.log import MemoryPlayLog

    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led)
    box.listening = MemoryPlayLog()

    box.place(FROG_UID)

    intervals = box.listening.intervals()
    assert len(intervals) == 1
    assert intervals[0].ended_at is None


def test_sim_unknown_figure_records_the_code_in_the_audit_log() -> None:
    from romini.features.audit.memory import MemoryAuditLog

    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led)
    box.audit = MemoryAuditLog()

    box.place("04deadbeef")

    summaries = [entry.summary for entry in box.audit.recent()]
    assert summaries == ["No story for 04deadbeef"]


def test_sim_volume_and_halt_record_the_audit_log() -> None:
    from romini.features.audit.memory import MemoryAuditLog

    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led, mixer=FakeMixer(level=4, ceiling=100), halt=FakeHalt())
    box.audit = MemoryAuditLog()

    apply_sim_line(box, "vol up")
    apply_sim_line(box, "halt")

    assert [entry.summary for entry in box.audit.recent()] == ["Halt", "Volume set to 5"]


def test_sim_lift_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = frog_sim_box(player, led, sessions=sessions)

    box.place(FROG_UID)
    box.lift(FROG_UID, elapsed_sec=2.1, position_sec=14.5)

    assert player.pauses == 1
    assert sessions.positions == {FROG_UID: 14.5}


def test_sim_halt_closes_todays_listening() -> None:
    from romini.composition.inject import apply_sim_line
    from romini.features.listening.log import MemoryPlayLog

    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led, mixer=FakeMixer(level=4, ceiling=100), halt=FakeHalt())
    box.listening = MemoryPlayLog()
    box.place(FROG_UID)

    apply_sim_line(box, "halt")

    assert box.listening.intervals()[0].ended_at is not None


def test_sim_play_line_closes_todays_listening() -> None:
    from romini.composition.inject import apply_sim_line
    from romini.features.listening.log import MemoryPlayLog

    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led)
    box.listening = MemoryPlayLog()
    box.place(FROG_UID)

    apply_sim_line(box, "play")

    assert box.listening.intervals()[0].ended_at is not None


def test_sim_lift_closes_todays_listening() -> None:
    from romini.features.listening.log import MemoryPlayLog

    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led, sessions=FakeSessions())
    box.listening = MemoryPlayLog()

    box.place(FROG_UID)
    box.lift(FROG_UID, elapsed_sec=2.1, position_sec=14.5)

    intervals = box.listening.intervals()
    assert len(intervals) == 1
    assert intervals[0].ended_at is not None


def test_load_sim_box_from_romini_data(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led)
    box.place(FROG_UID)

    assert player.plays == [(str(frog_story_path(data)), 0.0)]
    assert box.listening.intervals()[0].ended_at is None


def test_load_sim_box_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box_from_env(player=player, led=led)
    box.place(FROG_UID)

    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_load_pi_box_from_env_uses_systemd_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")

    box = load_sim_box_from_env(player=FakePlayer(), led=FakeLed())

    assert isinstance(box.halt, SystemdHalt)


def test_sim_line_place_starts_the_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led)

    apply_sim_line(box, "place 04aabbccddeeff")

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]


def test_sim_line_lift_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = frog_sim_box(player, led, sessions=sessions)

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift")

    assert player.pauses == 1
    assert sessions.positions == {FROG_UID: 0.0}


def test_sim_lines_stop_at_quit() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = frog_sim_box(player, led, sessions=sessions)

    run_sim_lines(box, ["place 04aabbccddeeff", "quit", "lift"])

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]
    assert player.pauses == 0


def test_sim_line_vol_up_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = frog_sim_box(player, led)
    box.mixer = mixer

    apply_sim_line(box, "vol up")

    assert mixer.level == 11


def test_sim_line_vol_down_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = frog_sim_box(player, led)
    box.mixer = mixer

    apply_sim_line(box, "vol down")

    assert mixer.level == 9


def test_sim_line_halt_flashes_and_powers_off() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    halt = FakeHalt()
    box = frog_sim_box(player, led, sessions=sessions)
    box.halt = halt

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "halt")

    assert led.flashes == 1
    assert halt.poweroffs == 1
    assert sessions.positions == {FROG_UID: 0.0}


def test_sim_line_remove_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = frog_sim_box(player, led, sessions=sessions)

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "remove")

    assert player.pauses == 1
    assert sessions.positions == {FROG_UID: 0.0}


def test_load_sim_box_vol_up_uses_mixer(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    mixer = FakeMixer(level=10, ceiling=100)
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led, mixer=mixer)
    apply_sim_line(box, "vol up")

    assert mixer.level == 11


def test_sim_http_place_starts_the_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led)

    status = apply_sim_http(box, "POST", "/place/04aabbccddeeff")

    assert status == 204
    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]


def test_sim_http_tap_starts_the_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = frog_sim_box(player, led, play_mode=PlayMode.TAP)

    status = apply_sim_http(box, "POST", "/tap/04aabbccddeeff")

    assert status == 204
    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]
    assert player.is_playing() is True


def test_sim_http_same_figure_tap_pauses_playback() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed(), play_mode=PlayMode.TAP)

    apply_sim_http(box, "POST", "/tap/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/tap/04aabbccddeeff")

    assert status == 204
    assert player.is_playing() is False
    assert player.pauses == 1


def test_sim_http_remove_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = frog_sim_box(player, led, sessions=sessions)

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/remove")

    assert status == 204
    assert player.pauses == 1
    assert sessions.positions == {FROG_UID: 0.0}


def test_sim_http_vol_up_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = frog_sim_box(player, led, mixer=mixer)

    status = apply_sim_http(box, "POST", "/vol/up")

    assert status == 204
    assert mixer.level == 11


def test_sim_http_vol_down_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
    box = frog_sim_box(player, led, mixer=mixer)

    status = apply_sim_http(box, "POST", "/vol/down")

    assert status == 204
    assert mixer.level == 9


def test_sim_http_halt_flashes_and_powers_off() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    halt = FakeHalt()
    box = frog_sim_box(player, led, sessions=sessions)
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
    data = write_frog_data(tmp_path)
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()

    box = load_sim_box(data_dir=data, player=player, led=led, sessions=sessions)
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "halt")

    assert box.halt.logs == ["halt"]


def test_sim_http_listen_place_starts_the_track(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    player = FakePlayer()
    led = FakeLed()
    box = load_sim_box(data_dir=data, player=player, led=led)
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        status = listener.post("/place/04aabbccddeeff")
    finally:
        listener.close()

    assert status == 204
    assert player.plays == [(str(frog_story_path(data)), 0.0)]


def test_sim_http_listen_get_root_is_ok(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        with urlopen(f"http://127.0.0.1:{listener.port}/") as resp:
            status = resp.status
    finally:
        listener.close()

    assert status == 200


def test_sim_http_page_has_nfc_tag_input_and_on_plate_toggle(tmp_path: Path) -> None:

    html = fetch_sim_root_html(tmp_path)

    assert '<label for="nfc-uid">NFC tag</label>' in html
    assert '<input id="nfc-uid" name="uid" type="text"' in html
    assert '<label for="nfc-present">On plate</label>' in html
    assert '<input id="nfc-present" type="checkbox"' in html


def test_sim_http_page_has_a_tap_button(tmp_path: Path) -> None:

    html = fetch_sim_root_html(tmp_path)

    assert 'id="nfc-tap"' in html
    assert ">Tap<" in html
    script = html[html.index("<script>") : html.index("</script>")]
    assert "/tap/" in script


def test_sim_http_page_tap_skips_when_the_figure_is_already_on_the_plate(tmp_path: Path) -> None:

    html = fetch_sim_root_html(tmp_path)

    script = html[html.index("<script>") : html.index("</script>")]
    tap = script[script.index("nfc-tap") :]
    checked_at = tap.index("checked")
    tap_post_at = tap.index("/tap/")
    assert checked_at < tap_post_at
    assert "return" in tap[checked_at:tap_post_at]


def test_sim_http_page_uses_romini_brand(tmp_path: Path) -> None:

    html = fetch_sim_root_html(tmp_path)

    assert 'lang="en"' in html
    assert "<main" in html
    assert "<h1" in html
    assert "#D97706" in html
    assert "#F9F7F2" in html
    assert "Plus Jakarta Sans" in html
    assert "Nunito" not in html
    assert "Quicksand" not in html


def test_sim_http_page_does_not_fetch_fonts_from_the_internet(tmp_path: Path) -> None:
    html = fetch_sim_root_html(tmp_path)

    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


def test_sim_http_page_groups_figure_and_box_buttons(tmp_path: Path) -> None:

    html = fetch_sim_root_html(tmp_path)

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

    html = fetch_sim_root_html(tmp_path)

    script = html[html.index("<script>") : html.index("</script>")]
    assert "value.trim()" in script
    assert "if(this.checked&&!uid)" in script
    assert "this.checked=false" in script


def test_sim_http_page_tucks_http_injectors_into_details(tmp_path: Path) -> None:

    html = fetch_sim_root_html(tmp_path)

    assert "<details" in html
    assert "<summary>HTTP injectors</summary>" in html
    assert "POST /place/" in html
    assert "/tap/" in html
    assert html.index("<h2>Box buttons</h2>") < html.index("<details")


def test_sim_http_page_shows_the_storybox_mark(tmp_path: Path) -> None:

    html = fetch_sim_root_html(tmp_path)

    assert 'src="/mark.svg"' in html
    assert 'alt=""' in html
    assert 'href="/favicon.svg"' in html


def test_sim_http_serves_mark_and_favicon(tmp_path: Path) -> None:
    from urllib.request import urlopen

    data = write_empty_data(tmp_path)
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

    html = fetch_sim_root_html(tmp_path)

    assert "data-inject" in html
    assert "preventDefault" in html
    assert "fetch(form.action" in html


def test_sim_http_refuses_non_localhost(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    with pytest.raises(ValueError, match="localhost"):
        start_sim_http(box, host="0.0.0.0", port=0)


def test_sim_http_refuses_pi_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = write_frog_data(tmp_path)
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    with pytest.raises(ValueError, match="sim"):
        start_sim_http(box, host="127.0.0.1", port=0)


def test_load_sim_box_remembers_lift_by_default(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led)
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift")

    assert player.pauses == 1


def test_load_sim_box_vol_up_works_by_default(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    apply_sim_line(box, "vol up")

    assert box.mixer.level == 1


def test_sim_place_after_lift_resumes_remembered_position(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift 14.5")
    apply_sim_line(box, "place 04aabbccddeeff")

    path = str(frog_story_path(data))
    assert player.plays == [(path, 0.0), (path, 14.5)]


def test_load_sim_box_persists_position_in_sqlite(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift 14.5")

    player2 = FakePlayer()
    box2 = load_sim_box(data_dir=data, player=player2, led=FakeLed())
    apply_sim_line(box2, "place 04aabbccddeeff")

    path = str(frog_story_path(data))
    assert player2.plays == [(path, 14.5)]


def test_load_sim_box_persists_volume_in_sqlite(tmp_path: Path) -> None:
    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    apply_sim_line(box, "vol up")

    box2 = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert box2.mixer.level == 1


def test_load_sim_box_applies_volume_to_mpv_player(tmp_path: Path) -> None:
    from romini.composition.pi import MpvPlayer

    data = write_empty_data(tmp_path)
    sent: list[str] = []
    player = MpvPlayer(ipc=sent.append)
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())
    apply_sim_line(box, "vol up")

    assert player.mixer is box.mixer
    assert sent == ['{"command":["set_property","volume",1]}']


def test_load_sim_box_persists_play_mode_in_sqlite(tmp_path: Path) -> None:
    data = write_empty_data(tmp_path)
    load_sim_box(
        data_dir=data,
        player=FakePlayer(),
        led=FakeLed(),
        play_mode=PlayMode.TAP,
    )

    box2 = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert box2.play_mode is PlayMode.TAP


def test_load_sim_box_writes_state_sqlite(tmp_path: Path) -> None:
    data = write_empty_data(tmp_path)
    load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert (data / "state.sqlite").is_file()
    assert not (data / "sessions.db").exists()


def test_load_sim_box_applies_schema_version(tmp_path: Path) -> None:
    import sqlite3

    data = write_empty_data(tmp_path)
    load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    conn = sqlite3.connect(data / "state.sqlite")
    assert conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone() == (SCHEMA_VERSION,)


def test_load_sim_box_unmaps_removed_yaml_uid_and_keeps_position(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    db = data / "state.sqlite"
    assert SqliteCatalog(db).track_for(FROG_UID) == str(frog_story_path(data))
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift 14.5")
    (data / "catalog.yaml").write_text("tracks: []\n")
    load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    assert SqliteCatalog(db).track_for(FROG_UID) is None
    assert SqliteSessions(db).position_for(FROG_UID) == 14.5


def test_catalog_mtime_tick_unmaps_uid_without_restart(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())
    previous_mtime = (data / "catalog.yaml").stat().st_mtime
    (data / "catalog.yaml").write_text("tracks: []\n")
    poll_catalog(box, data_dir=data, previous_mtime=previous_mtime)
    apply_sim_line(box, "place 04aabbccddeeff")

    assert player.plays == []


def test_catalog_reload_records_the_audit_log(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    previous_mtime = (data / "catalog.yaml").stat().st_mtime
    (data / "catalog.yaml").write_text("tracks: []\n")

    poll_catalog(box, data_dir=data, previous_mtime=previous_mtime)

    assert "Updated catalog" in [entry.summary for entry in box.audit.recent()]


def test_catalog_ticks_unmaps_after_yaml_change(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
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
    box = frog_sim_box(FakePlayer(), FakeLed(), empty=True, mixer=mixer)

    apply_gpio_press(box, GPIO_VOL_UP)

    assert mixer.level == 11


def test_gpio_vol_down_steps_the_mixer() -> None:
    mixer = FakeMixer(level=10, ceiling=100)
    box = frog_sim_box(FakePlayer(), FakeLed(), empty=True, mixer=mixer)

    apply_gpio_press(box, GPIO_VOL_DOWN)

    assert mixer.level == 9


def test_gpio_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed(), play_mode=PlayMode.TAP)
    box.place(FROG_UID)

    apply_gpio_press(box, GPIO_PLAY)

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]


def test_gpio_halt_flashes_and_powers_off() -> None:
    led = FakeLed()
    halt = FakeHalt()
    box = frog_sim_box(FakePlayer(), led, empty=True, halt=halt)

    apply_gpio_press(box, GPIO_HALT)

    assert led.flashes == 1
    assert halt.poweroffs == 1


def test_gpio_presses_record_the_audit_log() -> None:
    from romini.features.audit.memory import MemoryAuditLog

    mixer = FakeMixer(level=10, ceiling=100)
    box = frog_sim_box(FakePlayer(), FakeLed(), empty=True, mixer=mixer, halt=FakeHalt())
    box.audit = MemoryAuditLog()

    apply_gpio_press(box, GPIO_VOL_UP)
    apply_gpio_press(box, GPIO_HALT)

    assert [entry.summary for entry in box.audit.recent()] == ["Halt", "Volume set to 11"]


def test_gpio_led_pulses_on_pin_27() -> None:
    driver = FakeLedDriver()
    led = GpioLed(driver)

    led.pulse()

    assert GPIO_LED == 27
    assert driver.pins == [27]


def test_core_ticks_keep_the_field_up_while_waiting_for_a_figure(tmp_path: Path) -> None:
    class RestingNfc(FakeNfc):
        def __init__(self) -> None:
            super().__init__()
            self.rests = 0

        def rest(self) -> None:
            self.rests += 1

    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    nfc = RestingNfc()
    sleeps: list[float] = []

    run_core_ticks(box, nfc, data_dir=data, ticks=[None, None], sleep=sleeps.append)

    assert sleeps == [NFC_POLL_SEC, NFC_POLL_SEC]
    assert nfc.rests == 0


def test_core_ticks_idle_the_cpu_and_radio_when_the_shelf_is_quiet(tmp_path: Path) -> None:
    class Power:
        def __init__(self) -> None:
            self.calls: list[tuple[bool, bool]] = []

        def apply(self, *, playing: bool, radio_sleep: bool) -> None:
            self.calls.append((playing, radio_sleep))

    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    power = Power()
    box.host_power = power

    run_core_ticks(box, FakeNfc(), data_dir=data, ticks=[None], sleep=lambda _: None)

    assert power.calls == [(False, True)]


def test_core_ticks_sleep_nfc_poll_interval(tmp_path: Path) -> None:
    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    sleeps: list[float] = []

    run_core_ticks(
        box,
        FakeNfc(uid="04idlefast"),
        data_dir=data,
        ticks=[None, None],
        sleep=sleeps.append,
    )

    assert sleeps == [NFC_POLL_SEC, NFC_POLL_SEC]


def test_core_ticks_leave_the_status_light_on_when_the_shelf_sleeps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("romini.composition.loop.SHELF_HALT_SEC", 0.5)
    order: list[str] = []

    class Lamp(FakeLed):
        def off(self) -> None:
            order.append("off")

    class Halt(FakeHalt):
        def poweroff(self) -> None:
            order.append("poweroff")
            super().poweroff()

    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=Lamp())
    box.halt = Halt()

    run_core_ticks(box, FakeNfc(), data_dir=data, ticks=[None, None], sleep=lambda _: None)

    assert order == ["poweroff"]


def test_core_ticks_power_off_when_the_shelf_has_been_idle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("romini.composition.loop.SHELF_HALT_SEC", 0.5)
    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    halt = FakeHalt()
    box.halt = halt

    run_core_ticks(box, FakeNfc(), data_dir=data, ticks=[None, None], sleep=lambda _: None)

    assert halt.poweroffs == 1


def test_core_ticks_keep_the_shelf_awake_while_a_story_plays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("romini.composition.loop.SHELF_HALT_SEC", 0.5)
    data = write_empty_data(tmp_path)
    player = FakePlayer()
    player.play("story.mp3", position_sec=0.0, uid="04aabbccddeeff")
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())
    halt = FakeHalt()
    box.halt = halt

    run_core_ticks(box, FakeNfc(), data_dir=data, ticks=[None, None, None], sleep=lambda _: None)

    assert halt.poweroffs == 0


def test_core_ticks_power_off_when_bedtime_is_due(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())
    halt = FakeHalt()
    box.halt = halt
    box.settings.remember_sleep_at(datetime.now(UTC) - timedelta(minutes=1))

    run_core_ticks(box, FakeNfc(), data_dir=data, ticks=[None], sleep=lambda _: None)

    assert halt.poweroffs == 1
    assert box.settings.sleep_at() is None


def test_sim_line_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed(), play_mode=PlayMode.TAP)

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "play")

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]


def test_sim_http_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed(), play_mode=PlayMode.TAP)

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/play")

    assert status == 204
    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]


def test_sim_line_play_long_restarts_the_track() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed())

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "play long")

    assert player.plays == [
        (f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0),
        (f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0),
    ]


def test_nfc_poll_places_when_uid_appears() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed())
    nfc = FakeNfc(uid=FROG_UID)

    poll_nfc(box, nfc)

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]


def test_nfc_one_missed_poll_does_not_retrigger_tap_playback() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed(), play_mode=PlayMode.TAP)
    nfc = FakeNfc(uid=FROG_UID)

    seen = poll_nfc(box, nfc)
    nfc.clear()
    seen = poll_nfc(box, nfc, previous_uid=seen)
    nfc = FakeNfc(uid=FROG_UID)
    poll_nfc(box, nfc, previous_uid=seen)

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]
    assert player.pauses == 0
    assert player.is_playing() is True


def test_nfc_poll_lifts_when_uid_disappears() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed())
    nfc = FakeNfc(uid=FROG_UID)

    seen = poll_nfc(box, nfc)
    nfc.clear()
    absent = [0]
    for _ in range(NFC_ABSENT_TICKS):
        seen = poll_nfc(box, nfc, previous_uid=seen, absent_ticks=absent)

    assert player.pauses == 1


def test_nfc_ticks_lift_after_uid_clears() -> None:
    player = FakePlayer()
    box = frog_sim_box(player, FakeLed())
    nfc = FakeNfc(uid=FROG_UID)

    def ticks() -> None:
        yield None
        nfc.clear()
        yield None
        yield None
        yield None

    run_nfc_ticks(box, nfc, ticks())

    assert player.plays == [(f"{SIM_LIBRARY_ROOT}/{FROG_REL_PATH}", 0.0)]
    assert player.pauses == 1


def test_nfc_poll_interval_is_250_ms() -> None:
    assert NFC_POLL_SEC == 0.25


def test_sim_place_in_register_mode_lists_tag_and_does_not_play(tmp_path: Path) -> None:
    data = write_frog_data(tmp_path)
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
    data = write_empty_data(tmp_path)
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed(), assign_mode=True)

    run_core_ticks(
        box,
        FakeNfc(),
        data_dir=data,
        ticks=[None] * 240,
        sleep=lambda _: None,
    )

    assert box.assign_mode is False
