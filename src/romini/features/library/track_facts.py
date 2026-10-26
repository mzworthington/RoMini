import io
import wave
from dataclasses import dataclass


@dataclass(frozen=True)
class TrackFacts:
    size: str
    length: str
    duration_sec: int


def format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def format_length(duration_sec: int) -> str:
    minutes, seconds = divmod(max(0, duration_sec), 60)
    return f"{minutes}:{seconds:02d}"


def wav_duration_sec(audio: bytes) -> int | None:
    try:
        with wave.open(io.BytesIO(audio), "rb") as handle:
            rate = handle.getframerate()
            if rate <= 0:
                return None
            return int(handle.getnframes() / rate)
    except (wave.Error, EOFError):
        return None


_MPEG1_L3_KBPS = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_MPEG1_HZ = [44100, 48000, 32000]


def mp3_duration_sec(audio: bytes) -> int | None:
    seconds = 0.0
    index = 0
    found = False
    while index + 4 <= len(audio):
        frame = _mpeg_frame(audio, index)
        if frame is None:
            index += 1
            continue
        frame_len, rate = frame
        if frame_len < 4 or index + frame_len > len(audio):
            break
        seconds += 1152 / rate
        found = True
        index += frame_len
    if not found:
        return None
    return int(seconds)


def _mpeg_frame(audio: bytes, index: int) -> tuple[int, int] | None:
    if audio[index] != 0xFF or audio[index + 1] & 0xE0 != 0xE0:
        return None
    version = (audio[index + 1] >> 3) & 0x03
    layer = (audio[index + 1] >> 1) & 0x03
    bitrate_index = (audio[index + 2] >> 4) & 0x0F
    rate_index = (audio[index + 2] >> 2) & 0x03
    padding = (audio[index + 2] >> 1) & 0x01
    if version != 0b11 or layer != 0b01 or bitrate_index in (0, 15) or rate_index == 3:
        return None
    bitrate = _MPEG1_L3_KBPS[bitrate_index] * 1000
    rate = _MPEG1_HZ[rate_index]
    frame_len = int(144 * bitrate / rate) + padding
    return frame_len, rate


def describe_audio(audio: bytes) -> TrackFacts:
    duration = wav_duration_sec(audio)
    if duration is None:
        duration = mp3_duration_sec(audio) or 0
    return TrackFacts(
        size=format_size(len(audio)),
        length=format_length(duration),
        duration_sec=duration,
    )
