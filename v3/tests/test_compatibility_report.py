import json
import asyncio
from pathlib import Path
import sys
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import compatibility


class CompatibilityReportTest(unittest.TestCase):
    def inputs(self):
        inventory = {'complete': True, 'pid': 123, 'frameworks': {
            name: {'state': 'observed', 'cpuType': 0x100000c, 'cpuSubtype': 0,
                   'uuid': '00112233-4455-6677-8899-AABBCCDDEEFF'}
            for name in ('aptransport', 'airplaysender', 'mediaexperience')}}
        inspection = {'complete': True, 'inspection': {'complete': True,
            'host_profile': {'profile_matched': True, 'selected_profile': 'fixture',
                             'request_family': 'host_completion'}}}
        status = {'version': 'beta9', 'active': False, 'nativeFrames': 0,
                  'audioOutput': 'phone', 'native': {},
                  **{name: {'ready': True, 'pid': 123, 'code': 1}
                     for name in ('transport', 'videoBudget', 'audioRouting')}}
        return inventory, inspection, status

    def report(self, *args):
        function = getattr(compatibility, 'compatibility_summary', None)
        self.assertIsNotNone(function, 'Diagnostic export must explain component failures')
        return function(*args)

    def test_ready_adapters_do_not_claim_device_success(self):
        report = self.report(*self.inputs())
        self.assertEqual(report['verdict'], 'ready_for_device_trial')
        self.assertFalse(report['session_observed'])
        self.assertEqual(report['issues'], [])
        self.assertEqual(report['components']['session']['request_family'], 'host_completion')

    def test_failure_stage_and_observed_identity_are_preserved(self):
        inv, ins, status = self.inputs()
        status['transport'] = {'ready': False, 'pid': 123, 'code': 2, 'reasonCode': 7,
                               'error': 'entry mismatch'}
        report = self.report(inv, ins, status)
        self.assertEqual(report['verdict'], 'blocked')
        self.assertEqual(report['issues'][0]['code'], 'transport_instruction_mismatch')
        self.assertEqual(report['components']['transport']['identity']['uuid'],
                         '00112233-4455-6677-8899-AABBCCDDEEFF')
        self.assertIn('Export', report['issues'][0]['next_step'])

    def test_stale_or_missing_inventory_never_confirms_media_readiness(self):
        for change in ({'complete': False}, {'pid': 999}):
            inv, ins, status = self.inputs(); inv.update(change)
            report = self.report(inv, ins, status)
            self.assertEqual(report['verdict'], 'blocked')
            self.assertFalse(report['components']['transport']['ready'])
            self.assertIn('media_inventory_unverified', {i['code'] for i in report['issues']})

    def test_unknown_identity_and_unsupported_lifecycle_have_different_codes(self):
        for reason, code in ((2, 'transport_identity_unsupported'),
                             (11, 'transport_lifecycle_unsupported')):
            inv, ins, status = self.inputs()
            status['transport'].update(ready=False, code=2, reasonCode=reason)
            self.assertIn(code, {i['code'] for i in self.report(inv, ins, status)['issues']})

    def test_optional_audio_failure_is_diagnostic_without_blocking_browser_audio(self):
        inv, ins, status = self.inputs(); status['audioOutput'] = 'browser'
        status['audioRouting'].update(ready=False, code=2)
        report = self.report(inv, ins, status)
        self.assertEqual(report['verdict'], 'ready_for_device_trial')
        self.assertEqual(report['issues'][0]['severity'], 'optional')

    def test_missing_helper_is_explicit_even_when_media_loaded(self):
        inv, ins, status = self.inputs(); ins = {'complete': False, 'error': 'missing helper'}
        report = self.report(inv, ins, status)
        self.assertIn('session_inspection_unavailable', {i['code'] for i in report['issues']})
        self.assertEqual(report['components']['session']['error'], 'missing helper')

    def test_only_active_native_video_counts_as_session_observed(self):
        inv, ins, status = self.inputs()
        status.update(active=True, nativeFrames=3, native={'present': True, 'authenticated': True})
        self.assertTrue(self.report(inv, ins, status)['session_observed'])
        status['active'] = False
        self.assertFalse(self.report(inv, ins, status)['session_observed'])

    def test_report_allowlists_fields_and_bounds_strings(self):
        inv, ins, status = self.inputs()
        status.update(token='secret-token', session='secret-session')
        status['transport'].update(privateKey='secret-key', error='x' * 50000)
        inv['frameworks']['aptransport']['token'] = 'secret-inventory'
        ins['inspection']['host_profile']['credentials'] = 'secret-host'
        report = self.report(inv, ins, status); text = json.dumps(report)
        self.assertNotIn('secret-', text)
        self.assertLess(len(text), 20000)
        self.assertLessEqual(len(report['components']['transport']['error']), 1024)


class FailureExportTest(unittest.IsolatedAsyncioTestCase):
    async def test_completion_failure_survives_exit_without_a_second_diagnostic_event(self):
        from server import Receiver
        with tempfile.TemporaryDirectory() as folder:
            receiver = Receiver(SimpleNamespace(state=folder, port=0, capture=None, helper='/missing'))
            reader = asyncio.StreamReader()
            reader.feed_data(json.dumps({'event': 'native_completion', 'success': False,
                                         'error': 'CARSessionErrorDomain (42)'}).encode() + b'\n')
            reader.feed_eof()
            async def exited(): return 5
            child = SimpleNamespace(stdout=reader, wait=exited, returncode=5)
            receiver.helper=child; receiver.generation='test'; receiver.active=True
            await receiver.watch_helper(child, 'test')
            self.assertIn('CARSessionErrorDomain (42)', receiver.error)
            self.assertFalse(receiver.active)

    async def test_helper_exit_keeps_specific_native_failure_for_user(self):
        from server import Receiver
        with tempfile.TemporaryDirectory() as folder:
            receiver = Receiver(SimpleNamespace(state=folder, port=0, capture=None, helper='/missing'))
            reader = asyncio.StreamReader()
            reader.feed_data(json.dumps({'event': 'compatibility_failure', 'stage': 'host_profile',
                                         'diagnostic_code': 'unknown_carkit_identity'}).encode() + b'\n')
            reader.feed_eof()
            async def exited(): return 5
            child = SimpleNamespace(stdout=reader, wait=exited, returncode=5)
            receiver.helper=child; receiver.generation='test'; receiver.active=True
            await receiver.watch_helper(child, 'test')
            self.assertIn('unknown_carkit_identity', receiver.error)
            self.assertIn('host_profile', receiver.error)
            self.assertFalse(receiver.active)

    async def test_failed_start_is_logged_without_spawning_or_leasing(self):
        from server import Receiver
        with tempfile.TemporaryDirectory() as folder:
            receiver = Receiver(SimpleNamespace(state=folder, port=0, capture=None, helper='/missing'))
            accessory = Path(folder) / 'accessory'; accessory.mkdir()
            for name in ('identity.pk8', 'certificate.p7b'): (accessory / name).write_bytes(b'fixture')
            with patch('server.transport_status', return_value={'ready': False, 'reasonCode': 2,
                                                               'error': 'unknown firmware'}):
                with self.assertRaisesRegex(ValueError, 'unknown firmware'):
                    await receiver.start()
            self.assertIsNone(receiver.helper)
            self.assertFalse(receiver.audio_lease.tokens)
            rows = [json.loads(line) for line in (Path(folder) / 'diagnostic.ndjson').read_text().splitlines()]
            failures = [row for row in rows if row['event'] == 'compatibility_failure']
            self.assertTrue(failures, 'A failed startup gate must survive in exported logs')
            self.assertEqual(failures[-1]['stage'], 'transport')
            self.assertEqual(failures[-1]['reasonCode'], 2)

    async def test_export_includes_summary_when_service_cannot_start_session(self):
        from server import Receiver
        with tempfile.TemporaryDirectory() as folder:
            receiver = Receiver(SimpleNamespace(state=folder, port=0, capture=None, helper='/missing'))
            with patch('server.inventory_status', return_value={'event': 'native_media_inventory', 'complete': False, 'error': 'not injected'}), \
                 patch('server.inspect_session_helper', AsyncMock(return_value={'event': 'native_session_inspection', 'complete': False, 'error': 'missing helper'})):
                response = await receiver.action({'action': 'report'}, local=True)
            rows = [json.loads(line) for line in response['report'].splitlines()]
            summaries = [row for row in rows if row['event'] == 'compatibility_summary']
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0]['verdict'], 'blocked')
            self.assertFalse(receiver.active)


if __name__ == '__main__': unittest.main()
