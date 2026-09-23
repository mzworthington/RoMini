from romini.composition.ups_hat import UpsHatBattery


class FakeSmbus:
    def __init__(self, bus_raw: int) -> None:
        self._bus_raw = bus_raw
        self.writes: list[tuple[int, int, list[int]]] = []

    def write_i2c_block_data(self, addr: int, register: int, data: list[int]) -> None:
        self.writes.append((addr, register, data))

    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]:
        assert addr == 0x43
        assert register == 0x02
        assert length == 2
        return [(self._bus_raw >> 8) & 0xFF, self._bus_raw & 0xFF]


class BrokenSmbus:
    def write_i2c_block_data(self, addr: int, register: int, data: list[int]) -> None:
        return

    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]:
        raise OSError


def test_ups_hat_percent_is_missing_when_the_bus_raises() -> None:
    assert UpsHatBattery(BrokenSmbus()).percent is None


def test_ups_hat_reads_full_pack_as_100_percent() -> None:
    hat = UpsHatBattery(FakeSmbus(bus_raw=1050 << 3))

    assert hat.percent == 100


def test_ups_hat_reports_pack_voltage() -> None:
    assert UpsHatBattery(FakeSmbus(bus_raw=1050 << 3)).volts == 4.2
    assert UpsHatBattery(BrokenSmbus()).volts is None


def test_open_ups_hat_skips_when_the_bus_is_missing() -> None:
    from romini.composition.ups_hat import open_ups_hat

    def missing(_bus: int) -> object:
        raise OSError

    assert open_ups_hat(open_bus=missing) is None
