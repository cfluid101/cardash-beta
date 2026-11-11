import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from transport import transport_status, startup_failure, audio_route_status

class TransportTest(unittest.TestCase):
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

    def test_startup_deadline_does_not_limit_streaming_sessions(self):
        self.assertEqual(startup_failure(True,0,100,144),'')
        self.assertIn('45 seconds',startup_failure(True,0,100,145))
        self.assertEqual(startup_failure(True,100,100,1000000),'')
        self.assertEqual(startup_failure(False,0,100,1000000),'')
        self.assertIn('example error',startup_failure(True,0,100,101,'example error'))
