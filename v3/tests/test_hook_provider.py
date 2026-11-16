from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class HookProviderTest(unittest.TestCase):
    def test_provider_order_fallbacks_and_missing_symbol(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'hook-provider'
            subprocess.run(['xcrun', 'clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'v3/tests/hook_provider_harness.cpp'), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('Hook provider resolution cases passed', result.stdout)

    def test_every_adapter_uses_the_shared_resolver(self):
        for name in ('Loopback.mm', 'VideoBudget.mm', 'AudioRoute.mm'):
            source = (ROOT / 'v3/native' / name).read_text()
            self.assertIn('CDV3ResolveHookFunction(', source, name)
            self.assertNotIn('dlopen("/var/jb/usr/lib/libsubstrate.dylib"', source, name)


if __name__ == '__main__':
    unittest.main()
