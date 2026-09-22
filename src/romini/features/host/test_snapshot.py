from romini.features.host.snapshot import host_facts, parse_load_percent, parse_meminfo_mb, parse_thermal_c


def test_meminfo_reports_used_and_total_megabytes() -> None:
    used, total = parse_meminfo_mb("MemTotal: 3891200 kB\nMemAvailable: 3264512 kB\n") or (0, 0)

    assert used == 612
    assert total == 3800


def test_thermal_millidegrees_become_celsius() -> None:
    assert parse_thermal_c("42100\n") == 42.1


def test_load_percent_uses_the_core_count() -> None:
    assert parse_load_percent("0.24 0.20 0.18 1/120 1", cores=4) == 6


def test_missing_probes_stay_unreported() -> None:
    facts = host_facts(hostname="romini", meminfo=None, thermal=None, loadavg=None, cores=4)

    assert facts.hostname == "romini"
    assert facts.cpu_temp_c is None
    assert facts.load_pct is None
    assert facts.ram_used_mb is None
    assert facts.lan_ip == ""
