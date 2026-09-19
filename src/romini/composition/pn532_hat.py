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
    reader.SAM_configuration()
    return reader
