"""Monkeypatch seams for host probes. Page code imports its collaborators directly."""

import socket
import subprocess
from datetime import datetime
from pathlib import Path

from romini.adapters.files.catalog import PathCatalog
from romini.adapters.files.storage import DiskStorage
from romini.composition.dashboard.host import assemble_host_facts, player_log
from romini.composition.dashboard.templates_env import templates

_ROUTE_TABLE = Path("/proc/net/route")


def read_host_facts() -> dict[str, str]:
    return assemble_host_facts(route_table=_ROUTE_TABLE, socket_module=socket, run=subprocess.run)


def read_demo_host_facts() -> dict[str, str]:
    return assemble_host_facts(route_table=_ROUTE_TABLE, socket_module=socket, run=_unavailable)


def _unavailable(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
    raise FileNotFoundError("host probe is not available")


def read_player_log() -> str:
    return player_log(subprocess.run)


__all__ = [
    "DiskStorage",
    "PathCatalog",
    "datetime",
    "read_demo_host_facts",
    "read_host_facts",
    "read_player_log",
    "templates",
]
