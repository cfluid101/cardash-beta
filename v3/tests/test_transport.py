import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from transport import transport_status, startup_failure

class TransportTest(unittest.TestCase):
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
