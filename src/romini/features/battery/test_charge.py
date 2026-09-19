from romini.features.battery.charge import percent_from_pack_volts


def test_full_21700_pack_reads_as_100_percent() -> None:
    assert percent_from_pack_volts(4.2) == 100


def test_empty_21700_pack_reads_as_0_percent() -> None:
    assert percent_from_pack_volts(3.0) == 0
