import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_dashboard_scripts_keep_their_page_behavior() -> None:
    result = subprocess.run(
        ["node", "--test", "src/romini/composition/dashboard"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
