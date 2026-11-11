from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class HostProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='cardash-host-profile-')
        cls.binary = Path(cls.tmp.name) / 'host-profile-fixture'
        sources = ['v3/tests/host_profile_fixture.mm', 'v3/native/HostProfile.mm',
                   'src/Common.m', 'src/NativeIdentity.mm', 'src/HostPayload.mm']
        result = subprocess.run([
            'xcrun', 'clang++', '-x', 'objective-c++', '-std=c++17', '-fobjc-arc',
            '-fblocks', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
            '-DCD_HOST_TEST=1', '-I', str(ROOT / 'src'), '-I', str(ROOT / 'v3/native'),
            *[str(ROOT / path) for path in sources], '-framework', 'Foundation',
            '-o', str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, mode):
        result = subprocess.run([str(self.binary), mode], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, 'OK\n')

    def test_profile_selection_keeps_unknown_and_incompatible_targets_closed(self):
        for mode in ('profile-new', 'profile-legacy', 'profile-unknown',
                     'profile-different-build', 'profile-legacy-unverified', 'profile-wrong-start-type'):
            with self.subTest(mode=mode):
                self.run_case(mode)

    def test_verified_dictionary_fields_survive_actual_secure_archive(self):
        self.run_case('valid')

    def test_live_and_wire_field_mismatches_are_rejected(self):
        for mode in ('corrupt-live', 'wrong-live-type', 'corrupt-wire', 'wrong-wire-type',
                     'archive-throws', 'secure-disabled'):
            with self.subTest(mode=mode):
                self.run_case(mode)

    def test_invalid_types_and_foreign_implementations_never_construct(self):
        for mode in ('wrong-method-type', 'invalid-key-type', 'invalid-key-hex', 'production-owner-reject'):
            with self.subTest(mode=mode):
                self.run_case(mode)


if __name__ == '__main__':
    unittest.main()
