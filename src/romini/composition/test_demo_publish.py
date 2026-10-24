import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]


def test_demo_worker_is_published_on_the_party_zone() -> None:
    text = (_REPO / "deploy/demo/wrangler.jsonc").read_text()
    config = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))
    migration = (_REPO / "deploy/demo/migrations/0001_state.sql").read_text()

    assert config["name"] == "romini-demo"
    assert config["main"].endswith("src/romini/composition/demo_worker.py")
    assert "python_workers" in config["compatibility_flags"]
    assert config["routes"] == [{"pattern": "demo.romini.party", "custom_domain": True}]
    assert config["d1_databases"][0]["binding"] == "DB"
    assert config["d1_databases"][0]["database_name"] == "romini-demo"
    assert config["r2_buckets"][0]["binding"] == "LIBRARY"
    assert config["r2_buckets"][0]["bucket_name"] == "romini-demo"
    assert config["vars"]["LIBRARY_BASE_URL"].startswith("https://")
    assert "CREATE TABLE IF NOT EXISTS settings" in migration
    assert "CREATE TABLE IF NOT EXISTS catalog" in migration
