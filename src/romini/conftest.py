import pytest


@pytest.fixture(autouse=True)
def isolate_romini_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROMINI_HTTP_PORT", raising=False)
    monkeypatch.delenv("ROMINI_DASHBOARD_PORT", raising=False)
