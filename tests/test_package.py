import hashlib,io,json,plistlib,subprocess,tarfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.deb=ROOT/'dist/com.cfluid.cardash.diagnostics_0.1.1_iphoneos-arm64.deb'
        self.assertTrue(self.deb.is_file(),'Diagnostic DEB is not built')
    def archive(self,name):
        raw=subprocess.check_output(['/usr/bin/ar','-p',str(self.deb),name]);return tarfile.open(fileobj=io.BytesIO(raw),mode='r:xz')
    def test_rootless_payload_has_no_product_or_injection_paths(self):
        with self.archive('data.tar.xz') as tar:
            paths={m.name.removeprefix('./'):m for m in tar.getmembers()};self.assertIn('var/jb/usr/libexec/cardash-diagnostics',paths)
            for path,m in paths.items():
                self.assertNotIn('..',Path(path).parts);self.assertFalse(path.startswith('/'));self.assertEqual(m.uid,0);self.assertEqual(m.gid,0);self.assertFalse(m.issym() or m.islnk())
                if m.isfile():self.assertTrue(any(path.startswith(p) for p in ['var/jb/Applications/CarDashDiagnostics.app/','var/jb/usr/libexec/cardash-diagnostics','var/jb/Library/LaunchDaemons/com.cfluid.cardash.diagnostics.plist','var/jb/usr/share/cardash-diagnostics/']),path)
            job=plistlib.loads(tar.extractfile(paths['var/jb/Library/LaunchDaemons/com.cfluid.cardash.diagnostics.plist']).read())
            self.assertFalse(job['RunAtLoad']);self.assertFalse(job['KeepAlive']);self.assertEqual(job['ProgramArguments'],['/var/jb/usr/libexec/cardash-diagnostics','--daemon'])
            socket=job['Sockets']['ControlListeners'];self.assertEqual(socket['SockPathMode'],0o660);self.assertEqual(socket['SockPathGroup'],501)
            self.assertEqual(socket['SockPathName'],'/var/jb/var/lib/cardash-diagnostics/control.sock')
    def test_payload_matches_manifest_and_signed_native_targets(self):
        with self.archive('data.tar.xz') as tar:
            names={m.name.removeprefix('./'):m for m in tar.getmembers()};manifest=json.loads(tar.extractfile(names['var/jb/usr/share/cardash-diagnostics/manifest.json']).read())
            for path,sha in manifest['sha256'].items():self.assertEqual(hashlib.sha256(tar.extractfile(names[path]).read()).hexdigest(),sha)
        for path in [ROOT/'build/device/cardash-diagnostics',ROOT/'build/device/CarDashDiagnostics.app']:
            subprocess.run(['/usr/bin/codesign','--verify','--strict',str(path)],check=True,capture_output=True)
        self.assertNotIn(b'CD_TEST_WORKER_MODE',(ROOT/'build/device/cardash-diagnostics').read_bytes())
        self.assertNotIn(b'CD_SIM_AUTORUN',(ROOT/'build/device/CarDashDiagnostics.app/CarDashDiagnostics').read_bytes())
        info=plistlib.loads((ROOT/'build/device/CarDashDiagnostics.app/Info.plist').read_bytes());self.assertEqual(info['MinimumOSVersion'],'16.6');self.assertEqual(info['CFBundleIdentifier'],'com.cfluid.cardash.diagnostics.app')
    def test_control_scripts_are_valid_shell_and_package_is_separate(self):
        with self.archive('control.tar.xz') as tar:
            names={m.name.removeprefix('./'):m for m in tar.getmembers()};control=tar.extractfile(names['control']).read().decode();self.assertIn('Package: com.cfluid.cardash.diagnostics\n',control)
            for name in ['postinst','prerm','postrm']:
                data=tar.extractfile(names[name]).read();subprocess.run(['/bin/sh','-n'],input=data,check=True,capture_output=True)
                self.assertEqual(names[name].mode,0o755)

if __name__=='__main__':unittest.main()
