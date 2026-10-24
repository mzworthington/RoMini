import sys
from pathlib import Path


def seed_statements(catalog: str, *, play_mode: str) -> str:
    return (
        "DELETE FROM settings WHERE key IN ('catalog', 'play_mode');\n"
        f"INSERT INTO settings (key, value) VALUES ('catalog', '{_quote(catalog)}');\n"
        f"INSERT INTO settings (key, value) VALUES ('play_mode', '{_quote(play_mode)}');\n"
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m romini.adapters.cloudflare.seed catalog.yaml")
    sys.stdout.write(seed_statements(Path(sys.argv[1]).read_text(), play_mode="presence"))


def _quote(value: str) -> str:
    return value.replace("'", "''")


if __name__ == "__main__":
    main()
