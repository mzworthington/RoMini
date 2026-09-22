import os
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HostFacts:
    hostname: str
    cpu_temp_c: float | None
    load_pct: int | None
    ram_used_mb: int | None
    ram_total_mb: int | None
    lan_ip: str


def parse_meminfo_mb(text: str) -> tuple[int, int] | None:
    totals: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if len(parts) < 2 or parts[1] != "kB":
            continue
        totals[key] = int(parts[0])
    total = totals.get("MemTotal")
    available = totals.get("MemAvailable")
    if total is None or available is None or total <= 0:
        return None
    used = max(0, total - available)
    return used // 1024, total // 1024


def parse_thermal_c(text: str) -> float | None:
    raw = text.strip()
    if not raw or not raw.lstrip("-").isdigit():
        return None
    return int(raw) / 1000


def parse_load_percent(text: str, *, cores: int) -> int | None:
    if cores <= 0:
        return None
    first = text.split()
    if not first:
        return None
    try:
        load = float(first[0])
    except ValueError:
        return None
    return min(100, round(100 * load / cores))


def host_facts(
    *,
    hostname: str,
    meminfo: str | None,
    thermal: str | None,
    loadavg: str | None,
    cores: int,
    lan_ip: str = "",
) -> HostFacts:
    memory = parse_meminfo_mb(meminfo) if meminfo else None
    return HostFacts(
        hostname=hostname.strip(),
        cpu_temp_c=parse_thermal_c(thermal) if thermal else None,
        load_pct=parse_load_percent(loadavg, cores=cores) if loadavg else None,
        ram_used_mb=memory[0] if memory else None,
        ram_total_mb=memory[1] if memory else None,
        lan_ip=lan_ip.strip(),
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None


def lan_address() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            return str(sock.getsockname()[0])
    except OSError:
        return ""


def live_host_facts() -> HostFacts:
    cores = os.cpu_count() or 1
    return host_facts(
        hostname=socket.gethostname(),
        meminfo=_read(Path("/proc/meminfo")),
        thermal=_read(Path("/sys/class/thermal/thermal_zone0/temp")),
        loadavg=_read(Path("/proc/loadavg")),
        cores=cores,
        lan_ip=lan_address(),
    )
