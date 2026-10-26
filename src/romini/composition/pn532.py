NFC_READ_TIMEOUT = 0.2


class Pn532Nfc:
    def __init__(self, reader: object) -> None:
        self._reader = reader

    def read_uid(self) -> str | None:
        uid = self._reader.read_passive_target(timeout=NFC_READ_TIMEOUT)
        if uid is None:
            return None
        return bytes(uid).hex()

    def rest(self) -> None:
        power_down = getattr(self._reader, "power_down", None)
        if callable(power_down):
            power_down()
