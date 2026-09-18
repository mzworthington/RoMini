def PN532_I2C(*, reset: int = 20, debug: bool = False) -> object:
    import board
    import busio
    from adafruit_pn532.i2c import PN532_I2C as Driver
    from digitalio import DigitalInOut

    reset_pin = DigitalInOut(getattr(board, f"D{reset}"))
    reader = Driver(busio.I2C(board.SCL, board.SDA), debug=debug, reset=reset_pin)
    reader.SAM_configuration()
    return reader
