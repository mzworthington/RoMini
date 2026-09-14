import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sim_script_starts_core_with_sim_profile_http_ports_and_closed_stdin(tmp_path: Path) -> None:
    core = tmp_path / "romini-core"
    core.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "import sys\n"
        "for key in ('ROMINI_PROFILE', 'ROMINI_DATA', 'ROMINI_DASHBOARD_PORT', 'ROMINI_HTTP_PORT'):\n"
        "    print(f'{key}={os.environ.get(key, \"\")}')\n"
        "print('stdin_isatty=' + str(sys.stdin.isatty()))\n"
    )
    core.chmod(0o755)
    data = tmp_path / "romini"
    env = os.environ.copy()
    env["ROMINI_CORE"] = str(core)
    env["ROMINI_DATA"] = str(data)

    result = subprocess.run(
        [str(ROOT / "bin" / "sim")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )

    assert "ROMINI_PROFILE=sim" in result.stdout
    assert f"ROMINI_DATA={data}" in result.stdout
    assert "ROMINI_DASHBOARD_PORT=8080" in result.stdout
    assert "ROMINI_HTTP_PORT=8081" in result.stdout
    assert "stdin_isatty=False" in result.stdout
    assert data.is_dir()
