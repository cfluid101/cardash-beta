import json,os,shutil,subprocess,tempfile,time,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class InstallerTests(unittest.TestCase):
    def test_installation_activates_status_only_and_records_helper_reply(self):
        with tempfile.TemporaryDirectory(prefix='cddiag-install-',dir='/tmp') as folder:
            prefix=Path(folder);runtime=prefix/'var/lib/cardash-diagnostics';runtime.mkdir(parents=True,mode=0o750)
            helper=prefix/'usr/libexec/cardash-diagnostics';helper.parent.mkdir(parents=True);shutil.copy2(ROOT/'build/host/cardash-diagnostics',helper)
            # launchd/uicache are device services; only their command boundaries
            # are substituted. The helper socket, parser, and STATUS reply are real.
            for name in ['bin/launchctl','usr/bin/uicache']:
                path=prefix/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o755)
            env=dict(os.environ,CD_DIAG_ROOT=str(runtime));proc=subprocess.Popen([str(helper),'--host-daemon'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    if (runtime/'control.sock').exists():break
                    self.assertIsNone(proc.poll());time.sleep(.01)
                script=(ROOT/'packaging/postinst').read_text()
                if os.environ.get('CD_TEST_INSTALLER_BASELINE'):
                    script=subprocess.check_output(['git','show','d61047e:packaging/postinst'],cwd=ROOT,text=True)
                script=script.replace('/var/jb',str(prefix))
                result=subprocess.run(['/bin/sh','-s','--','configure'],input=script,env=env,capture_output=True,text=True,timeout=7)
                self.assertEqual(result.returncode,0,result.stderr)
                lines=(runtime/'installation.log').read_text().splitlines()
                replies=[json.loads(line) for line in lines if line.startswith('{')]
                self.assertEqual(len(replies),1,'Installer did not record its real STATUS response')
                self.assertIs(replies[0]['running'],False);self.assertEqual(replies[0]['report'],'');self.assertEqual(replies[0]['error'],'')
                self.assertEqual(list(runtime.glob('report-*.log')),[],'Installation started a diagnostic run')
            finally:
                proc.terminate();proc.communicate(timeout=6)

if __name__=='__main__':unittest.main()
