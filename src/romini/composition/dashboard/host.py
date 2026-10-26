import os
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path


def read_text(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def player_log(run: Callable[..., subprocess.CompletedProcess[str]]) -> str:
    try:
        shown = run(
            [
                "journalctl",
                "-u",
                "romini-core.service",
                "-u",
                "romini-update.service",
                "-n",
                "1000",
                "--no-pager",
                "-o",
                "short-iso",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = shown.stdout.strip()
    if text:
        return text
    return shown.stderr.strip()


def wifi_name(run: Callable[..., subprocess.CompletedProcess[str]]) -> str:
    try:
        shown = run(
            ["iw", "dev", "wlan0", "link"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in shown.stdout.splitlines():
        label, _, ssid = line.strip().partition(":")
        if label == "SSID" and ssid.strip():
            return ssid.strip()
    return ""


def default_gateway(route_text: str) -> str:
    for line in route_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 3 or fields[1] != "00000000":
            continue
        gateway = _gateway_address(fields[2])
        if gateway:
            return gateway
    return ""


def _gateway_address(raw: str) -> str:
    if len(raw) != 8 or raw == "00000000":
        return ""
    try:
        octets = [int(raw[index : index + 2], 16) for index in (6, 4, 2, 0)]
    except ValueError:
        return ""
    return ".".join(str(part) for part in octets)


def local_address(route_table: Path, socket_module: socket) -> str:
    try:
        route_text = route_table.read_text()
    except OSError:
        return ""
    gateway = default_gateway(route_text)
    if not gateway:
        return ""
    try:
        with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_DGRAM) as sock:
            sock.connect((gateway, 80))
            return sock.getsockname()[0]
    except OSError:
        return ""


def cpu_temp() -> str:
    temp_raw = read_text("/sys/class/thermal/thermal_zone0/temp").strip()
    if not temp_raw.isdigit():
        return ""
    return f"{int(temp_raw) / 1000:.0f}°C"


def load_average() -> str:
    try:
        one, _, _ = os.getloadavg()
    except OSError:
        return ""
    return f"{one:.2f}"


def memory_usage() -> str:
    total_kb, available_kb = _meminfo_kb(read_text("/proc/meminfo"))
    if not total_kb:
        return ""
    used_mb = max(0, total_kb - available_kb) // 1024
    total_mb = total_kb // 1024
    return f"{used_mb} MB / {total_mb} MB"


def _meminfo_kb(meminfo: str) -> tuple[int, int]:
    total_kb = 0
    available_kb = 0
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            total_kb = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            available_kb = int(line.split()[1])
    return total_kb, available_kb


def uptime_label() -> str:
    uptime_raw = read_text("/proc/uptime").split()
    if not uptime_raw:
        return ""
    seconds = int(float(uptime_raw[0]))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def assemble_host_facts(
    *,
    route_table: Path,
    socket_module: socket,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, str]:
    hostname = socket_module.gethostname().strip() or "romini"
    address = local_address(route_table, socket_module)
    if address.startswith("127."):
        address = ""
    missing = "Not reported"
    model = read_text("/proc/device-tree/model").replace("\x00", "").strip()
    return {
        "hostname": hostname,
        "address": address or missing,
        "cpu_temp": cpu_temp() or missing,
        "load": load_average() or missing,
        "memory": memory_usage() or missing,
        "uptime": uptime_label() or missing,
        "wifi": wifi_name(run) or missing,
        "model": model or missing,
    }
