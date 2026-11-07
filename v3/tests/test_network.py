import ctypes
import errno
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'v3/backend'))
from network import TeslaNetwork, allowed_peer


class NetworkAliasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        source = ROOT / 'v3/native/Network.c'
        if not source.exists():
            raise AssertionError('V3 has no native Tesla-address setup implementation')
        library = Path(cls.tmp.name) / 'network.dylib'
        subprocess.run(['xcrun', 'clang', '-dynamiclib', '-Wall', '-Wextra', '-Werror',
                        '-DCD_NETWORK_TEST', str(source), '-o', str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lookup_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t)
        cls.add_type = ctypes.CFUNCTYPE(ctypes.c_int)
        cls.lib.cd_network_ensure_with.argtypes = [cls.lookup_type, cls.add_type,
                                                   ctypes.c_void_p, ctypes.c_size_t,
                                                   ctypes.POINTER(ctypes.c_int)]
        cls.lib.cd_network_ensure_with.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def scenario(self, initial=None, add_error=0, after='lo0', lookup_error=0):
        current = initial
        calls = []
        @self.lookup_type
        def lookup(buffer, capacity):
            if lookup_error:
                return lookup_error
            if current is None:
                return errno.EADDRNOTAVAIL
            data = current.encode() + b'\0'
            assert len(data) <= capacity
            ctypes.memmove(buffer, data, len(data))
            return 0
        @self.add_type
        def add():
            nonlocal current
            calls.append('add')
            current = after
            return add_error
        output = ctypes.create_string_buffer(32)
        added = ctypes.c_int()
        result = self.lib.cd_network_ensure_with(lookup, add, output, len(output), ctypes.byref(added))
        return result, output.value, added.value, calls

    def test_fresh_install_creates_and_verifies_missing_alias(self):
        self.assertEqual(self.scenario(), (0, b'lo0', 1, ['add']))

    def test_existing_alias_is_reused_without_modification(self):
        self.assertEqual(self.scenario(initial='lo0'), (0, b'lo0', 0, []))

    def test_address_on_another_interface_is_never_modified(self):
        self.assertEqual(self.scenario(initial='pdp_ip0'), (errno.EADDRINUSE, b'pdp_ip0', 0, []))

    def test_permission_failure_does_not_claim_address_is_ready(self):
        self.assertEqual(self.scenario(add_error=errno.EPERM, after=None),
                         (errno.EPERM, b'', 0, ['add']))

    def test_successful_ioctl_without_readback_is_not_ready(self):
        self.assertEqual(self.scenario(after=None), (errno.EADDRNOTAVAIL, b'', 0, ['add']))

    def test_concurrent_creator_is_accepted_only_after_readback(self):
        self.assertEqual(self.scenario(add_error=errno.EEXIST), (0, b'lo0', 0, ['add']))

    def test_interface_lookup_failure_does_not_attempt_mutation(self):
        self.assertEqual(self.scenario(lookup_error=errno.ENOBUFS), (errno.ENOBUFS, b'', 0, []))


class NetworkStatusTest(unittest.TestCase):
    def test_url_is_exposed_only_after_verified_readback(self):
        replies = iter([(errno.EPERM, '', False), (0, 'lo0', True), (0, 'lo0', False)])
        network = TeslaNetwork(8890, probe=lambda: next(replies))
        self.assertIsNone(network.status['url'])
        self.assertFalse(network.refresh()['ready'])
        self.assertIsNone(network.status['url'])
        self.assertEqual(network.refresh()['url'], 'http://100.99.10.2:8890/')
        self.assertTrue(network.refresh()['ready'])

    def test_only_the_verified_local_alias_is_an_exception_to_private_peers(self):
        network = TeslaNetwork(8890, probe=lambda: (0, 'lo0', False))
        self.assertFalse(allowed_peer('100.99.10.2', network))
        network.refresh()
        for address in ['127.0.0.1', '172.20.10.2', '100.99.10.2']:
            self.assertTrue(allowed_peer(address, network))
        for address in ['100.99.10.1', '100.99.10.3', '100.64.1.5', '8.8.8.8']:
            self.assertFalse(allowed_peer(address, network))

    def test_missing_native_library_reports_failure_without_a_false_url(self):
        def missing():
            raise OSError('network bridge unavailable')
        network = TeslaNetwork(8890, probe=missing)
        self.assertFalse(network.refresh()['ready'])
        self.assertIsNone(network.status['url'])
        self.assertIn('network bridge unavailable', network.status['error'])

if __name__ == '__main__':
    unittest.main()
