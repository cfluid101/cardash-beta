"""Audio readiness must identify the failing guard without changing the readiness ABI."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from transport import audio_route_status


class AudioStatusTest(unittest.TestCase):
    def status(self, code, **kwargs):
        return audio_route_status(probe=lambda: (123 << 8) | code,
                                  alive=kwargs.pop('alive', lambda _: None), **kwargs)

    def test_unknown_framework_requests_evidence_instead_of_reinstallation(self):
        status = self.status(3)
        self.assertFalse(status['ready'])
        self.assertEqual((status['pid'], status['code'], status['reasonCode']), (123, 3, 3))
        self.assertEqual(status['reason'], 'unsupported_image_identity_or_cpu')
        self.assertIn('MediaExperience', status['error'])
        self.assertIn('Export Diagnostics', status['advice'])
        self.assertIn('reinstalling will not add', status['advice'])
        self.assertIn('Browser audio', status['advice'])

    def test_each_native_guard_has_a_stable_reason(self):
        reasons = {2: 'initialization_incomplete', 4: 'text_segment_mismatch',
                   5: 'data_segment_mismatch', 6: 'hook_provider_unavailable',
                   7: 'setter_mapping_mismatch', 8: 'flag_mapping_mismatch',
                   9: 'setter_prologue_mismatch', 10: 'flag_value_invalid',
                   11: 'hook_installation_failed'}
        for code, reason in reasons.items():
            with self.subTest(code=code):
                status = self.status(code)
                self.assertFalse(status['ready'])
                self.assertEqual((status['reasonCode'], status['reason']), (code, reason))
                self.assertIn('Export Diagnostics', status['advice'])
        self.assertIn('ElleKit', self.status(6)['advice'])
        future = self.status(99)
        self.assertFalse(future['ready'])
        self.assertEqual((future['reasonCode'], future['reason']), (99, 'unknown_readiness_code'))

    def test_ready_keeps_live_ownership_fields_and_optional_state_failure(self):
        status = self.status(1, state_probe=lambda: (123 << 16) | 14)
        self.assertTrue(status['ready'])
        self.assertEqual(status['reasonCode'], 0)
        self.assertEqual(status['error'], '')
        self.assertTrue(status['ownHost'] and status['leaseValid'] and status['deviceOutputActive'])
        self.assertNotIn('advice', status)
        self.assertFalse(self.status(1, state_probe=lambda: (999 << 16) | 14)['deviceOutputActive'])
        def missing(): raise OSError('optional state unavailable')
        self.assertTrue(self.status(1, state_probe=missing)['ready'])

    def test_missing_or_dead_process_cannot_be_reported_as_a_live_guard_failure(self):
        status = audio_route_status(probe=lambda: 0)
        self.assertFalse(status['ready'])
        self.assertEqual(status['reason'], 'adapter_not_loaded')
        def dead(_): raise ProcessLookupError('old media process')
        for code in (1, 3):
            status = self.status(code, alive=dead)
            self.assertFalse(status['ready'])
            self.assertEqual(status['reason'], 'publisher_not_running')
            self.assertNotIn('reasonCode', status)
