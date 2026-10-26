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
    assert "routes" not in config
    assert config["d1_databases"][0]["database_id"] == "5948544a-74ae-4e4e-922c-908af99e4b9a"
    assert config["d1_databases"][0]["binding"] == "DB"
    assert config["d1_databases"][0]["database_name"] == "romini-demo"
    assert config["d1_databases"][0]["migrations_dir"] == "migrations"
    assert config["r2_buckets"][0]["binding"] == "LIBRARY"
    assert config["r2_buckets"][0]["bucket_name"] == "romini-demo"
    assert config["vars"]["LIBRARY_BASE_URL"].startswith("https://")
    assert config["vars"]["POSTHOG_HOST"] == "https://a.mzworthington.co.uk"
    assert config["limits"]["cpu_ms"] == 30000
    assert "POSTHOG_TOKEN" not in text
    assert "phc_" not in text
    assert "CREATE TABLE IF NOT EXISTS settings" in migration
    assert "CREATE TABLE IF NOT EXISTS catalog" in migration


def test_demo_state_migration_creates_headline_instead_of_adding_it_again() -> None:
    migration = (_REPO / "deploy/demo/migrations/0001_state.sql").read_text()
    audit = migration.split("CREATE TABLE IF NOT EXISTS audit_log", 1)[1].split(");", 1)[0]

    assert "headline TEXT NOT NULL DEFAULT ''" in audit
    assert "ALTER TABLE audit_log ADD COLUMN headline" not in migration


def test_demo_worker_bundles_the_packages_the_script_imports() -> None:
    text = (_REPO / "deploy/demo/pyproject.toml").read_text()

    assert "fastapi" in text
    assert "jinja2" in text
    assert "pyyaml" in text
    assert 'romini = { path = "../.." }' in text
    assert "workers-py" in text
