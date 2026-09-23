from romini.features.battery.charge import flow_from_current_ma, percent_from_pack_volts


def test_full_21700_pack_reads_as_100_percent() -> None:
    assert percent_from_pack_volts(4.2) == 100


def test_empty_21700_pack_reads_as_0_percent() -> None:
    assert percent_from_pack_volts(3.0) == 0


def test_pack_current_sign_is_charging_or_discharging() -> None:
    assert flow_from_current_ma(120) == "charging"
    assert flow_from_current_ma(-80) == "discharging"
    assert flow_from_current_ma(0) == "steady"
