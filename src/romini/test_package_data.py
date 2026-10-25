import tomllib
from pathlib import Path

from setuptools.glob import glob

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "romini"


def test_wheel_package_data_includes_the_welcome_track() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = config["tool"]["setuptools"]["package-data"]["romini"]
    matched = {Path(path).name for pattern in patterns for path in glob(str(PACKAGE / pattern))}
    assert "connect.mp3" in matched
    assert "disconnect.mp3" in matched


def test_wheel_package_data_includes_dashboard_css_partials() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = config["tool"]["setuptools"]["package-data"]["romini"]
    matched = {Path(path).resolve() for pattern in patterns for path in glob(str(PACKAGE / pattern))}
    css = PACKAGE / "composition" / "dashboard" / "templates" / "css" / "base.css"
    assert css.resolve() in matched


def test_wheel_package_data_includes_the_demo_studio() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = config["tool"]["setuptools"]["package-data"]["romini"]
    matched = {Path(path).resolve() for pattern in patterns for path in glob(str(PACKAGE / pattern))}
    studio = PACKAGE / "composition" / "demo_content"
    expected = {
        studio / "characters" / "romy" / "character.yaml",
        studio / "characters" / "mama" / "character.yaml",
        studio / "characters" / "baba" / "character.yaml",
        studio / "characters" / "current",
        studio / "stories" / "romy-and-the-banana" / "story.yaml",
        studio / "stories" / "romy-and-the-brick-tower" / "story.yaml",
        studio / "stories" / "romy-and-the-little-station" / "story.yaml",
        studio / "stories" / "romy-and-the-red-helmet" / "story.yaml",
        studio / "stories" / "romy-and-the-robot" / "story.yaml",
        studio / "stories" / "current",
    }
    assert expected <= matched
