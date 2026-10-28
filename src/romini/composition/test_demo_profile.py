from pathlib import Path

from romini.fakes import FakeLed, FakePlayer, write_empty_data


def test_demo_profile_serves_a_public_dashboard_without_nfc(tmp_path: Path, monkeypatch) -> None:
    import romini.__main__ as core

    data = write_empty_data(tmp_path)
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "demo")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    seen: dict[str, object] = {}

    def create_dashboard(**kwargs: object) -> object:
        seen["demo"] = kwargs["demo"]
        seen["secrets"] = kwargs["secrets"]
        seen["power"] = kwargs["power"]
        return object()

    def start_dashboard(app: object, *, host: str, port: int, **extra: object) -> object:
        seen["host"] = host
        return type("Listener", (), {"wait": lambda self: None, "close": lambda self: None})()

    def nfc_opener() -> object:
        seen["nfc"] = True
        return object()

    monkeypatch.setattr(core, "create_dashboard", create_dashboard)
    monkeypatch.setattr(core, "start_dashboard", start_dashboard)
    monkeypatch.setattr(core, "default_nfc", nfc_opener)

    core.entry(player=FakePlayer(), led=FakeLed())

    assert seen["demo"] is True
    assert seen["secrets"] is None
    assert seen["power"] is None
    assert seen["host"] == "0.0.0.0"
    assert "nfc" not in seen
