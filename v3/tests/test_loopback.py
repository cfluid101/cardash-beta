from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class LoopbackTest(unittest.TestCase):
    def test_native_scoping_restoration_and_disconnect_lifecycle(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'loopback-test'
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fobjc-arc',
                            '-fblocks', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'v3/tests/loopback_harness.mm'),
                            '-framework', 'Foundation', '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('10 native lifecycle cases passed', result.stdout)

