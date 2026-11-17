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
            self.assertIn('Final-reference callback lifetime case passed', result.stdout)
            guarded = subprocess.run([str(binary), 'guarded'], check=True, capture_output=True, text=True)
            self.assertIn('Guarded layout refusal preserves native forwarding', guarded.stdout)
            self.assertIn('10 native lifecycle cases passed', guarded.stdout)
            self.assertIn('Final-reference callback lifetime case passed', guarded.stdout)

    def test_exact_firmware_profile_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'loopback-profiles'
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'v3/tests/loopback_profile_harness.cpp'),
                            '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('Exact identity and full prologue gates passed', result.stdout)

