from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class LocalSetupTests(unittest.TestCase):
    def test_generates_distinct_private_settings_without_printing_or_overwriting_them(self):
        source = Path(__file__).resolve().parents[2] / "scripts/setup_local.py"
        spec = importlib.util.spec_from_file_location("local_setup", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            with patch.object(module, "__file__", str(root / "scripts/setup_local.py")):
                output = io.StringIO()
                with redirect_stdout(output):
                    module.main()
                content = (root / ".env").read_text()
                values = dict(line.split("=", 1) for line in content.splitlines())
                secrets = [
                    value
                    for key, value in values.items()
                    if key.endswith("PASSWORD") or key == "CLOUD_INTERNAL_KEY"
                ]
                self.assertEqual(len(secrets), len(set(secrets)))
                for value in secrets:
                    self.assertGreaterEqual(len(value), 32)
                    self.assertNotIn(value, output.getvalue())
                with self.assertRaises(SystemExit):
                    module.main()
                self.assertEqual(content, (root / ".env").read_text())
