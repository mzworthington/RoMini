PN532_COMMAND_RFCONFIGURATION = 0x32
PN532_RF_FIELD_ON = [0x01, 0x01]
PN532_ANALOG_TYPE_A_106_MAX_GAIN = [0x0A, 0x79, 0xF4, 0x3F, 0x11, 0x4D, 0x85, 0x61, 0x6F, 0x26, 0x62, 0x87]


def configure_pn532_rf(reader: object) -> None:
    reader.SAM_configuration()
    reader.call_function(PN532_COMMAND_RFCONFIGURATION, params=PN532_RF_FIELD_ON)
    reader.call_function(PN532_COMMAND_RFCONFIGURATION, params=PN532_ANALOG_TYPE_A_106_MAX_GAIN)


def PN532_SPI(*, reset: int = 20, cs: int = 4, debug: bool = False) -> object:
    import board
    import busio
    from adafruit_pn532.spi import PN532_SPI as Driver
    from digitalio import DigitalInOut

    reset_pin = DigitalInOut(getattr(board, f"D{reset}"))
    cs_pin = DigitalInOut(getattr(board, f"D{cs}"))
    reader = Driver(
        busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO),
        cs_pin,
        debug=debug,
        reset=reset_pin,
    )
    configure_pn532_rf(reader)
    return reader
