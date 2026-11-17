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

    def test_each_failure_tells_the_tester_what_can_actually_help(self):
        def failed(reason):
            return transport_status(probe=lambda:(123<<8)|2,alive=lambda pid:None,build='20H19',
                                    reason_probe=lambda:(123<<32)|(2<<16)|reason)
        unsupported=failed(2)
        self.assertEqual(unsupported['build'],'20H19')
        self.assertIn('This iOS build (20H19) is not supported by this beta yet',unsupported['error'])
        self.assertIn('reinstalling will not change that',unsupported['error'])
        self.assertIn('Export Diagnostics',unsupported['advice'])
        # The stable diagnostic text testers already quote is still present.
        self.assertTrue(unsupported['error'].startswith('USB-free transport is unavailable: adapter unavailable: unsupported APTransport firmware UUID or CPU'))
        self.assertIn('ElleKit',failed(4)['error']);self.assertNotIn('not supported by this beta yet',failed(4)['error'])
        self.assertIn('matching arm64 or arm64e adapter slice',failed(3)['advice'])
        for reason in (5,6,7):
            with self.subTest(reason=reason):
                self.assertIn('a safety check failed, so nothing was patched',failed(reason)['error'])
        for reason in (8,9):
            with self.subTest(reason=reason):
                self.assertIn('hook attempt failed',failed(reason)['advice'])
                self.assertIn('Session startup is blocked',failed(reason)['advice'])
                self.assertNotIn('nothing was patched',failed(reason)['advice'])
        self.assertIn('after the update hook was installed',failed(9)['advice'])
        self.assertIn('forwarded this native callback',failed(10)['advice'])
        self.assertNotIn('nothing was patched',failed(10)['advice'])
        lifecycle=failed(11)
        self.assertEqual(lifecycle['reasonCode'],11)
        self.assertIn('lifecycle is not implemented; no hooks installed',lifecycle['error'])
        self.assertIn('USB-disconnect ownership path',lifecycle['advice'])
        self.assertIn('reinstalling does not add',lifecycle['advice'])
        missing=transport_status(probe=lambda:0)
        self.assertIn('has not loaded the CarDash adapter',missing['error']);self.assertIn('userspace reboot',missing['advice'])
        ready=transport_status(probe=lambda:(123<<8)|1,alive=lambda pid:None)
        self.assertEqual(ready['error'],'');self.assertNotIn('advice',ready);self.assertNotIn('build',ready)
        # An unreadable build never breaks the message.
        self.assertIn('This iOS build is not supported',transport_status(probe=lambda:(123<<8)|2,alive=lambda pid:None,build='',reason_probe=lambda:(123<<32)|(2<<16)|2)['error'])

    def test_os_build_is_bounded_and_fails_closed(self):
        from transport import os_build
        class Library:
            def __init__(self,value,code=0):self.value=value;self.code=code
            def sysctlbyname(self,name,buffer,size,new,newlen):
                buffer.value=self.value;return self.code
        self.assertEqual(os_build(Library(b'20G75')),'20G75')
        self.assertEqual(os_build(Library(b'20G75',code=-1)),'')
        self.assertEqual(os_build(Library(b'../etc')),'')
        self.assertEqual(os_build(object()),'')

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
