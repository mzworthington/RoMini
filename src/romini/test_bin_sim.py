import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ephemeral_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


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
    dash_port = _ephemeral_port()
    http_port = _ephemeral_port()
    env = os.environ.copy()
    env["ROMINI_CORE"] = str(core)
    env["ROMINI_DATA"] = str(data)
    env["ROMINI_DASHBOARD_PORT"] = str(dash_port)
    env["ROMINI_HTTP_PORT"] = str(http_port)

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
    assert f"ROMINI_DASHBOARD_PORT={dash_port}" in result.stdout
    assert f"ROMINI_HTTP_PORT={http_port}" in result.stdout
    assert "stdin_isatty=False" in result.stdout
    assert data.is_dir()


def test_sim_script_replaces_romini_core_already_listening_on_http_ports(tmp_path: Path) -> None:
    http_port = _ephemeral_port()
    dash_port = _ephemeral_port()
    leftover_bin = tmp_path / "romini-core"
    leftover_bin.write_text(
        f"#!{sys.executable}\n"
        "import socket\n"
        "import time\n"
        f"http = socket.socket(); http.bind(('127.0.0.1', {http_port})); http.listen()\n"
        f"dash = socket.socket(); dash.bind(('127.0.0.1', {dash_port})); dash.listen()\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    leftover_bin.chmod(0o755)
    leftover = subprocess.Popen([str(leftover_bin)], stdout=subprocess.PIPE, text=True)
    try:
        assert leftover.stdout.readline().strip() == "ready"
        next_core = tmp_path / "next-core"
        next_core.write_text(f"#!{sys.executable}\nprint('started')\n")
        next_core.chmod(0o755)
        env = os.environ.copy()
        env["ROMINI_CORE"] = str(next_core)
        env["ROMINI_DATA"] = str(tmp_path / "romini")
        env["ROMINI_HTTP_PORT"] = str(http_port)
        env["ROMINI_DASHBOARD_PORT"] = str(dash_port)
        result = subprocess.run(
            [str(ROOT / "bin" / "sim")],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        leftover.wait(timeout=5)
        assert leftover.returncode is not None
        assert "started" in result.stdout
    finally:
        leftover.kill()
        leftover.wait(timeout=2)
