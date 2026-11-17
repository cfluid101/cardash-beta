import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from compatibility import inventory_status, inspect_session_helper, PREFIX
from compatibility import media_process_alive
from unittest.mock import patch, AsyncMock


class InventoryTest(unittest.TestCase):
    def test_reused_pid_from_another_process_is_rejected(self):
        import ctypes
        from types import SimpleNamespace
        def process_path(pid, buffer, length):
            buffer.value = b'/usr/bin/unrelated'
            return len(buffer.value)
        with patch('compatibility.os.kill'), patch('compatibility.ctypes.CDLL', return_value=SimpleNamespace(proc_pidpath=process_path)):
            with self.assertRaisesRegex(ValueError, 'not the current media service'): media_process_alive(123)

    def sample(self):
        return {'snapshot': (123 << 32) | 2, 'cpu': (0x100000c << 32) | 0x80000002,
                'status': 7, 'failure': 0, 'aptransport.state': 1,
                'aptransport.cpu': (0x100000c << 32) | 2,
                'aptransport.uuid0': 0x0011223344556677,
                'aptransport.uuid1': 0x8899aabbccddeeff}

    def read(self, values, alive=lambda pid: None):
        return inventory_status(probe=lambda name: values.get(name.decode().removeprefix(PREFIX + '.'), 0), alive=alive)

    def test_committed_observed_identities_and_capability_bits(self):
        result = self.read(self.sample())
        self.assertTrue(result['complete'])
        self.assertEqual(result['adapter']['cpuSubtype'], 0x80000002)
        self.assertEqual(result['frameworks']['aptransport']['uuid'], '00112233-4455-6677-8899-AABBCCDDEEFF')
        self.assertEqual(result['frameworks']['mediaexperience']['state'], 'not_observed')
        self.assertNotIn('uuid', result['frameworks']['mediaexperience'])

    def test_missing_odd_and_failed_publications_do_not_claim_complete(self):
        for change in ({'snapshot': 0}, {'snapshot': (123 << 32) | 3},
                       {'failure': (123 << 32) | (3 << 24) | (7 << 16) | 9}):
            value = self.sample(); value.update(change)
            self.assertFalse(self.read(value)['complete'])

    def test_failed_registration_or_partial_write_preserves_notification_error(self):
        for snapshot, phase in ((0, 1), ((123 << 32) | 3, 3)):
            value = self.sample(); value.update(snapshot=snapshot, failure=(123 << 32) | (phase << 24) | (4 << 16) | 9)
            result = self.read(value)
            self.assertFalse(result['complete'])
            self.assertEqual(result['publicationFailure']['notifyStatus'], 9)
            self.assertEqual(result['publicationFailure']['phase'], phase)
            self.assertTrue(result['publicationFailure']['publisherVerified'])

    def test_changed_snapshot_dead_pid_and_notification_errors(self):
        value = self.sample(); calls = 0
        def probe(name):
            nonlocal calls
            if name.endswith(b'.snapshot'):
                calls += 1
                return value['snapshot'] + (2 if calls > 1 else 0)
            return value.get(name.decode().removeprefix(PREFIX + '.'), 0)
        self.assertFalse(inventory_status(probe=probe, alive=lambda pid: None)['complete'])
        def dead(pid): raise ProcessLookupError('gone')
        self.assertFalse(self.read(value, dead)['complete'])
        def denied(name): raise OSError('notify error 5')
        self.assertIn('notify error 5', inventory_status(probe=denied)['error'])

    def test_parse_errors_and_ambiguity_never_become_valid_uuids(self):
        for state in (2, 3, 99):
            value = self.sample(); value['aptransport.state'] = (8 << 32) | state
            record = self.read(value)['frameworks']['aptransport']
            self.assertNotIn('uuid', record)
            self.assertEqual(record['parseError'], 8)


class InspectionTest(unittest.IsolatedAsyncioTestCase):
    def helper(self, root, body):
        path = Path(root) / 'helper'
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o700)
        return str(path)

    async def test_inspect_only_and_valid_record(self):
        with tempfile.TemporaryDirectory() as root:
            helper = self.helper(root, '''import json,sys
assert sys.argv[1:]==['--inspect']
print(json.dumps({'event':'native_inspection','schema_version':1,'inspection_kind':'carkit','read_only':True,'session_requested':False,'complete':True,'machine':'fixture'}))
''')
            record = await inspect_session_helper(helper)
            self.assertTrue(record['complete'])
            self.assertEqual(record['inspection']['machine'], 'fixture')

    async def test_missing_timeout_oversize_and_invalid_record_are_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            result = await inspect_session_helper(str(Path(root) / 'missing'))
            self.assertFalse(result['complete'])
            for body in ('import time;time.sleep(10)', 'print("x"*100000)',
                         'print("not JSON")', 'print("{}")'):
                helper = self.helper(root, body)
                result = await inspect_session_helper(helper, timeout=0.3, limit=4096)
                self.assertFalse(result['complete'])
                self.assertTrue(result['error'])

    async def test_nonzero_exit_still_reports_valid_inspection_but_not_completion(self):
        with tempfile.TemporaryDirectory() as root:
            helper = self.helper(root, '''import json,sys
print(json.dumps({'event':'native_inspection','schema_version':1,'inspection_kind':'carkit','read_only':True,'session_requested':False}))
sys.exit(4)
''')
            result = await inspect_session_helper(helper)
            self.assertFalse(result['complete'])
            self.assertEqual(result['returncode'], 4)
            self.assertEqual(result['inspection']['event'], 'native_inspection')

    async def test_zero_exit_with_incomplete_record_is_not_success(self):
        with tempfile.TemporaryDirectory() as root:
            helper = self.helper(root, '''import json
print(json.dumps({'event':'native_inspection','schema_version':1,'inspection_kind':'carkit','read_only':True,'session_requested':False,'complete':False}))
''')
            record = await inspect_session_helper(helper)
            self.assertFalse(record['complete'])
            self.assertIn('did not complete', record['error'])

    async def test_cancel_reaps_child(self):
        with tempfile.TemporaryDirectory() as root:
            pidfile = Path(root) / 'pid'
            helper = self.helper(root, f'import os,time\nopen({str(pidfile)!r},"w").write(str(os.getpid()))\ntime.sleep(10)')
            task = asyncio.create_task(inspect_session_helper(helper))
            for _ in range(100):
                if pidfile.exists(): break
                await asyncio.sleep(.01)
            self.assertTrue(pidfile.exists())
            pid = int(pidfile.read_text()); task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    async def test_export_collects_all_inspections_when_startup_is_unavailable(self):
        from server import Receiver
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as root:
            receiver = Receiver(SimpleNamespace(state=root, port=0, capture=None, helper='/configured-helper'))
            receiver.start = AsyncMock(side_effect=AssertionError('Must not start a session'))
            inspection = {'event': 'native_session_inspection', 'complete': True}
            inventory = {'event': 'native_media_inventory', 'complete': False, 'error': 'not loaded'}
            with patch('server.inspect_session_helper', AsyncMock(return_value=inspection)) as inspect, \
                 patch('server.inventory_status', return_value=inventory):
                response = await receiver.action({'action': 'report'}, local=True)
                rows = [json.loads(line) for line in response['report'].splitlines()]
                self.assertIn(inspection, rows); self.assertIn(inventory, rows)
                inspect.assert_awaited_once_with('/configured-helper')
                self.assertFalse(response['status']['transport']['ready'])
                receiver.start.assert_not_called()

    async def test_concurrent_export_does_not_launch_duplicate_inspector(self):
        from server import Receiver
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as root:
            receiver = Receiver(SimpleNamespace(state=root, port=0, capture=None, helper='/configured-helper'))
            await receiver.inspection_lock.acquire()
            try:
                with patch('server.inspect_session_helper', AsyncMock()) as inspect:
                    response = await receiver.action({'action': 'report'}, local=True)
                    rows = [json.loads(line) for line in response['report'].splitlines()]
                    row = next(row for row in rows if row['event'] == 'native_session_inspection')
                    self.assertFalse(row['complete']); self.assertIn('progress', row['error'])
                    inspect.assert_not_called()
            finally: receiver.inspection_lock.release()
