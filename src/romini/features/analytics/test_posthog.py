from pathlib import Path

from romini.features.analytics.posthog import DEFAULT_POSTHOG_HOST, resolve_public_posthog_config

_REPO = Path(__file__).resolve().parents[4]


def test_missing_token_skips_posthog() -> None:
    assert resolve_public_posthog_config(None) == {"enabled": False}
    assert resolve_public_posthog_config("  ") == {"enabled": False}


def test_reverse_proxy_host_is_the_default() -> None:
    assert resolve_public_posthog_config(" phc_test ") == {
        "enabled": True,
        "apiKey": "phc_test",
        "apiHost": DEFAULT_POSTHOG_HOST,
    }
    assert DEFAULT_POSTHOG_HOST == "https://a.mzworthington.co.uk"


def test_public_pages_share_the_boot_script_and_privacy_notice() -> None:
    script = (_REPO / "src/romini/composition/dashboard/templates/posthog.js").read_text()
    privacy = (_REPO / "src/romini/composition/dashboard/templates/privacy.html").read_text()

    assert script == (_REPO / "deploy/party/public/posthog.js").read_text()
    assert privacy == (_REPO / "deploy/party/public/privacy/index.html").read_text()
    assert 'cookieless_mode: "always"' in script
    assert 'person_profiles: "never"' in script
    assert "disable_session_recording: true" in script
    assert "https://eu.posthog.com" in script
    assert "2026-05-30" in script


def test_committed_party_config_stays_disabled() -> None:
    config = (_REPO / "deploy/party/public/posthog-config.json").read_text()

    assert config.strip() == '{"enabled":false}'
    assert "phc_" not in config


def test_posthog_host_override_is_trimmed() -> None:
    assert resolve_public_posthog_config("phc_test", " https://eu.i.posthog.com ") == {
        "enabled": True,
        "apiKey": "phc_test",
        "apiHost": "https://eu.i.posthog.com",
    }
