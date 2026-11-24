"""Discover actual serial endpoints and Windows Classic Bluetooth candidates.

Discovery never opens a serial port, pairs a device, or claims that a listed port
has passed the BITalino protocol handshake. BLE-only devices are not supported by
the current paired-serial BITalino adapter.
"""

import ctypes
import platform
import re


def _text(value, fallback=""):
    value = str(value or fallback)
    return "".join(c for c in value if c.isprintable()).strip()[:200]


def _mac(value):
    compact = re.sub(r"[^0-9a-fA-F]", "", str(value))
    if len(compact) != 12 or int(compact, 16) == 0:
        return None
    return ":".join(compact[i : i + 2] for i in range(0, 12, 2)).upper()


def _port_mac(hwid):
    # Windows BTHENUM instance IDs include the remote address before _C...
    match = re.search(r"(?:^|[\\&])([0-9A-F]{12})(?=_|$)", hwid, re.I)
    return _mac(match.group(1)) if match else None


def _likely_sensor(name):
    return any(part in name.lower() for part in ("bitalino", "musclebit", "plux"))


def windows_bluetooth_devices():
    """Read Classic Bluetooth discovery results through Windows' own API.

    At most two radios are queried, with a 5.12-second inquiry per radio. No
    administrator permission, PyBluez, shell command or pairing mutation is used.
    """
    from ctypes import wintypes as w

    class SystemTime(ctypes.Structure):
        _fields_ = [(name, w.WORD) for name in (
            "year", "month", "day_of_week", "day", "hour", "minute", "second", "milliseconds"
        )]

    class RadioParams(ctypes.Structure):
        _fields_ = [("dwSize", w.DWORD)]

    class SearchParams(ctypes.Structure):
        _fields_ = [
            ("dwSize", w.DWORD), ("authenticated", w.BOOL), ("remembered", w.BOOL),
            ("unknown", w.BOOL), ("connected", w.BOOL), ("inquiry", w.BOOL),
            ("timeout", w.BYTE), ("radio", w.HANDLE),
        ]

    class DeviceInfo(ctypes.Structure):
        _fields_ = [
            ("dwSize", w.DWORD), ("address", ctypes.c_ulonglong),
            ("device_class", w.ULONG), ("connected", w.BOOL),
            ("remembered", w.BOOL), ("authenticated", w.BOOL),
            ("last_seen", SystemTime), ("last_used", SystemTime),
            ("name", w.WCHAR * 248),
        ]

    api = ctypes.WinDLL("bthprops.cpl", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    api.BluetoothFindFirstRadio.argtypes = [ctypes.POINTER(RadioParams), ctypes.POINTER(w.HANDLE)]
    api.BluetoothFindFirstRadio.restype = w.HANDLE
    api.BluetoothFindNextRadio.argtypes = [w.HANDLE, ctypes.POINTER(w.HANDLE)]
    api.BluetoothFindNextRadio.restype = w.BOOL
    api.BluetoothFindRadioClose.argtypes = [w.HANDLE]
    api.BluetoothFindFirstDevice.argtypes = [ctypes.POINTER(SearchParams), ctypes.POINTER(DeviceInfo)]
    api.BluetoothFindFirstDevice.restype = w.HANDLE
    api.BluetoothFindNextDevice.argtypes = [w.HANDLE, ctypes.POINTER(DeviceInfo)]
    api.BluetoothFindNextDevice.restype = w.BOOL
    api.BluetoothFindDeviceClose.argtypes = [w.HANDLE]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    params = RadioParams(ctypes.sizeof(RadioParams))
    radio = w.HANDLE()
    finder = api.BluetoothFindFirstRadio(ctypes.byref(params), ctypes.byref(radio))
    if not finder:
        error = ctypes.get_last_error()
        if error in (0, 259, 1168):
            return [], ["No Classic Bluetooth radio is available. Enable Bluetooth and rescan."]
        raise OSError(error, "Windows Bluetooth radio discovery failed")
    devices = {}
    try:
        for _ in range(2):
            try:
                search = SearchParams(ctypes.sizeof(SearchParams), True, True, True, True, True, 4, radio)
                info = DeviceInfo()
                info.dwSize = ctypes.sizeof(DeviceInfo)
                device_finder = api.BluetoothFindFirstDevice(ctypes.byref(search), ctypes.byref(info))
                if device_finder:
                    try:
                        for _ in range(256):
                            address = _mac(f"{info.address:012X}")
                            if address:
                                devices[address] = {
                                    "address": address,
                                    "name": _text(info.name, "Bluetooth device"),
                                    "paired": bool(info.authenticated or info.remembered),
                                }
                            if not api.BluetoothFindNextDevice(device_finder, ctypes.byref(info)):
                                break
                    finally:
                        api.BluetoothFindDeviceClose(device_finder)
            finally:
                kernel.CloseHandle(radio)
            if not api.BluetoothFindNextRadio(finder, ctypes.byref(radio)):
                break
        else:
            # The next radio handle was opened at the end of the bounded loop.
            kernel.CloseHandle(radio)
    finally:
        api.BluetoothFindRadioClose(finder)
    return list(devices.values()), []


def scan_sensors(port_provider=None, bluetooth_provider=None, system=None):
    """Return serial choices plus named, not-yet-paired sensor candidates."""
    system = system or platform.system()
    if port_provider is None:
        from serial.tools import list_ports
        port_provider = list_ports.comports
    warnings = []
    bluetooth = []
    if system == "Windows":
        try:
            bluetooth, notes = (bluetooth_provider or windows_bluetooth_devices)()
            warnings.extend(notes)
        except (OSError, AttributeError):
            warnings.append("Windows Bluetooth discovery is unavailable. Pair the sensor in Bluetooth settings, then rescan serial ports.")
    else:
        warnings.append("This scan lists serial ports. Pair Bluetooth sensors in system settings first; BLE discovery is not supported.")
    by_mac = {item["address"]: item for item in bluetooth}
    used_addresses = set()
    devices = []
    try:
        ports = list(port_provider())
    except (OSError, RuntimeError):
        ports = []
        warnings.append("Serial ports could not be enumerated. Check device permissions and rescan.")
    seen = set()
    for port in ports:
        address = _text(getattr(port, "device", ""))
        if not address or address in seen:
            continue
        seen.add(address)
        description = _text(getattr(port, "description", ""), "Serial port")
        hwid = _text(getattr(port, "hwid", ""))
        remote = _port_mac(hwid)
        matched = by_mac.get(remote)
        is_bluetooth = "BTHENUM" in hwid.upper() or "BLUETOOTH" in description.upper() or (system == "Darwin" and "BLUETOOTH" in address.upper())
        transport = "bluetooth-serial" if is_bluetooth else "usb-serial" if getattr(port, "vid", None) is not None else "serial"
        incoming = bool(is_bluetooth and re.search(r"(?:^|[\\&])000000000000(?=_|$)", hwid, re.I))
        name = matched["name"] if matched else description
        if incoming:
            name += " (incoming port; select an outgoing sensor port instead)"
        devices.append({
            "id": "serial:" + address, "address": address, "name": name,
            "transport": transport, "paired": True if is_bluetooth else None,
            "selectable": not incoming, "likely_sensor": _likely_sensor(name),
        })
        if remote:
            used_addresses.add(remote)
    for remote, item in by_mac.items():
        # Do not flood the selector with unrelated headphones/phones. An unknown
        # serial port is still offered above without falsely identifying it.
        if remote in used_addresses or not _likely_sensor(item["name"]):
            continue
        devices.append({
            "id": "bluetooth:" + remote, "address": remote, "name": item["name"],
            "transport": "bluetooth", "paired": item["paired"],
            "selectable": False, "likely_sensor": True,
        })
    devices.sort(key=lambda item: (not item["likely_sensor"], not item["selectable"], item["name"].lower(), item["address"]))
    return {
        "devices": devices,
        "warnings": warnings,
        "scope": "Windows Classic Bluetooth and serial ports" if system == "Windows" else "Serial ports",
    }
