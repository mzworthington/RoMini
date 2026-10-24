from romini.features.demo.policy import demo_forbids


def test_public_demo_refuses_keys_uploads_and_other_changes() -> None:
    assert demo_forbids("POST", "/keys")
    assert demo_forbids("POST", "/tracks")
    assert demo_forbids("POST", "/tracks/")
    assert demo_forbids("POST", "/stories/draft")
    assert demo_forbids("POST", "/stories/speak")
    assert demo_forbids("POST", "/stories")
    assert demo_forbids("POST", "/stories/delete")
    assert demo_forbids("POST", "/library/delete")
    assert demo_forbids("POST", "/characters")
    assert demo_forbids("POST", "/characters/new")
    assert demo_forbids("POST", "/assign")
    assert demo_forbids("POST", "/library/cover")
    assert demo_forbids("POST", "/figures/cover")
    assert demo_forbids("POST", "/tags/04a1/name")
    assert demo_forbids("POST", "/system/power")
    assert demo_forbids("POST", "/system/update")
    assert demo_forbids("PUT", "/play-mode")
    assert demo_forbids("POST", "/safety/sleep")
    assert not demo_forbids("GET", "/settings")
    assert not demo_forbids("GET", "/library")
    assert not demo_forbids("POST", "/play")
    assert not demo_forbids("POST", "/volume")
    assert not demo_forbids("POST", "/library/play/04a1")
    assert not demo_forbids("POST", "/library/stop")


def test_public_demo_refuses_backup_restore() -> None:
    assert demo_forbids("POST", "/backup")
    assert not demo_forbids("GET", "/backup")
