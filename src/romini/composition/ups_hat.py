from collections.abc import Callable

from romini.features.battery.charge import flow_from_current_ma, percent_from_pack_volts

INA219_ADDR = 0x43
REG_BUS_VOLTAGE = 0x02
REG_CURRENT = 0x04
REG_CALIBRATION = 0x05
CALIBRATION_16V_5A = 26868
CURRENT_LSB_MA = 0.1524


class UpsHatBattery:
    def __init__(self, bus: object, *, addr: int = INA219_ADDR) -> None:
        self._bus = bus
        self._addr = addr
        self._write(REG_CALIBRATION, CALIBRATION_16V_5A)

    def _write(self, register: int, value: int) -> None:
        self._bus.write_i2c_block_data(self._addr, register, [(value >> 8) & 0xFF, value & 0xFF])

    def _read_u16(self, register: int) -> int:
        data = self._bus.read_i2c_block_data(self._addr, register, 2)
        return (data[0] << 8) | data[1]

    def _pack_volts(self) -> float | None:
        try:
            self._write(REG_CALIBRATION, CALIBRATION_16V_5A)
            return (self._read_u16(REG_BUS_VOLTAGE) >> 3) * 0.004
        except OSError:
            return None

    @property
    def volts(self) -> float | None:
        return self._pack_volts()

    @property
    def percent(self) -> int | None:
        volts = self.volts
        if volts is None:
            return None
        return percent_from_pack_volts(volts)

    def _current_ma(self) -> float | None:
        try:
            self._write(REG_CALIBRATION, CALIBRATION_16V_5A)
            raw = self._read_u16(REG_CURRENT)
        except OSError:
            return None
        if raw > 32767:
            raw -= 65536
        return raw * CURRENT_LSB_MA

    @property
    def flow(self) -> str | None:
        current = self._current_ma()
        if current is None:
            return None
        return flow_from_current_ma(current)


def _smbus(bus: int) -> object:
    try:
        from smbus2 import SMBus
    except ImportError:
        from smbus import SMBus
    return SMBus(bus)


def open_ups_hat(*, open_bus: Callable[[int], object] | None = None) -> UpsHatBattery | None:
    factory = open_bus if open_bus is not None else _smbus
    try:
        return UpsHatBattery(factory(1))
    except (OSError, ImportError):
        return None

    def __init__(self, bus: object, *, addr: int = INA219_ADDR) -> None:
        self._bus = bus
        self._addr = addr
        self._write(REG_CALIBRATION, CALIBRATION_16V_5A)

    def _write(self, register: int, value: int) -> None:
        self._bus.write_i2c_block_data(self._addr, register, [(value >> 8) & 0xFF, value & 0xFF])

    def _read_u16(self, register: int) -> int:
        data = self._bus.read_i2c_block_data(self._addr, register, 2)
        return (data[0] << 8) | data[1]

    @property
    def percent(self) -> int | None:
        try:
            self._write(REG_CALIBRATION, CALIBRATION_16V_5A)
            volts = (self._read_u16(REG_BUS_VOLTAGE) >> 3) * 0.004
        except OSError:
            return None
        return percent_from_pack_volts(volts)
