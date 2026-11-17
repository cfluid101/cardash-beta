from pathlib import Path
import errno
import json
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ServiceDiagnosticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.build.name) / 'service-diagnostics-test'
        subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fobjc-arc',
                        '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'v3/tests/service_diagnostics_harness.mm'),
                        str(ROOT / 'v3/app/ServiceDiagnostics.mm'),
                        '-framework', 'Foundation', '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def report(self, folder, reply=None, context=None):
        value = {'reply': reply or {'ok': False, 'error': 'Service unavailable',
                                   'errno': 2, 'errnoName': 'ENOENT', 'stage': 'connect',
                                   'socketPath': '/var/jb/var/lib/cardash-v3/control.sock'},
                 'context': context or {}}
        result = subprocess.run([str(self.binary), str(folder)], input=json.dumps(value),
                                capture_output=True, text=True, check=True, timeout=5)
        self.assertTrue(result.stdout.strip(), 'Service failure must still produce an export')
        self.assertLess(len(result.stdout.encode()), 5 * 1024 * 1024)
        try:
            rows = [json.loads(line) for line in result.stdout.splitlines()]
        except json.JSONDecodeError as error:
            self.fail('Export must contain only complete NDJSON records: ' + str(error))
        self.assertEqual(rows[0].get('event'), 'app_export', 'Every report needs its service/context header')
        return rows, result.stdout

    def test_missing_service_and_logs_still_export_failure_context(self):
        with tempfile.TemporaryDirectory() as folder:
            rows, text = self.report(folder, context={'machine': 'iPhone12,1',
                'build': '20G81', 'packageVersion': 'test', 'token': 'hidden-secret',
                'pathChecks': [{'path': '/var/jb/usr/bin/python3', 'exists': False,
                                'errno': 2, 'token': 'hidden-path-secret'}]})
            self.assertEqual(rows[0]['event'], 'app_export')
            self.assertEqual(rows[0]['report_scope'], 'offline_service_diagnostics')
            self.assertEqual(rows[0]['serviceError']['errno'], 2)
            self.assertEqual(rows[0]['context']['machine'], 'iPhone12,1')
            self.assertEqual(rows[0]['context']['pathChecks'][0]['errno'], 2)
            errors = {r['file']: r for r in rows if r['event'] == 'supporting_log_error'}
            self.assertEqual(set(errors), {'installation.log', 'service-bootstrap.log'})
            self.assertTrue(all(r['errno'] == errno.ENOENT for r in errors.values()))
            self.assertNotIn('hidden-secret', text)
            self.assertNotIn('hidden-path-secret', text)

    def test_log_tails_are_bounded_and_other_state_files_are_never_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'installation.log').write_text('OLD-BEGIN\n' + 'x' * 80000 + '\nLAST-LINE\n')
            (root / 'service-bootstrap.log').write_text('Traceback:\nModuleNotFoundError: missing\n')
            (root / 'identity.json').write_text('private-identity-secret')
            (root / 'accessory').mkdir()
            (root / 'accessory/identity.pk8').write_text('private-key-secret')
            rows, text = self.report(root)
            logs = {r['file']: r for r in rows if r['event'] == 'supporting_log'}
            self.assertEqual(set(logs), {'installation.log', 'service-bootstrap.log'})
            self.assertTrue(logs['installation.log']['truncated'])
            self.assertLessEqual(logs['installation.log']['bytesRead'], 65536)
            self.assertTrue(logs['installation.log']['text'].endswith('LAST-LINE\n'))
            self.assertNotIn('OLD-BEGIN', text)
            self.assertNotIn('private-identity-secret', text)
            self.assertNotIn('private-key-secret', text)
            self.assertIn('ModuleNotFoundError', logs['service-bootstrap.log']['text'])

    def test_symlink_and_fifo_logs_are_rejected_without_reading_or_blocking(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'private').write_text('symlink-target-secret')
            (root / 'installation.log').symlink_to(root / 'private')
            os.mkfifo(root / 'service-bootstrap.log')
            rows, text = self.report(root)
            errors = {r['file']: r for r in rows if r['event'] == 'supporting_log_error'}
            self.assertEqual(set(errors), {'installation.log', 'service-bootstrap.log'})
            self.assertEqual(errors['service-bootstrap.log']['reason'], 'not_regular')
            self.assertNotIn('symlink-target-secret', text)

    def test_missing_or_symlink_state_directory_still_yields_an_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'real').mkdir()
            (root / 'real/installation.log').write_text('outside-directory-secret')
            (root / 'link').symlink_to(root / 'real')
            for state in (root / 'missing', root / 'link'):
                with self.subTest(state=state):
                    rows, text = self.report(state)
                    self.assertEqual(rows[0]['report_scope'], 'offline_service_diagnostics')
                    self.assertEqual(sum(r['event'] == 'supporting_log_error' for r in rows), 2)
                    self.assertNotIn('outside-directory-secret', text)

    @unittest.skipIf(os.getuid() == 0, 'Host permission test needs an unprivileged process')
    def test_unreadable_log_reports_permission_error(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'installation.log'
            log.write_text('permission-secret')
            log.chmod(0)
            try:
                rows, text = self.report(folder)
            finally:
                log.chmod(0o600)
            error = next(r for r in rows if r.get('file') == 'installation.log')
            self.assertEqual(error['event'], 'supporting_log_error')
            self.assertEqual(error['errno'], errno.EACCES)
            self.assertNotIn('permission-secret', text)

    def test_live_report_preserves_events_and_sanitizes_status(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'installation.log').write_text('fallback-should-not-be-read')
            reply = {'ok': True, 'report': '{"event":"listening","port":8890}\n',
                     'status': {'version': 'candidate', 'active': False, 'session': 'session-secret',
                                'token': 'bearer-secret', 'identityReady': True,
                                'transport': {'ready': False, 'error': 'adapter unavailable', 'pid':123,'code':2,
                                              'privateKey': 'nested-secret'}}}
            rows, text = self.report(folder, reply=reply)
            self.assertEqual(rows[0]['report_scope'], 'service_report')
            self.assertEqual(rows[0]['status']['transport']['ready'], False)
            self.assertEqual(rows[0]['status']['transport']['code'],2)
            self.assertEqual(rows[0]['status']['transport']['pid'],123)
            self.assertEqual(rows[1], {'event': 'listening', 'port': 8890})
            for secret in ('session-secret', 'bearer-secret', 'nested-secret', 'fallback-should-not-be-read'):
                self.assertNotIn(secret, text)

    def test_large_live_report_and_partial_lines_remain_bounded_valid_ndjson(self):
        with tempfile.TemporaryDirectory() as folder:
            body = '{"event":"old-head"}\n' + ('{"event":"sample","value":"' + 'x' * 100 + '"}\n') * 20000
            body += '{"event":"last-complete"}\n{"partial":'
            rows, text = self.report(folder, reply={'ok': True, 'report': body})
            self.assertEqual(rows[0]['report_scope'], 'service_report')
            self.assertNotIn('old-head', text)
            self.assertTrue(any(r.get('event') == 'last-complete' for r in rows))
            self.assertTrue(any(r.get('event') == 'report_read_warning' for r in rows))

    def test_live_export_retains_adapter_reasons_on_success_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            for ready, reason_code, reason in ((True, 0, 'ready'), (False, 5, 'entry_prologue_mismatch')):
                with self.subTest(ready=ready):
                    adapter = {'ready': ready, 'pid': 1234, 'code': 1 if ready else 2,
                               'reasonCode': reason_code, 'reason': reason,
                               'privateKey': 'never-export-this-secret'}
                    reply = {'ok': True, 'report': '{"event":"native_inspection"}\n',
                             'status': {'active': ready, 'nativeFrames': 100 if ready else 0,
                                        'transport': adapter, 'videoBudget': adapter}}
                    rows, text = self.report(folder, reply=reply)
                    for name in ('transport', 'videoBudget'):
                        exported = rows[0]['status'][name]
                        self.assertEqual(exported['ready'], ready)
                        self.assertEqual(exported['reasonCode'], reason_code)
                        self.assertEqual(exported['reason'], reason)
                    self.assertNotIn('never-export-this-secret', text)

    def test_non_utf8_log_bytes_still_produce_parseable_report(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'installation.log').write_bytes(b'loader error: \xff\xfe\n')
            rows, _ = self.report(folder)
            log = next(r for r in rows if r.get('file') == 'installation.log')
            self.assertEqual(log['event'], 'supporting_log')
            self.assertIn('loader error:', log['text'])


if __name__ == '__main__':
    unittest.main()
