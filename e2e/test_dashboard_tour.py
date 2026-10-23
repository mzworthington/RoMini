"""A recorded walkthrough of the parent dashboard.

Not part of `make test`. Refresh the files with `make tour`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_dashboard_tour import record_tour  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
WEBM = REPO / "docs" / "images" / "dashboard-tour.webm"
EBML = b"\x1a\x45\xdf\xa3"


def test_dashboard_tour_writes_a_webm() -> None:
    record_tour(WEBM)
    data = WEBM.read_bytes()
    assert data.startswith(EBML)
    assert len(data) > 50_000
