from romini.composition.mixer import LiveMixer, MemoryMixer


def test_live_mixer_persists_and_applies() -> None:
    applied: list[int] = []
    inner = MemoryMixer(level=10, ceiling=100)
    mixer = LiveMixer(inner, applied.append)

    mixer.set_level(42)

    assert inner.level == 42
    assert mixer.level == 42
    assert mixer.ceiling == 100
    assert applied == [42]
