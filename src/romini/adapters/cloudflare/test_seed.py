def test_seed_sql_stores_the_catalog_in_settings() -> None:
    from romini.adapters.cloudflare.seed import seed_statements

    sql = seed_statements("tracks:\n  - path: frog.mp3\n    title: Frog's day\n", play_mode="presence")

    assert "DELETE FROM settings WHERE key IN ('catalog', 'play_mode')" in sql
    assert "INSERT INTO settings (key, value) VALUES ('catalog', 'tracks:" in sql
    assert "Frog''s day" in sql
    assert "('play_mode', 'presence')" in sql
