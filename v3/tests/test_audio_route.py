from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AudioRouteTest(unittest.TestCase):
    def test_native_audio_lease_and_restoration(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'audio-route-test'
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fobjc-arc',
                            '-fblocks', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'v3/tests/audio_route_harness.mm'),
                            '-framework', 'Foundation', '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('concurrent-callback checks passed', result.stdout)
