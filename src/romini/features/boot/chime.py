import math
import subprocess
import tempfile
import wave
from pathlib import Path
from time import sleep


def _tone(path: Path) -> None:
    rate = 22050
    frames = int(rate * 0.18)
    samples = bytearray()
    for index in range(frames):
        level = int(9000 * math.sin(2 * math.pi * 880 * index / rate))
        samples += level.to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples)


def main() -> None:
    try:
        with tempfile.TemporaryDirectory() as directory:
            wav = Path(directory) / "boot.wav"
            _tone(wav)
            for index in range(3):
                subprocess.run(["aplay", "-D", "plughw:Headphones", str(wav)], check=False)
                if index < 2:
                    sleep(0.22)
    finally:
        _quiet_pwm()


def _quiet_pwm() -> None:
    subprocess.run(["amixer", "-c", "Headphones", "--", "sset", "PCM", "0%", "mute"], check=False)
    for pin in ("18", "19"):
        subprocess.run(["pinctrl", "set", pin, "op", "dl"], check=False)


if __name__ == "__main__":
    main()
