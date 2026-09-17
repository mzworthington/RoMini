def PN532_SPI(*, reset: int = 20, cs: int = 4, debug: bool = False) -> object:
    import time

    import RPi.GPIO as GPIO
    import spidev
    from adafruit_pn532.adafruit_pn532 import PN532

    statread, datawrite, dataread, ready = 0x02, 0x01, 0x03, 0x01

    def reverse_bit(num: int) -> int:
        result = 0
        for _ in range(8):
            result <<= 1
            result += num & 1
            num >>= 1
        return result

    class SPIDevice:
        def __init__(self, cs_pin: int) -> None:
            self.spi = spidev.SpiDev(0, 0)
            self.spi.no_cs = True
            GPIO.setmode(GPIO.BCM)
            self._cs = cs_pin
            GPIO.setup(self._cs, GPIO.OUT)
            GPIO.output(self._cs, GPIO.HIGH)
            self.spi.max_speed_hz = 1_000_000
            self.spi.mode = 0b10

        def writebytes(self, buf: bytes) -> None:
            GPIO.output(self._cs, GPIO.LOW)
            time.sleep(0.001)
            self.spi.writebytes(list(buf))
            time.sleep(0.001)
            GPIO.output(self._cs, GPIO.HIGH)

        def xfer(self, buf: bytearray) -> bytearray:
            GPIO.output(self._cs, GPIO.LOW)
            time.sleep(0.001)
            out = bytearray(self.spi.xfer(list(buf)))
            time.sleep(0.001)
            GPIO.output(self._cs, GPIO.HIGH)
            return out

    class HatDriver(PN532):
        def __init__(self, cs_pin: int, reset_pin: int, *, debug: bool = False) -> None:
            self.debug = debug
            self.low_power = False
            self._irq = None
            self._reset_pin = reset_pin
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(reset_pin, GPIO.OUT)
            GPIO.setup(cs_pin, GPIO.OUT)
            GPIO.output(cs_pin, True)
            self._spi = SPIDevice(cs_pin)
            GPIO.output(reset_pin, True)
            time.sleep(0.1)
            GPIO.output(reset_pin, False)
            time.sleep(0.5)
            GPIO.output(reset_pin, True)
            time.sleep(0.1)
            try:
                self._wakeup()
                _ = self.firmware_version
            except RuntimeError:
                _ = self.firmware_version

        def _wakeup(self) -> None:
            time.sleep(1)
            GPIO.output(self._spi._cs, GPIO.LOW)
            time.sleep(0.002)
            self._spi.writebytes(bytearray([0x00]))
            time.sleep(1)

        def _wait_ready(self, timeout: float = 1) -> bool:
            status = bytearray([reverse_bit(statread), 0])
            started = time.monotonic()
            while (time.monotonic() - started) < timeout:
                time.sleep(0.01)
                status = self._spi.xfer(status)
                if reverse_bit(status[1]) == ready:
                    return True
                time.sleep(0.005)
            return False

        def _read_data(self, count: int) -> bytearray:
            frame = bytearray(count + 1)
            frame[0] = reverse_bit(dataread)
            time.sleep(0.005)
            frame = self._spi.xfer(frame)
            return bytearray(reverse_bit(val) for val in frame)[1:]

        def _write_data(self, framebytes: bytes) -> None:
            rev = bytes([reverse_bit(x) for x in bytes([datawrite]) + framebytes])
            time.sleep(0.02)
            self._spi.writebytes(rev)

    reader = HatDriver(cs, reset, debug=debug)
    reader.SAM_configuration()
    return reader
