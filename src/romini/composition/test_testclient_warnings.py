import subprocess
import sys


def test_testclient_import_does_not_warn() -> None:
    completed = subprocess.run(
        [sys.executable, "-W", "always", "-c", "from fastapi.testclient import TestClient"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "install `httpx2`" not in completed.stderr
    assert "BlockingPortal" not in completed.stderr
