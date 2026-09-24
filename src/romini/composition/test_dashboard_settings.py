import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard import create_dashboard


@dataclass
class FakeBattery:
    percent: int | None
    volts: float | None = None
    flow: str | None = None


@dataclass
class FakeStorage:
    free_bytes: int
    files: dict[str, bytes] = field(default_factory=dict)
    total_bytes: int | None = None
    root: str = ""

    def put(self, filename: str, audio: bytes) -> None:
        self.files[filename] = audio

    def paths(self) -> list[str]:
        return sorted(self.files)

    def get(self, filename: str) -> bytes | None:
        return self.files.get(filename)


@dataclass
class FakeNotices:
    messages: list[str] = field(default_factory=list)

    def tell(self, message: str) -> None:
        self.messages.append(message)


@dataclass
class FakeCatalog:
    paths: list[str] = field(default_factory=list)

    def list_track(self, filename: str) -> None:
        self.paths.append(filename)


@dataclass
class FakeMixer:
    level: int
    ceiling: int = 100

    def set_level(self, level: int) -> None:
        self.level = level


@dataclass
class FakeDrafter:
    script: str
    calls: list[dict[str, str]] = field(default_factory=list)

    def draft(
        self,
        *,
        title: str,
        characters: str,
        interests: str,
        outline: str,
        duration_seconds: int = 10,
    ) -> str:
        self.calls.append(
            {
                "title": title,
                "characters": characters,
                "interests": interests,
                "outline": outline,
                "duration_seconds": str(duration_seconds),
            }
        )
        return self.script


@dataclass
class FakeSpeech:
    audio: bytes
    calls: list[dict[str, str]] = field(default_factory=list)

    def speak(self, *, text: str, voice_id: str) -> bytes:
        self.calls.append({"text": text, "voice_id": voice_id})
        return self.audio


def test_dashboard_pi_profile_may_bind_lan(monkeypatch) -> None:
    from fastapi import FastAPI

    from romini.composition.dashboard import start_dashboard

    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    listener = start_dashboard(FastAPI(), host="0.0.0.0", port=0)
    try:
        assert listener.port > 0
    finally:
        listener.close()


def test_dashboard_settings_shows_volume_when_mixer_is_wired() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
    home = client.get("/").text
    html = client.get("/settings").text

    assert "<h2>Volume</h2>" not in home
    assert 'name="step"' not in home
    assert "<h2>Volume</h2>" in html
    assert "10 of 100" in html
    assert 'action="/volume"' in html
    assert 'name="step" value="down"' in html
    assert 'name="step" value="up"' in html
    assert ">Quieter<" in html
    assert ">Louder<" in html
    assert 'id="volume-level"' in html
    assert 'for="volume-level"' in html
    assert 'type="range"' in html
    assert 'max="100"' in html
    assert 'value="10"' in html
    assert "power button" in html.lower()


def test_dashboard_hardware_shows_percent_volume_studio_keys_and_box_facts() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                mixer=FakeMixer(level=10),
                battery=FakeBattery(percent=72),
            )
        )
        .get("/settings")
        .text
    )

    assert "<h2>Studio keys</h2>" in html
    assert "software ceiling" not in html.lower()
    assert "10 of 100" in html
    assert "72% charged" in html
    assert "1.0 KB free" in html
    assert 'for="volume-level"' in html
    assert 'for="gemini-key"' in html
    assert 'for="play_mode"' in html
    assert html.count('class="card"') >= 4


def test_dashboard_hardware_lays_care_out_as_pods() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )

    assert 'class="hw-care"' in html
    care = html.split('class="hw-care"', 1)[1]
    assert care.index("Studio keys") < care.index("Play mode")
    assert care.index("Audit log") > care.index("Play mode")
    assert "Firmware" not in care


def test_dashboard_hardware_studio_puts_box_facts_above_the_care_cards() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=72),
            )
        )
        .get("/settings")
        .text
    )
    facts = html.split('class="studio"', 1)[1].split('class="hw-care"', 1)[0]

    assert "Charged" in facts
    assert ">72%<" in facts
    assert "Free on the box" in facts


def test_dashboard_settings_shows_the_pn532_on_spi() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "SPI0" in html
    assert "BCM 4" in html
    assert "BCM 20" in html
    assert "250 ms" in html
    assert "NTAG203" in html
    assert "0x24" not in html
    assert "HiFiBerry" not in html


def test_dashboard_settings_shows_the_analogue_player() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )

    assert "ALSA Headphones" in html
    assert "mpv.sock" in html
    assert "Cap 100" in html


def test_dashboard_settings_shows_host_load_memory_and_disk(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "romini",
            "address": "192.168.1.140",
            "cpu_temp": "42°C",
            "load": "0.24",
            "memory": "612 MB / 3891 MB",
            "uptime": "4d 12h",
            "wifi": "Not reported",
            "model": "Not reported",
        },
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(
                    free_bytes=4 * 1024 * 1024 * 1024,
                    total_bytes=28 * 1024 * 1024 * 1024,
                    root="/var/lib/romini",
                )
            )
        )
        .get("/settings")
        .text
    )

    assert "42°C" in html
    assert "Load 0.24" in html
    assert "612 MB / 3891 MB" in html
    assert "4.0 GB free" in html
    assert "28.0 GB" in html
    assert "/var/lib/romini" in html


def test_dashboard_host_card_draws_ram_and_disk_meters(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "romini",
            "address": "192.168.1.140",
            "cpu_temp": "42°C",
            "load": "0.24",
            "memory": "612 MB / 3891 MB",
            "uptime": "4d 12h",
            "wifi": "Not reported",
            "model": "Not reported",
        },
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(
                    free_bytes=4 * 1024 * 1024 * 1024,
                    total_bytes=28 * 1024 * 1024 * 1024,
                    root="/var/lib/romini",
                )
            )
        )
        .get("/settings")
        .text
    )
    card = html.split("Host node", 1)[1].split("<h2>Reader</h2>", 1)[0]

    assert "42°C" in card
    assert "Load 0.24" in card
    assert "612 MB / 3891 MB" in card
    assert 'style="width: 16%"' in card
    assert 'style="width: 86%"' in card
    assert "/var/lib/romini" in card


def test_dashboard_subsystem_cards_use_the_hardware_labels() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=84, volts=4.12, flow="charging"),
                mixer=FakeMixer(level=40, ceiling=75),
            )
        )
        .get("/settings")
        .text
    )

    assert "Proximity sensor" in html
    assert "Acoustic pipeline" in html
    assert "Telemetry unit" in html
    assert "SPI0" in html
    assert "NTAG203" in html
    assert "ALSA Headphones" in html
    assert "mpv.sock" in html
    assert "UPS HAT (D)" in html
    assert "21700" in html
    assert "4.12 V" in html
    assert "HiFiBerry" not in html
    assert "18650" not in html


def test_dashboard_hardware_skips_the_summary_strip() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), battery=FakeBattery(percent=72)))
        .get("/settings")
        .text
    )

    assert 'class="metrics"' not in html
    assert "Free on the box" in html
    assert "Charged" in html
    assert ">72%<" in html


def test_dashboard_network_card_names_remote_access() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    card = (
        html.split("<h2>Network</h2>", 1)[0].rsplit("<section", 1)[1]
        + html.split("<h2>Network</h2>", 1)[1].split("</section>", 1)[0]
    )

    assert "Remote access" in card
    assert "Not reported" in card
    assert "sudo nmtui" in card


def test_dashboard_hardware_keeps_labels_clear_of_their_values() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024, root="/var/lib/romini"),
                mixer=FakeMixer(level=10),
            )
        )
        .get("/settings")
        .text
    )
    host = html.split("Host node", 1)[1].split("<h2>Reader</h2>", 1)[0]
    player = html.split("Acoustic pipeline", 1)[1].split("<h2>Pack</h2>", 1)[0]
    care = html.split('class="hw-care"', 1)[1]
    pair = care.split('class="hw-pair"', 1)[1].split('id="audit"', 1)[0]

    assert 'class="mount"' in host
    assert host.index(">Mount<") < host.index("/var/lib/romini")
    assert player.index("</p>") < player.index("Analogue jack")
    assert "Studio keys" in pair
    assert "Play mode" in pair
    assert "Audit log" not in pair


def test_dashboard_settings_names_the_board_the_host_reports(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "storybox",
            "address": "10.0.0.8",
            "cpu_temp": "Not reported",
            "load": "Not reported",
            "memory": "Not reported",
            "uptime": "1h 2m",
            "wifi": "Not reported",
            "model": "Raspberry Pi 5 Model B Rev 1.0",
        },
    )
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    head = html.split('class="page-head"', 1)[1].split('class="page-actions"', 1)[0]
    host = html.split("<h2>Host</h2>", 1)[1].split("<h2>Reader</h2>", 1)[0]

    assert "Raspberry Pi 5 Model B Rev 1.0" in head
    assert "Raspberry Pi 5 Model B Rev 1.0" in host
    assert "Raspberry Pi 4 Model B" not in html
    assert "4GB RAM" not in head


def test_dashboard_settings_names_the_box_on_the_title_line(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "romini",
            "address": "192.168.1.140",
            "cpu_temp": "42°C",
            "load": "0.24",
            "memory": "612 MB / 3891 MB",
            "uptime": "4d 12h",
            "wifi": "Not reported",
            "model": "Not reported",
        },
    )
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    head = html.split('class="page-head"', 1)[1].split('class="page-actions"', 1)[0]

    assert "romini.local" in head
    assert "192.168.1.140" in head
    assert "4d 12h" in head
    assert "System Healthy" not in html


def test_dashboard_mdns_name_keeps_a_single_local_suffix(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "Matthews-MacBook-Air.local",
            "address": "10.5.0.2",
            "cpu_temp": "Not reported",
            "load": "1.70",
            "memory": "Not reported",
            "uptime": "Not reported",
            "wifi": "Not reported",
            "model": "Not reported",
        },
    )
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "Matthews-MacBook-Air.local.local" not in html
    assert "Matthews-MacBook-Air.local (10.5.0.2)" in html
    assert "ssh Matthews-MacBook-Air.local\n" in html


def test_dashboard_hardware_owns_the_chime_and_bedtime_sleep(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            mixer=FakeMixer(level=40, ceiling=75),
            settings=SqliteSettings(tmp_path / "state.sqlite"),
        )
    )
    home = client.get("/").text
    hardware = client.get("/settings").text
    safety = hardware.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]

    assert 'aria-label="Raspberry Pi safety"' not in home
    assert 'action="/safety/beep"' not in home
    assert 'action="/safety/sleep"' not in home
    assert "Volume cap" in home
    assert 'action="/volume"' in safety
    assert 'action="/safety/beep"' in safety
    assert 'action="/safety/sleep"' in safety
    assert "Sleep in 30m" in safety
    assert "dB" not in safety


def test_dashboard_hardware_puts_the_plate_on_the_keys_row_and_firmware_full_width() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )
    studio = html.split('class="studio"', 1)[1]
    main = studio.split('class="hw-main"', 1)[1].split('class="hw-side"', 1)[0]
    pair = studio.split('class="hw-pair"', 1)[1].split('id="audit"', 1)[0]
    columns = html.split(".hw-pair {", 1)[1].split("}", 1)[0]

    assert "firmware-update" not in main
    assert studio.index('class="hw-side"') < studio.index('id="firmware-update"')
    assert studio.index('id="firmware-update"') < studio.index('class="hw-care"')
    assert pair.index("Studio keys") < pair.index("Play mode")
    assert pair.index("Play mode") < pair.index('aria-label="On the plate"')
    assert "Audit log" not in pair
    assert "1fr 1fr 1fr" in columns
    assert "align-items: stretch" in columns


def test_dashboard_hardware_puts_safety_beside_the_network() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )
    left = html.split('class="hw-main"', 1)[1].split('class="hw-side"', 1)[0]
    side = html.split('class="hw-side"', 1)[1].split('id="firmware-update"', 1)[0]

    assert "Parental audio safety" in left
    assert "Firmware" not in left
    assert "Network" in side
    assert 'aria-label="On the plate"' not in side


def test_dashboard_hardware_safety_and_network_share_the_row_height() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )
    rule = html.split(".hw-main > section,", 1)[1].split("}", 1)[0]

    assert rule.strip().startswith(".hw-side > section")
    assert "flex: 1" in rule


def test_dashboard_hardware_puts_chime_and_sleep_on_one_row() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )
    safety = html.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]
    tools = safety.split('class="safety-tools"', 1)[1]
    rule = html.split(".safety-tools {", 1)[1].split("}", 1)[0]

    assert tools.index('action="/safety/beep"') < tools.index("Sleep in 30m")
    assert "grid-template-columns: 1fr 1fr" in rule
    assert "align-items: stretch" in rule


def test_dashboard_hardware_plate_matches_the_keys_row() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    rule = html.split(".hw-pair > section {", 1)[1].split("}", 1)[0]

    assert "height: 100%" in rule


def test_dashboard_settings_names_the_ups_hat() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), battery=FakeBattery(percent=72)))
        .get("/settings")
        .text
    )

    assert "UPS HAT (D)" in html
    assert "21700" in html
    assert "18650" not in html


def test_dashboard_settings_shows_pack_voltage() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=72, volts=4.12),
            )
        )
        .get("/settings")
        .text
    )

    assert "4.12 V" in html
    assert "Pack voltage is not reported" not in html


def test_dashboard_settings_shows_whether_the_pack_is_charging() -> None:
    from fastapi.testclient import TestClient

    def page(flow: str) -> str:
        return (
            TestClient(
                create_dashboard(
                    storage=FakeStorage(free_bytes=1024),
                    battery=FakeBattery(percent=72, flow=flow),
                )
            )
            .get("/settings")
            .text
        )

    assert "Charging" in page("charging")
    assert "Discharging" in page("discharging")


def test_dashboard_hardware_names_the_figure_on_the_plate(tmp_path: Path) -> None:
    from datetime import datetime

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

        def position_sec(self) -> float:
            return 0.0

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog-prince.mp3"\n'
        '    title: "The Frog Prince"\n'
        "tags:\n"
        "  - uid: 04aabbccddeeff\n"
        "    name: Frog\n"
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=Playing(),
            )
        )
        .get("/settings")
        .text
    )
    dock = html.split('aria-label="On the plate"', 1)[1].split("</section>", 1)[0]

    assert ">Frog<" in dock
    assert "The Frog Prince" in dock


def test_dashboard_dock_shows_the_tag_and_safety_uses_panels(tmp_path: Path) -> None:
    from datetime import datetime

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

        def position_sec(self) -> float:
            return 0.0

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog-prince.mp3"\n'
        '    title: "The Frog Prince"\n'
        "tags:\n"
        "  - uid: 04aabbccddeeff\n"
        "    name: Frog\n"
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=Playing(),
                mixer=FakeMixer(level=40, ceiling=75),
                settings=SqliteSettings(tmp_path / "state.sqlite"),
            )
        )
        .get("/settings")
        .text
    )
    dock = html.split('aria-label="On the plate"', 1)[1].split("</section>", 1)[0]
    safety = html.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]

    assert "Figure present" in dock
    assert "04aabbccddeeff" in dock
    assert safety.count('class="safety-panel"') == 2
    assert safety.index('class="safety-panel"') < safety.index('action="/volume"')
    assert "Sleep in 30m" in safety.split('class="safety-panel"', 2)[2]
    assert 'class="safety-row"' in safety
    assert "dB" not in safety


def test_dashboard_hardware_shows_when_the_update_check_skipped(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    status = tmp_path / "update-check.json"
    status.write_text('{"when": "22 September 2026 at 10:04", "result": "skipped"}')
    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), update_status=status)).get("/settings").text
    )

    assert "Last checked 22 September 2026 at 10:04." in html
    assert "skipped the install because a story was playing" in html
    assert "Story was playing" in html
    assert "romini-update.timer" in html
    assert "systemctl" not in html
    assert 'action="/update"' not in html


def test_dashboard_settings_shows_the_firmware_update_center(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    status = tmp_path / "update-check.json"
    status.write_text('{"when": "22 September 2026 at 03:15", "result": "current"}')
    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), update_status=status)).get("/settings").text
    )
    center = html.split('id="firmware-update"', 1)[1].split("</section>", 1)[0]

    assert "Firmware &amp; OTA Update Center" in center
    assert "Official GitHub wheel distribution channel" in center
    assert "Up to date" in center
    assert "Current Build" in center
    assert "Update Channel" in center
    assert "mzworthington/RoMini" in center
    assert "Last Check Timer" in center
    assert "22 September 2026 at 03:15" in center
    assert "romini-update.timer" in center
    assert "Check for Updates Now" in center
    assert "Recent Installation Ledger" in center
    assert "The player is already up to date." in center


def test_dashboard_update_channel_stays_inside_its_card() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    center = html.split('id="firmware-update"', 1)[1]
    channel_value = center.split("Update Channel", 1)[1].split("</div>", 1)[0]
    columns = html.split(".firmware-facts {", 1)[1].split("}", 1)[0]
    channel = html.split(".firmware-facts dd.channel {", 1)[1].split("}", 1)[0]
    value = html.split(".firmware-facts dd {", 1)[1].split("}", 1)[0]

    assert 'class="channel"' in channel_value

    assert "minmax(18rem, 1fr)" in columns
    assert "white-space: nowrap" in channel
    assert "overflow-wrap: anywhere" not in value


def test_dashboard_firmware_center_shows_the_update_and_refresh_icons() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    center = html.split('id="firmware-update"', 1)[1].split("</section>", 1)[0]
    head = center.split("<h2", 1)[0]
    check = center.split("Check for Updates Now", 1)[0]

    assert 'class="firmware-mark"' in head
    assert 'class="refresh-mark"' in check


def test_dashboard_check_for_updates_starts_the_updater() -> None:
    from fastapi.testclient import TestClient

    class Updates:
        def __init__(self) -> None:
            self.checked = False

        def check(self) -> None:
            self.checked = True

    updates = Updates()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), updates=updates))
    html = client.get("/settings").text

    assert 'action="/system/update"' in html
    response = client.post("/system/update", follow_redirects=False)

    assert response.status_code == 303
    assert updates.checked is True
    assert "Update check started" in client.get("/settings?notice=update").text


def test_dashboard_check_for_updates_keeps_the_card_live_until_the_service_finishes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    status = tmp_path / "update-check.json"
    status.write_text('{"when": "23 September 2026 at 16:58", "result": "updated"}')

    class Updates:
        def check(self) -> None:
            return

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), updates=Updates(), update_status=status))
        .post("/system/update")
        .text
    )

    assert "Checking" in html
    assert "data-poll" in html
    assert "16:58" not in html.split('id="firmware-update"', 1)[1].split("</section>", 1)[0]


def test_pi_update_check_records_a_failure_when_sudo_refuses(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard.power import LocalUpdate

    status = tmp_path / "update-check.json"

    class Result:
        returncode = 1

    real_run = subprocess.run

    def run(cmd: list[str], check: bool = False, **kwargs: object) -> object:
        if cmd[:1] == ["sudo"]:
            return Result()
        return real_run(cmd, check=check, **kwargs)

    monkeypatch.setattr("romini.composition.dashboard.power.subprocess.run", run)
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            updates=LocalUpdate(profile="pi"),
            update_status=status,
        )
    )
    html = client.post("/system/update").text

    assert "Check failed" in html
    assert "did not finish" in html
    assert "Checking" not in html.split('id="firmware-update"', 1)[1].split("</section>", 1)[0]


def test_pi_update_check_starts_the_nightly_service(monkeypatch) -> None:
    from romini.composition.dashboard.power import LocalUpdate

    calls: list[list[str]] = []

    class Result:
        returncode = 0

    def run(cmd: list[str], check: bool = False) -> Result:
        calls.append(cmd)
        return Result()

    monkeypatch.setattr("romini.composition.dashboard.power.subprocess.run", run)
    LocalUpdate(profile="pi").check()

    assert calls == [["sudo", "-n", "systemctl", "start", "--no-block", "romini-update.service"]]


def test_pi_power_restart_uses_passwordless_sudo(monkeypatch) -> None:
    from romini.composition.dashboard.power import LocalPower

    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.dashboard.power.subprocess.run", run)
    LocalPower(halt=None, profile="pi").restart()

    assert calls == [["sudo", "-n", "systemctl", "restart", "romini-core"]]


def test_dashboard_volume_quieter_steps_the_mixer() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10)
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "down"},
    )

    assert mixer.level == 9
    assert "Volume saved" in response.text
    assert "9 of 100" in response.text


def test_dashboard_volume_louder_steps_the_mixer() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10)
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "up"},
    )

    assert mixer.level == 11
    assert "Volume saved" in response.text
    assert "11 of 100" in response.text


def test_dashboard_volume_set_jumps_to_the_level() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10)
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"level": "42"},
    )

    assert mixer.level == 42
    assert "Volume saved" in response.text
    assert "42 of 100" in response.text


def test_dashboard_volume_set_clamps_to_the_ceiling() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10, ceiling=100)
    TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"level": "200"},
    )

    assert mixer.level == 100


def test_dashboard_volume_louder_at_ceiling_stays() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=100, ceiling=100)
    TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "up"},
    )

    assert mixer.level == 100


def test_dashboard_volume_quieter_at_zero_stays() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=0)
    TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "down"},
    )

    assert mixer.level == 0


def test_dashboard_volume_without_mixer_is_missing() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).post(
        "/volume",
        data={"step": "up"},
    )

    assert response.status_code == 404


def test_dashboard_saving_an_opened_character_updates_background(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    client.post(
        "/characters",
        data={"name": "Romy", "background": "Now loves boats.", "slug": "romy"},
    )
    html = client.get("/characters").text

    assert ">Now loves boats.</textarea>" in html
    assert "Loves trains." not in html


def test_dashboard_settings_shows_masked_key_tails(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=sk-gemini-test-1a2b\nELEVENLABS_API_KEY=sk_eleven-test-9z8y\n")
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), secrets=secrets)).get("/settings").text

    assert "sk-gemini-test-1a2b" not in html
    assert "sk_eleven-test-9z8y" not in html
    assert "••••1a2b" in html
    assert "••••9z8y" in html


def test_dashboard_settings_shows_empty_audit_log() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "<h2>Audit log</h2>" in html
    assert "Nothing has happened yet" in html


def test_dashboard_settings_lists_audit_entries_newest_first() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    times = iter(
        [
            datetime(2026, 9, 19, 21, 0, tzinfo=UTC),
            datetime(2026, 9, 19, 21, 1, tzinfo=UTC),
        ]
    )
    record_event(log, action="upload", summary="Stored frog.mp3", clock=lambda: next(times))
    record_event(log, action="play", summary="Played The Frog Prince", clock=lambda: next(times))

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/settings").text

    assert "Nothing has happened yet" not in html
    play = html.index("Played The Frog Prince")
    stored = html.index("Stored frog.mp3")
    assert play < stored
    assert "2026-09-19 21:01" in html
    assert 'datetime="2026-09-19T21:01:00+00:00"' in html


def test_dashboard_figures_volume_stays_on_the_figures_page() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=65))).post(
        "/volume", data={"level": "40", "return": "/figures"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=volume"


def test_dashboard_hardware_shows_live_host_facts_without_inventing_wifi() -> None:
    import socket

    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "<h2>Host</h2>" in html
    assert "<h2>Network</h2>" in html
    assert socket.gethostname() in html
    assert ">Wi-Fi<" in html
    assert "Not reported" in html
    assert "sudo nmtui" in html
    assert "software ceiling" not in html.lower()


def test_dashboard_power_controls_stay_off_until_a_box_is_wired() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "Safe power down" in html
    assert 'action="/system/power"' not in html
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).post(
        "/system/power",
        data={"action": "poweroff"},
    )
    assert response.status_code == 404


def test_dashboard_safe_power_down_calls_the_box_halt() -> None:
    from fastapi.testclient import TestClient

    class Power:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def restart(self) -> None:
            self.actions.append("restart")

        def reboot(self) -> None:
            self.actions.append("reboot")

        def poweroff(self) -> None:
            self.actions.append("poweroff")

    power = Power()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), power=power))
    html = client.get("/settings").text

    assert 'action="/system/power"' in html
    assert "Restart daemon" in html
    response = client.post("/system/power", data={"action": "poweroff"}, follow_redirects=False)

    assert response.status_code == 303
    assert power.actions == ["poweroff"]
    assert "Power request sent" in client.get("/settings?notice=power").text


def test_dashboard_sleep_arms_a_thirty_minute_bedtime(tmp_path: Path) -> None:
    from datetime import datetime, timedelta

    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings))
    before = datetime.now().astimezone()

    assert "Sleep in 30m" in client.get("/settings").text
    response = client.post("/safety/sleep", follow_redirects=False)
    deadline = settings.sleep_at()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings")
    assert deadline is not None
    assert timedelta(minutes=29, seconds=50) <= deadline - before <= timedelta(minutes=30, seconds=10)
    assert "Sleeping in 30m" in client.get("/settings").text


def test_dashboard_sleep_can_be_cancelled(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings))
    client.post("/safety/sleep")
    card = client.get("/settings").text.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]

    assert 'name="cancel" value="1"' in card
    response = client.post("/safety/sleep", data={"cancel": "1"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings")
    assert settings.sleep_at() is None
    assert "Sleep in 30m" in client.get("/settings").text
