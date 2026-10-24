from romini.features.play_by_tag.place_figure import PlayMode


def test_settings_rows_become_a_read_only_catalog_and_play_mode() -> None:
    from romini.adapters.cloudflare.snapshot import snapshot_from_settings

    catalog, settings = snapshot_from_settings(
        [
            ("catalog", "tracks:\n  - path: frog.mp3\n    title: Frog\n"),
            ("play_mode", "presence"),
        ]
    )

    assert "Frog" in catalog.read_text()
    assert settings.play_mode() is PlayMode.PRESENCE
    assert settings.sleep_at() is None
    assert settings.nfc_beep() is True
    try:
        catalog.write_text("tracks: []\n")
    except PermissionError:
        return
    raise AssertionError("demo catalog accepted a write")
