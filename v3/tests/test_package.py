import io
import tarfile
from pathlib import Path
import unittest
import plistlib
import re
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
class PackageTest(unittest.TestCase):
 def test_rootless_payload_ownership_paths_and_credentials(self):
  version=re.search(r'^Version: (.+)$',(ROOT/'v3/packaging/control').read_text(),re.M).group(1);path=ROOT/'dist/v3'/('com.cfluid.cardash.v3_'+version+'_iphoneos-arm64.deb');data=path.read_bytes();self.assertEqual(data[:8],b'!<arch>\n');at=8;members={}
  while at<len(data):
   header=data[at:at+60];n=int(header[48:58]);name=header[:16].decode().strip().rstrip('/');members[name]=data[at+60:at+60+n];at+=60+n+(n%2)
  with tarfile.open(fileobj=io.BytesIO(members['data.tar.xz'])) as tar:
   app=plistlib.loads(tar.extractfile('./var/jb/Applications/CarDashV3.app/Info.plist').read())
   self.assertEqual(app['MinimumOSVersion'],'16.0')
   job=plistlib.loads(tar.extractfile('./var/jb/Library/LaunchDaemons/com.cfluid.cardash.v3.plist').read())
   self.assertEqual(job['JetsamProperties']['MemoryLimit'],128)
   self.assertEqual(job['ProcessType'],'Interactive')
   self.assertEqual(job['EnvironmentVariables']['DISABLE_TWEAKS'],'1')
   self.assertNotIn('DYLD_INSERT_LIBRARIES',job['EnvironmentVariables'])
   self.assertEqual(job['ProgramArguments'],['/var/jb/usr/libexec/cardash-v3-service'])
   launcher=tar.getmember('./var/jb/usr/libexec/cardash-v3-service')
   self.assertEqual(launcher.mode,0o755)
   self.assertEqual(tar.extractfile(launcher).read(4),b'\xcf\xfa\xed\xfe')
   injection=plistlib.loads(tar.extractfile('./var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.plist').read())
   self.assertEqual(injection,{'Filter':{'Executables':['mediaserverd']}})
   # The app may run as arm64 on newer phones while mediaserverd requires
   # arm64e injection. Verify the shipped binary, not the DEB architecture label.
   with tempfile.TemporaryDirectory() as tmp:
    adapter=Path(tmp)/'CarDashV3Loopback.dylib'
    adapter.write_bytes(tar.extractfile('./var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.dylib').read())
    architectures=subprocess.check_output(['xcrun','lipo','-archs',str(adapter)],text=True).split()
    self.assertEqual(set(architectures),{'arm64','arm64e'},'Injected adapter must support both system-process architectures')
    subprocess.run(['codesign','--verify','--strict','--all-architectures',str(adapter)],check=True,capture_output=True)
    for architecture in ('arm64','arm64e'):
     thin=Path(tmp)/(architecture+'.dylib')
     subprocess.run(['xcrun','lipo',str(adapter),'-thin',architecture,'-output',str(thin)],check=True,capture_output=True)
     build=subprocess.check_output(['xcrun','vtool','-show-build',str(thin)],text=True)
     self.assertRegex(build,r'platform\s+IOS\b')
     self.assertRegex(build,r'minos\s+16\.0\b','Neither adapter slice may raise the iOS deployment floor')
   for item in tar.getmembers():
    self.assertEqual((item.uid,item.gid),(0,0));self.assertFalse(item.issym() or item.islnk());self.assertNotIn('..',Path(item.name).parts)
    if not item.isfile():continue
    n=item.name.removeprefix('./')
    self.assertTrue(n.startswith(('var/jb/usr/lib/cardash-v3/','var/jb/Applications/CarDashV3.app/')) or n in ('var/jb/usr/libexec/cardash-v3-session','var/jb/usr/libexec/cardash-v3-download','var/jb/usr/libexec/cardash-v3-service','var/jb/Library/LaunchDaemons/com.cfluid.cardash.v3.plist','var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.dylib','var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.plist'),n)
    self.assertFalse(n.endswith(('.pk8','.p7b','.apk')) or n.endswith('/identity.json'),n)
  with tarfile.open(fileobj=io.BytesIO(members['control.tar.xz'])) as tar:
   control=tar.extractfile('./control').read().decode();self.assertIn('Package: com.cfluid.cardash.v3\n',control)
   self.assertNotIn('firmware',re.search(r'^Depends: (.+)$',control,re.M).group(1))
   self.assertIn('Architecture: iphoneos-arm64\n',control)
   preinst=tar.extractfile('./preinst').read().decode()
   self.assertNotIn('sysctl',preinst)
   with tempfile.TemporaryDirectory() as tmp:
    # Exercise the shipped installer in an isolated simulated rootless layout.
    script=preinst.replace('/var/jb',tmp+'/jb')
    rejected=subprocess.run(['/bin/sh','-c',script],capture_output=True,text=True)
    self.assertNotEqual(rejected.returncode,0);self.assertIn('rootless jailbreak',rejected.stderr)
    Path(tmp,'jb').mkdir()
    accepted=subprocess.run(['/bin/sh','-c',script],capture_output=True,text=True)
    self.assertEqual(accepted.returncode,0,accepted.stderr)
   for name in ('preinst','postinst','prerm','postrm'):
    script=tar.extractfile('./'+name).read().decode();self.assertNotIn('killall',script);self.assertNotIn('com.cfluid.cardash.v2',script);self.assertNotIn('sbreload',script)
if __name__=='__main__':unittest.main()
