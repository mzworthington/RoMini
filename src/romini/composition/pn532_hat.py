def PN532_SPI(*, reset: int = 20, cs: int = 4, debug: bool = False) -> object:
    import board
    import busio
    from adafruit_pn532.spi import PN532_SPI as Driver
    from digitalio import DigitalInOut

    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    chip_select = DigitalInOut(getattr(board, f"D{cs}"))
    reset_pin = DigitalInOut(getattr(board, f"D{reset}"))
    reader = Driver(spi, chip_select, reset=reset_pin, debug=debug)
    reader.SAM_configuration()
    return reader
