"""Shared stand-ins for the dashboard HTTP tests."""

from dataclasses import dataclass, field


@dataclass
class FakeBattery:
    percent: int | None
    volts: float | None = None
    flow: str | None = None


@dataclass
class FakeStorage:
    free_bytes: int
    files: dict[str, bytes] = field(default_factory=dict)
    total_bytes: int | None = None
    root: str = ""

    def put(self, filename: str, audio: bytes) -> None:
        self.files[filename] = audio

    def paths(self) -> list[str]:
        return sorted(self.files)

    def get(self, filename: str) -> bytes | None:
        return self.files.get(filename)


@dataclass
class FakeNotices:
    messages: list[str] = field(default_factory=list)

    def tell(self, message: str) -> None:
        self.messages.append(message)


@dataclass
class FakeCatalog:
    paths: list[str] = field(default_factory=list)

    def list_track(self, filename: str) -> None:
        self.paths.append(filename)


@dataclass
class FakeMixer:
    level: int
    ceiling: int = 100

    def set_level(self, level: int) -> None:
        self.level = level


@dataclass
class FakeDrafter:
    script: str
    calls: list[dict[str, str]] = field(default_factory=list)

    def draft(
        self,
        *,
        title: str,
        characters: str,
        interests: str,
        outline: str,
        duration_seconds: int = 10,
    ) -> str:
        self.calls.append(
            {
                "title": title,
                "characters": characters,
                "interests": interests,
                "outline": outline,
                "duration_seconds": str(duration_seconds),
            }
        )
        return self.script


@dataclass
class FakeSpeech:
    audio: bytes
    calls: list[dict[str, str]] = field(default_factory=list)

    def speak(self, *, text: str, voice_id: str) -> bytes:
        self.calls.append({"text": text, "voice_id": voice_id})
        return self.audio
