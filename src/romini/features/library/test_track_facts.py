import io
import wave

from romini.features.library.track_facts import describe_audio


def test_track_facts_name_the_size_and_length_of_a_wav() -> None:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)

    facts = describe_audio(buffer.getvalue())

    assert facts.size == "15.7 KB"
    assert facts.length == "0:01"
    assert facts.duration_sec == 1


def test_track_facts_name_the_length_of_an_mp3() -> None:
    frame = bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(413)
    facts = describe_audio(frame * 39)

    assert facts.length == "0:01"
    assert facts.duration_sec == 1
