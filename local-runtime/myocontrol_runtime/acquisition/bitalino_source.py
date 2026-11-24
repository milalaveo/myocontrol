import importlib
import platform
import re


class BitalinoSource:
    def __init__(self, address, sample_rate_hz, channels, factory=None):
        if not isinstance(address, str) or not 1 <= len(address) <= 200:
            raise ValueError("Enter a Bluetooth address or paired serial port")
        if sample_rate_hz not in {1, 10, 100, 1000}:
            raise ValueError("BITalino supports 1, 10, 100 or 1000 Hz")
        if (
            not isinstance(channels, list)
            or not 1 <= len(channels) <= 6
            or len(set(channels)) != len(channels)
            or any(type(c) is not int or c not in range(6) for c in channels)
        ):
            raise ValueError("Select unique BITalino channels A1–A6")
        if platform.system() == "Darwin" and re.fullmatch(
            r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", address
        ):
            raise ValueError(
                "On macOS select the paired Bluetooth serial port (/dev/...), not a MAC address"
            )
        address = address.strip()
        if platform.system() == "Windows":
            if re.fullmatch(r"COM[0-9]+", address, re.IGNORECASE):
                address = address.upper()
            elif re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", address):
                raise ValueError("Pair BITalino in Windows Bluetooth settings and select its outgoing COM port")
        self.channels = sorted(channels)
        self.rate = sample_rate_hz
        self.device = None
        self.last_sequence = None
        self.factory = factory
        self.address = address

    def open(self):
        factory = self.factory
        if factory is None:
            try:
                factory = importlib.import_module("bitalino").BITalino
            except ImportError:
                raise ValueError(
                    "The BITalino SDK is not installed in this runtime"
                ) from None
        try:
            self.device = factory(self.address, timeout=2)
            if getattr(self.device, "serial", False):
                self.device.socket.timeout = 2
                self.device.socket.write_timeout = 2
            self.device.start(self.rate, self.channels)
        except Exception:
            self.close()
            raise

    def read(self):
        rows = self.device.read(max(1, self.rate // 10))
        samples = []
        for row in rows:
            sequence = int(row[0])
            if (
                self.last_sequence is not None
                and sequence != (self.last_sequence + 1) % 16
            ):
                raise ValueError(
                    "BITalino sample sequence discontinuity; acquisition stopped"
                )
            self.last_sequence = sequence
            samples.append([float(value) for value in row[5 : 5 + len(self.channels)]])
        if not samples:
            raise ValueError("BITalino returned no samples")
        return samples

    def close(self):
        device, self.device = self.device, None
        if device:
            try:
                if getattr(device, "started", False):
                    device.stop()
            finally:
                device.close()
