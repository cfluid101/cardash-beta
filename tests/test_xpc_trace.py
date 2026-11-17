"""Real local NSXPC transport regression tests; no phone or CarKit framework."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class XPCTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = ROOT / 'build/host/xpc-trace-tests'
        cls.binary.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([
            'xcrun', 'clang++', '-std=c++17', '-fobjc-arc', '-fblocks',
            '-Wall', '-Wextra', '-Werror', '-DCD_HOST_TEST=1', '-I', str(ROOT / 'src'),
            str(ROOT / 'tests/XPCTraceTests.mm'), str(ROOT / 'src/XPCTrace.mm'),
            '-framework', 'Foundation', '-o', str(cls.binary),
        ], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_case(self, mode):
        result = subprocess.run([str(self.binary), mode], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for line in result.stdout.splitlines():
            self.assertIsInstance(json.loads(line), dict)
            self.assertLess(len(line.encode()), 16 * 1024)

    def test_original_async_error_and_invalidation_are_preserved(self):
        self.run_case('missing-async')

    def test_synchronous_error_is_not_deferred(self):
        self.run_case('missing-sync')

    def test_plain_proxy_failure_is_observed(self):
        self.run_case('missing-plain')

    def test_one_way_failure_is_reported_by_invalidation(self):
        self.run_case('missing-oneway')

    def test_success_and_untracked_connections_are_not_changed(self):
        self.run_case('success-untracked')

    def test_replaced_connection_and_concurrent_errors_are_observed(self):
        self.run_case('replacement-concurrency')

    def test_existing_interruption_handler_is_preserved(self):
        self.run_case('interruption')

    def test_error_causes_and_unicode_respect_the_report_limit(self):
        self.run_case('error-bounds')

    def test_unexpected_classes_and_non_xpc_values_are_not_instrumented(self):
        self.run_case('guarded-registration')

    def test_foreign_getter_implementation_is_not_hooked(self):
        self.run_case('foreign-getter-owner')

    def test_handler_setup_failure_is_reported_and_retried_without_duplication(self):
        self.run_case('handler-setup-failure')

    def test_remote_protocol_inventory_includes_inherited_optional_block_methods(self):
        self.run_case('protocol-metadata')

    def test_protocol_inventory_is_bounded_and_reports_unavailable_metadata(self):
        self.run_case('protocol-bounds')

    def test_concurrent_setup_retries_preserve_real_lifecycle_callbacks(self):
        self.run_case('concurrent-retry-lifecycle')


if __name__ == '__main__':
    unittest.main()
