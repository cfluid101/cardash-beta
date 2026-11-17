import json
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
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('10 native lifecycle cases passed', result.stdout)
            self.assertIn('Final-reference callback lifetime case passed', result.stdout)
            guarded = subprocess.run([str(binary), 'guarded'], check=True, capture_output=True, text=True)
            self.assertIn('Guarded layout refusal preserves native forwarding', guarded.stdout)
            self.assertIn('10 native lifecycle cases passed', guarded.stdout)
            self.assertIn('Final-reference callback lifetime case passed', guarded.stdout)
            shifted = subprocess.run([str(binary), 'shifted'], check=True, capture_output=True, text=True)
            self.assertIn('Shifted transport preserves request identity and adjacent double', shifted.stdout)
            self.assertIn('10 native lifecycle cases passed', shifted.stdout)
            self.assertIn('Final-reference callback lifetime case passed', shifted.stdout)


    def test_exact_firmware_profile_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'loopback-profiles'
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'v3/tests/loopback_profile_harness.cpp'),
                            '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Exact identity and full prologue gates passed', result.stdout)
            fixtures = json.loads((ROOT / 'v3/tests/fixtures/transport_beta9_firmware.json').read_text())
            names = {'Middle': 'middle', 'RequestIdentifier': 'request-identifier',
                     'EarlyUnsupported': 'early-usb-release-unimplemented'}
            for row in fixtures['samples']:
                with self.subTest(sample=row['sample']):
                    checked = subprocess.run([str(binary), row['uuid'].replace('-', ''),
                        row['cpu_type'], row['cpu_subtype'], row['update_offset'], row['event_offset'],
                        row['update_prefix'], row['event_prefix'], names[row['layout']],
                        str(int(row['hookable']))], capture_output=True, text=True)
                    self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                    self.assertIn('Firmware fixture identity, layout, bounds and full entry bytes passed', checked.stdout)



    def test_loader_rejects_unknown_and_early_lifecycle_before_hooking(self):
        fixtures = json.loads((ROOT / 'v3/tests/fixtures/transport_beta9_firmware.json').read_text())['samples']
        by_build = {row['sample']: row for row in fixtures}
        arm64 = by_build['iPhone10,2_16.0_20A362']
        early = by_build['iPhone14,2_15.0_19A346']
        arm64e = by_build['iPhone14,2_15.6.1_19G82']
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'loopback-loader'
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fobjc-arc',
                            '-fblocks', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'v3/tests/loopback_loader_harness.mm'),
                            '-framework', 'Foundation', '-o', str(binary)], check=True)
            for row, scenario, hooks, reason, ready in (
                    (arm64, 'valid', 2, 0, 1),
                    (arm64, 'unknown', 0, 2, 2),
                    (arm64, 'changed-entry', 0, 7, 2),
                    (arm64, 'arm64e-adapter', 0, 3, 2),
                    (arm64e, 'arm64e-adapter', 2, 0, 1),
                    (early, 'valid', 0, 11, 2),
                    (arm64e, 'valid', 0, 3, 2)):
                with self.subTest(sample=row['sample'], scenario=scenario):
                    result = subprocess.run([str(binary), row['uuid'].replace('-', ''),
                        row['cpu_type'], row['cpu_subtype'], row['update_offset'], row['event_offset'],
                        row['update_prefix'], row['event_prefix'], scenario, str(hooks), str(reason),
                        str(ready)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('Actual loader identity, lifecycle, CPU and prologue gates passed', result.stdout)
