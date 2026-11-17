from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class NativeInventoryTest(unittest.TestCase):
    def test_bounded_identity_parser_and_atomic_notification_publication(self):
        source = ROOT / 'v3/native/NativeInventory.mm'
        self.assertTrue(source.is_file(), 'Native media-framework inventory is missing')
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'native-inventory-test'
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fobjc-arc',
                            '-Wall', '-Wextra', '-Werror', '-DCDV3_INVENTORY_TEST',
                            str(ROOT / 'v3/tests/native_inventory_harness.mm'), str(source),
                            '-framework', 'Foundation', '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True,
                                    text=True, timeout=10)
            self.assertIn('Native inventory parser and publication checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
