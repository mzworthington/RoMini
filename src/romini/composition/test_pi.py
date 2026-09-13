from romini.composition.pi import MpvPlayer, Pn532Nfc, SystemdHalt


def test_systemd_halt_runs_systemctl_poweroff(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.pi.subprocess.run", run)
    SystemdHalt().poweroff()

    assert calls == [["systemctl", "poweroff"]]


def test_mpv_player_starts_track_on_alsa(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.pi.subprocess.run", run)
    MpvPlayer().play("/var/lib/romini/library/frog.mp3", position_sec=14.5, uid="04AABBCC")

    assert calls == [["mpv", "--ao=alsa", "--start=14.5", "/var/lib/romini/library/frog.mp3"]]


def test_pn532_nfc_reads_uid_as_lowercase_hex() -> None:
    class Reader:
        def read_passive_target(self) -> bytes:
            return bytes.fromhex("04aabbccddeeff")

    assert Pn532Nfc(Reader()).read_uid() == "04aabbccddeeff"
