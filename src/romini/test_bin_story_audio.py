import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_story_audio_script_runs_the_module(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.write_text(f"#!{sys.executable}\nimport sys\nprint(' '.join(sys.argv[1:]))\n")
    python.chmod(0o755)
    env = os.environ.copy()
    env["ROMINI_PYTHON"] = str(python)

    result = subprocess.run(
        [str(ROOT / "bin" / "story-audio"), "--folder", "docs/stories"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )

    assert "-m romini.composition.story_audio --folder docs/stories" in result.stdout
