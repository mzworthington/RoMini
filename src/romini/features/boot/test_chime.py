def test_boot_chime_plays_three_tones_on_the_headphones(monkeypatch) -> None:
    from romini.features.boot.chime import main

    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.features.boot.chime.subprocess.run", run)
    monkeypatch.setattr("romini.features.boot.chime.sleep", lambda _seconds: None)
    main()

    assert calls[0][:3] == ["aplay", "-D", "plughw:Headphones"]
    assert calls[0][-1].endswith(".wav")
    assert calls[1][:3] == ["aplay", "-D", "plughw:Headphones"]
    assert calls[2][:3] == ["aplay", "-D", "plughw:Headphones"]
    assert calls[3:] == [
        ["amixer", "-c", "Headphones", "--", "sset", "PCM", "0%", "mute"],
        ["pinctrl", "set", "18", "op", "dl"],
        ["pinctrl", "set", "19", "op", "dl"],
    ]
