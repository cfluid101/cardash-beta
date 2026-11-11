import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from transport import transport_status, startup_failure, audio_route_status

class TransportTest(unittest.TestCase):
    def setUp(self):
        notifications=patch('transport.notification_state',return_value=0)
        notifications.start();self.addCleanup(notifications.stop)

    def test_failure_retains_observed_pid_and_status_without_guessing_identity(self):
        for reader in (transport_status, audio_route_status):
            result=reader(probe=lambda:(123<<8)|2,alive=lambda pid:None)
            self.assertFalse(result['ready'])
            self.assertEqual(result['pid'],123)
            self.assertEqual(result['code'],2)
        result=transport_status(probe=lambda:(123<<8)|1,alive=lambda pid:None)
        self.assertNotIn('imageUUID',result)
        self.assertEqual(result['code'],1)

    def test_missing_failed_dead_and_ready_adapter(self):
        self.assertFalse(transport_status(probe=lambda:0)['ready'])
        self.assertFalse(transport_status(probe=lambda:123*256+2,alive=lambda p:None)['ready'])
        def dead(pid):raise ProcessLookupError(pid)
        self.assertFalse(transport_status(probe=lambda:123*256+1,alive=dead)['ready'])
        self.assertTrue(transport_status(probe=lambda:123*256+1,alive=lambda p:None)['ready'])
        def unavailable():raise OSError('notify unavailable')
        self.assertFalse(transport_status(probe=unavailable)['ready'])

    def test_optional_missing_or_failed_reason_preserves_old_readiness(self):
        def unavailable():raise OSError('reason channel unavailable')
        for code in (1,2):
            for detail in (lambda:0,unavailable):
                result=transport_status(probe=lambda:(123<<8)|code,alive=lambda pid:None,reason_probe=detail)
                self.assertEqual(result['ready'],code==1)
                self.assertEqual((result['pid'],result['code']),(123,code))
                self.assertNotIn('reasonCode',result)
                self.assertNotIn('reason',result)
                if code==2:self.assertIn('exact-firmware or hook-provider check',result['error'])

    def test_matching_live_reason_preserves_code_and_explains_failure(self):
        result=transport_status(probe=lambda:(123<<8)|2,alive=lambda pid:None,
                                reason_probe=lambda:(123<<32)|(2<<16)|7)
        self.assertFalse(result['ready']);self.assertEqual(result['code'],2)
        self.assertEqual(result['reasonCode'],7)
        self.assertEqual(result['reason'],'transport entry instruction fingerprint mismatch')
        self.assertIn(result['reason'],result['error'])
        ready=transport_status(probe=lambda:(123<<8)|1,alive=lambda pid:None,
                               reason_probe=lambda:(123<<32)|(1<<16))
        self.assertTrue(ready['ready']);self.assertEqual(ready['error'],'')
        self.assertEqual(ready['reasonCode'],0)

    def test_stale_conflicting_and_changing_sideband_is_ignored(self):
        for detail in ((122<<32)|(2<<16)|7, # different media process
                       (123<<32)|(1<<16),   # earlier successful readiness
                       (123<<32)|(2<<16)):  # success reason cannot describe failure
            result=transport_status(probe=lambda:(123<<8)|2,alive=lambda pid:None,reason_probe=lambda:detail)
            self.assertFalse(result['ready']);self.assertNotIn('reasonCode',result)
        changed=iter(((123<<8)|2,(123<<8)|1))
        result=transport_status(probe=lambda:next(changed),alive=lambda pid:None,
                                reason_probe=lambda:(123<<32)|(2<<16)|7)
        self.assertFalse(result['ready']);self.assertNotIn('reasonCode',result)
        result=transport_status(probe=lambda:(123<<8)|1,alive=lambda pid:None,
                                reason_probe=lambda:(123<<32)|(1<<16)|7)
        self.assertTrue(result['ready']);self.assertNotIn('reasonCode',result)

    def test_dead_publisher_and_unknown_future_reason_cannot_enable_adapter(self):
        def dead(pid):raise ProcessLookupError(pid)
        detail=Mock(return_value=(123<<32)|(1<<16))
        result=transport_status(probe=lambda:(123<<8)|1,alive=dead,reason_probe=detail)
        self.assertFalse(result['ready']);detail.assert_not_called()
        result=transport_status(probe=lambda:(123<<8)|2,alive=lambda pid:None,
                                reason_probe=lambda:(123<<32)|(2<<16)|999)
        self.assertFalse(result['ready']);self.assertEqual(result['reasonCode'],999)
        self.assertNotIn('reason',result)
        self.assertIn('exact-firmware or hook-provider check',result['error'])

    def test_startup_deadline_does_not_limit_streaming_sessions(self):
        self.assertEqual(startup_failure(True,0,100,144),'')
        self.assertIn('45 seconds',startup_failure(True,0,100,145))
        self.assertEqual(startup_failure(True,100,100,1000000),'')
        self.assertEqual(startup_failure(False,0,100,1000000),'')
        self.assertIn('example error',startup_failure(True,0,100,101,'example error'))
