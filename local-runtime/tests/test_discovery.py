import unittest
from types import SimpleNamespace

from myocontrol_runtime.acquisition.discovery import scan_sensors


def port(device="COM7", description="Standard Serial over Bluetooth link", hwid="BTHENUM\\SERVICE\\7&ABC&0&001122AABBCC_C00000000", vid=None):
    return SimpleNamespace(device=device, description=description, hwid=hwid, vid=vid)


class DiscoveryTests(unittest.TestCase):
    def test_matches_real_bluetooth_port_to_device_name_and_deduplicates(self):
        result = scan_sensors(
            lambda: [port(), port()],
            lambda: ([{"address": "00:11:22:AA:BB:CC", "name": "BITalino-ABCD", "paired": True}], []),
            "Windows",
        )
        self.assertEqual(len(result["devices"]), 1)
        selected = result["devices"][0]
        self.assertEqual(selected["address"], "COM7")
        self.assertEqual(selected["name"], "BITalino-ABCD")
        self.assertTrue(selected["selectable"])
        self.assertEqual(selected["transport"], "bluetooth-serial")

    def test_unpaired_bitalino_requires_pairing_and_never_becomes_fake_com_port(self):
        result = scan_sensors(lambda: [], lambda: ([
            {"address": "00:11:22:AA:BB:CC", "name": "BITalino", "paired": False},
            {"address": "00:11:22:AA:BB:DD", "name": "Headphones", "paired": True},
        ], []), "Windows")
        self.assertEqual(len(result["devices"]), 1)
        self.assertFalse(result["devices"][0]["selectable"])
        self.assertFalse(result["devices"][0]["paired"])

    def test_bluetooth_failure_keeps_usb_and_manual_choices(self):
        def failure():
            raise OSError("radio unavailable")
        result = scan_sensors(lambda: [port("COM3", "USB Serial", "USB VID", 123)], failure, "Windows")
        self.assertEqual(result["devices"][0]["transport"], "usb-serial")
        self.assertTrue(result["warnings"])

    def test_non_windows_scan_uses_ports_without_calling_windows_api(self):
        def forbidden():
            raise AssertionError("Windows API must not run")
        result = scan_sensors(lambda: [port("/dev/cu.BITalino", "BITalino", "")], forbidden, "Darwin")
        self.assertEqual(result["devices"][0]["address"], "/dev/cu.BITalino")
        self.assertIn("serial", result["scope"].lower())

    def test_incoming_bluetooth_port_is_not_a_sensor_connection(self):
        result = scan_sensors(lambda: [port(hwid="BTHENUM\\SERVICE\\7&ABC&0&000000000000_00000002")], lambda: ([], []), "Windows")
        self.assertEqual(len(result["devices"]), 1)
        self.assertFalse(result["devices"][0]["selectable"])
        self.assertIn("incoming", result["devices"][0]["name"])

    def test_no_device_is_an_empty_result_not_a_demo(self):
        result = scan_sensors(lambda: [], lambda: ([], []), "Windows")
        self.assertEqual(result["devices"], [])


if __name__ == "__main__":
    unittest.main()
