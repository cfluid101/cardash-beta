from pathlib import Path
import json
import errno
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class ServiceEnvironmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='cdenv-', dir='/tmp')
        cls.binary = Path(cls.folder.name) / 'environment'
        source = ROOT / 'v3/app/ServiceEnvironment.mm'
        if not source.exists():
            raise AssertionError('No service-independent path metadata collector')
        harness = Path(cls.folder.name) / 'harness.mm'
        harness.write_text('''#import "ServiceEnvironment.h"
#include <stdio.h>
int main(int argc,char **argv){@autoreleasepool{
 if(argc!=2)return 2;
 NSData *d=[NSJSONSerialization dataWithJSONObject:CDV3DiagnosticContexts(@(argv[1]),@"test-version") options:0 error:nil];
 fwrite(d.bytes,1,d.length,stdout);return 0;
}}
''')
        subprocess.run(['xcrun','clang++','-std=c++17','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-I',str(source.parent),str(source),str(harness),'-framework','Foundation','-o',str(cls.binary)],check=True)
    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()
    def context(self, executable):
        return json.loads(subprocess.check_output([str(self.binary),str(executable)],text=True,timeout=5))
    def test_legacy_context_survives_missing_roothide_link(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            result = self.context(Path(folder)/'CarDashV3')
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['socketPath'],'/var/jb/var/lib/cardash-v3/control.sock')
            self.assertEqual(result[0]['rootSource'],'configured-rootless')
            self.assertEqual(result[0]['packageVersion'],'test-version')
            self.assertTrue(result[0]['pathChecks'])
            paths=[entry['path'] for entry in result[0]['pathChecks']]
            for relative in ('Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.dylib',
                             'Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.plist',
                             'usr/lib/libsubstrate.dylib','usr/libexec/cardash-v3-session'):
                self.assertIn('/var/jb/'+relative, paths)
    def test_documented_executable_link_adds_read_only_candidate(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            base=Path(folder);app=base/'app';app.mkdir();root=base/'hidden-root';root.mkdir()
            (app/'.jbroot').symlink_to(root,target_is_directory=True)
            python=root/'usr/bin/python3';python.parent.mkdir(parents=True);python.write_bytes(b'NOT AN EXECUTABLE');python.chmod(0o700)
            before=sorted(str(p.relative_to(base)) for p in base.rglob('*'))
            result=self.context(app/'CarDashV3')
            self.assertEqual(len(result),2)
            candidate=result[1]
            self.assertEqual(candidate['rootSource'],'executable-jbroot-link')
            self.assertEqual(Path(candidate['rootPath']).resolve(),root.resolve())
            self.assertEqual(Path(candidate['stateDirectory']).resolve(),(root/'var/lib/cardash-v3').resolve())
            checks=candidate['pathChecks'];entry=next(x for x in checks if x['path'].endswith('/usr/bin/python3'))
            self.assertTrue(entry['exists']);self.assertEqual(entry['type'],'file')
            self.assertNotIn('NOT AN EXECUTABLE',json.dumps(result))
            self.assertEqual(before,sorted(str(p.relative_to(base)) for p in base.rglob('*')))
    def test_broken_link_or_regular_dot_jbroot_is_not_adopted(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            base=Path(folder);link=base/'.jbroot';link.symlink_to(base/'missing')
            self.assertEqual(len(self.context(base/'CarDashV3')),1)
            link.unlink();link.write_text('not a root directory')
            self.assertEqual(len(self.context(base/'CarDashV3')),1)
    def test_report_does_not_follow_unrelated_root_candidates(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            base=Path(folder);(base/'.jbroot-anything').mkdir()
            self.assertEqual(len(self.context(base/'CarDashV3')),1)

    @unittest.skipIf(os.geteuid()==0,'Permission denial needs an unprivileged host')
    def test_inaccessible_root_is_not_reported_as_missing_files(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            base=Path(folder);app=base/'app';app.mkdir();root=base/'hidden-root';root.mkdir()
            (app/'.jbroot').symlink_to(root,target_is_directory=True)
            root.chmod(0)
            try:
                contexts=self.context(app/'CarDashV3')
                denied=next(p for p in contexts[1]['pathChecks'] if p['path'].endswith('/usr/bin/python3'))
                self.assertEqual(denied['errno'],errno.EACCES)
                self.assertEqual(denied['type'],'unavailable')
            finally:
                root.chmod(0o700)

if __name__=='__main__':unittest.main()
