import errno
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ServiceClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='cdipc-', dir='/tmp')
        cls.binary = Path(cls.folder.name) / 'client'
        source = ROOT / 'v3/app/ServiceClient.mm'
        if not source.exists():
            raise AssertionError('Service connection errors have no testable errno-preserving client yet')
        harness = Path(cls.folder.name) / 'client.mm'
        harness.write_text('''#import "ServiceClient.h"
#include <stdio.h>
int main(int argc,char **argv){@autoreleasepool{
 if(argc!=2)return 2;
 NSDictionary *r=CDV3ServiceRequest(@"status",@(argv[1]));
 NSData *d=[NSJSONSerialization dataWithJSONObject:r options:0 error:nil];
 fwrite(d.bytes,1,d.length,stdout);return 0;
}}
''')
        subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fobjc-arc', '-fblocks',
                        '-Wall', '-Wextra', '-Werror', '-I', str(source.parent),
                        str(source), str(harness), '-framework', 'Foundation',
                        '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def request(self, path):
        p = subprocess.run([str(self.binary), str(path)], capture_output=True,
                           text=True, check=True, timeout=5)
        return json.loads(p.stdout)

    def test_missing_socket_preserves_enoent_and_exact_path(self):
        path = str(Path(self.folder.name) / 'missing.sock')
        result = self.request(path)
        self.assertFalse(result['ok'])
        self.assertEqual(result.get('errno'), errno.ENOENT)
        self.assertEqual(result.get('stage'), 'connect')
        self.assertEqual(result.get('socketPath'), path)
        self.assertIn('Export diagnostic report', result['error'])

    def test_stale_socket_is_distinguished_from_missing_path(self):
        path = str(Path(self.folder.name) / 'stale.sock')
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind(path)
        result = self.request(path)
        self.assertEqual(result.get('errno'), errno.ECONNREFUSED)
        self.assertEqual(result.get('stage'), 'connect')

    def test_overlong_path_is_not_silently_truncated(self):
        path = '/tmp/' + 'x' * 120
        result = self.request(path)
        self.assertEqual(result.get('errno'), errno.ENAMETOOLONG)
        self.assertEqual(result.get('stage'), 'address')
        self.assertEqual(result.get('socketPath'), path)

    def reply(self, fragments):
        path = str(Path(self.folder.name) / 'service.sock')
        Path(path).unlink(missing_ok=True)
        received = []
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(path)
            server.listen()
            server.settimeout(4)
            def respond():
                with server.accept()[0] as client:
                    data = b''
                    while not data.endswith(b'\n'):
                        data += client.recv(4096)
                    received.append(json.loads(data))
                    for fragment in fragments:
                        client.sendall(fragment)
            worker = threading.Thread(target=respond)
            worker.start()
            try:
                result = self.request(path)
            finally:
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(received, [{'action': 'status'}])
        return result

    def test_actual_service_reply_survives_fragmentation(self):
        result = self.reply([b'{"ok":true,', b'"active":false}\n'])
        self.assertEqual(result, {'ok': True, 'active': False})

    def test_invalid_response_is_identified_as_protocol_failure(self):
        result = self.reply([b'not-json\n'])
        self.assertFalse(result['ok'])
        self.assertEqual(result.get('stage'), 'response')
        self.assertEqual(result.get('errno'), errno.EPROTO)

    def test_closed_service_connection_produces_exportable_failure(self):
        result = self.reply([])
        self.assertFalse(result['ok'])
        self.assertEqual(result.get('stage'), 'receive')
        self.assertEqual(result.get('errno'), errno.ECONNRESET)


if __name__ == '__main__':
    unittest.main()
