import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_dashboard_scripts_keep_their_page_behavior() -> None:
    scripts = sorted((ROOT / "src/romini/composition/dashboard").glob("*.test.js"))
    assert scripts
    result = subprocess.run(
        ["node", "--test", *(path.relative_to(ROOT).as_posix() for path in scripts)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
