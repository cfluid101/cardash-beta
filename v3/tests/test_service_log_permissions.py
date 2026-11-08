from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class ServiceLogPermissionsTest(unittest.TestCase):
    def test_install_preserves_logs_and_makes_only_startup_logs_group_readable(self):
        with tempfile.TemporaryDirectory(prefix='cd-install-') as folder:
            jb=Path(folder)/'jb';state=jb/'var/lib/cardash-v3';state.mkdir(parents=True)
            bootstrap=state/'service-bootstrap.log';bootstrap.write_text('EARLIER STARTUP ERROR\n');bootstrap.chmod(0o600)
            install=state/'installation.log';install.write_text('EARLIER INSTALL\n');install.chmod(0o600)
            identity=state/'identity.json';identity.write_text('PRIVATE');identity.chmod(0o600)
            commands=jb/'usr/bin';commands.mkdir(parents=True)
            # These commands affect launchd/system ownership only on a phone.
            # Keep real chmod/touch/mkdir and verify their filesystem effects.
            for name in ('launchctl','uicache','chown'):
                stub=commands/name;stub.write_text('#!/bin/sh\nexit 0\n');stub.chmod(0o755)
            script=(ROOT/'v3/packaging/postinst').read_text().replace('/var/jb',str(jb))
            result=subprocess.run(['/bin/sh','-c',script],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(stat.S_IMODE(bootstrap.stat().st_mode),0o640)
            self.assertEqual(stat.S_IMODE(install.stat().st_mode),0o640)
            self.assertTrue(bootstrap.read_text().startswith('EARLIER STARTUP ERROR\n'))
            self.assertTrue(install.read_text().startswith('EARLIER INSTALL\n'))
            self.assertEqual(identity.read_text(),'PRIVATE')
            self.assertEqual(stat.S_IMODE(identity.stat().st_mode),0o600)

if __name__=='__main__':unittest.main()
