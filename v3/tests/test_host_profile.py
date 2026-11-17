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

    def test_ios1541_profile_selects_dictionary_path_with_its_verified_completion(self):
        for mode in ('profile-new-ios15', 'profile-different-build-ios15'):
            with self.subTest(mode=mode):
                self.run_case(mode)

    def test_sweep_profiles_select_and_validate_real_archives(self):
        for suffix in ('-15early', '-15late', '-16arm64', '-16arm64e', '-17early', '-17late'):
            for mode in ('profile-new', 'profile-different-build', 'profile-unknown',
                         'profile-wrong-start-type', 'profile-mixed-method-uuid',
                         'profile-foreign-method-owner', 'valid', 'corrupt-live', 'corrupt-wire'):
                with self.subTest(mode=mode + suffix):
                    self.run_case(mode + suffix)

    def test_authentication_fields_are_checked_before_and_after_secure_coding(self):
        for suffix in ('-16arm64e', '-17early', '-17late'):
            modes = ['mutual-live', 'mutual-wire']
            if suffix.startswith('-17'):
                modes += ['serial-live', 'serial-wire', 'vehicle-live', 'vehicle-wire']
            for mode in modes:
                with self.subTest(mode=mode + suffix):
                    self.run_case(mode + suffix)

    def test_actual_request_dispatch_preserves_both_callback_arguments(self):
        for suffix in ('', '-ios15', '-15early', '-15late', '-16arm64', '-16arm64e', '-17early', '-17late', '-legacy'):
            for mode in ('dispatch-valid', 'dispatch-unknown', 'dispatch-stale-image', 'dispatch-wrong-method'):
                with self.subTest(mode=mode + suffix):
                    self.run_case(mode + suffix)

    def test_dictionary_profiles_reject_mixed_or_foreign_method_images(self):
        for suffix in ('', '-ios15'):
            for mode in ('profile-unknown', 'profile-mixed-method-uuid',
                         'profile-unknown-method-uuid', 'profile-foreign-method-owner',
                         'profile-foreign-class-image', 'profile-foreign-implementation-image',
                         'profile-wrong-start-type'):
                with self.subTest(mode=mode + suffix):
                    self.run_case(mode + suffix)

    def test_verified_dictionary_fields_survive_actual_secure_archive(self):
        for mode in ('valid', 'valid-ios15'):
            with self.subTest(mode=mode):
                self.run_case(mode)

    def test_live_and_wire_field_mismatches_are_rejected(self):
        for suffix in ('', '-ios15'):
            for mode in ('corrupt-live', 'wrong-live-type', 'corrupt-wire', 'wrong-wire-type',
                         'archive-throws', 'secure-disabled'):
                with self.subTest(mode=mode + suffix):
                    self.run_case(mode + suffix)

    def test_invalid_types_and_foreign_implementations_never_construct(self):
        for suffix in ('', '-ios15'):
            for mode in ('wrong-method-type', 'invalid-key-type', 'invalid-key-hex',
                         'production-owner-reject', 'mixed-method-uuid',
                         'unknown-method-uuid', 'foreign-method-owner'):
                with self.subTest(mode=mode + suffix):
                    self.run_case(mode + suffix)


if __name__ == '__main__':
    unittest.main()
