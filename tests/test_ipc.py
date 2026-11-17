import json,os,plistlib,socket,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'build/host/cardash-diagnostics'

class IPCDiagnosticsTests(unittest.TestCase):
    def test_policy_denial_reports_existing_socket_and_sandbox_state(self):
        # Exercise the real connect() under an OS-enforced sandbox, not mocked errno.
        with tempfile.TemporaryDirectory(prefix='cddiag-denied-',dir='/tmp') as folder:
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(folder+'/control.sock');listener.listen(1)
                p=subprocess.run(['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network-outbound)',str(BIN),'--status'],env=dict(os.environ,CD_DIAG_ROOT=folder),capture_output=True,text=True,timeout=5)
            result=json.loads(p.stdout)
            self.assertEqual(p.returncode,1);self.assertEqual(result['errno'],1)
            self.assertEqual(result.get('stage'),'connect')
            self.assertEqual(result.get('errno_name'),'EPERM')
            facts=result['ipc_diagnostics']
            self.assertEqual(facts['euid'],os.geteuid());self.assertEqual(facts['sandbox_active'],1)
            self.assertTrue(facts['socket']['is_socket']);self.assertEqual(facts['socket']['stat_errno'],0)
            self.assertFalse((Path(folder)/'helper.lock').exists())

    def test_missing_socket_is_not_classified_as_policy_denial(self):
        with tempfile.TemporaryDirectory(prefix='cddiag-missing-',dir='/tmp') as folder:
            p=subprocess.run([str(BIN),'--status'],env=dict(os.environ,CD_DIAG_ROOT=folder),capture_output=True,text=True,timeout=5)
            result=json.loads(p.stdout)
            self.assertEqual(result['errno'],2);self.assertEqual(result.get('errno_name'),'ENOENT')
            self.assertEqual(result['ipc_diagnostics']['socket']['stat_errno'],2)
            self.assertNotIn('denied',result['error'].lower())

    def test_signed_device_app_does_not_require_container_confinement(self):
        # Inspect the deployable signature, not the build script's dictionary.
        app=ROOT/'build/device/CarDashDiagnostics.app'
        raw=subprocess.check_output(['/usr/bin/codesign','-d','--entitlements',':-',str(app)],stderr=subprocess.DEVNULL)
        ent=plistlib.loads(raw)
        self.assertIs(ent.get('com.apple.private.security.container-required'),False)
        self.assertIs(ent.get('com.apple.private.security.no-sandbox'),True)
        self.assertEqual(ent['application-identifier'],'com.cfluid.cardash.diagnostics.app')

if __name__=='__main__':unittest.main()
