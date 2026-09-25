from romini.features.power.host import cpu_governor, radio_should_sleep


def test_cpu_governor_idles_in_powersave_and_plays_ondemand() -> None:
    assert cpu_governor(playing=False) == "powersave"
    assert cpu_governor(playing=True) == "ondemand"


def test_dashboard_traffic_remembers_the_latest_request() -> None:
    from romini.features.power.host import DashboardTraffic

    traffic = DashboardTraffic()
    assert traffic.seconds_since(100.0) is None
    traffic.note(90.0)
    assert traffic.seconds_since(100.0) == 10.0


def test_radio_sleeps_until_a_dashboard_request_is_recent() -> None:
    assert radio_should_sleep(seconds_since_request=None) is True
    assert radio_should_sleep(seconds_since_request=60) is True
    assert radio_should_sleep(seconds_since_request=59) is False
