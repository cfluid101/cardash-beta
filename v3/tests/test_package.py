import io
import tarfile
from pathlib import Path
import unittest
import plistlib
ROOT=Path(__file__).resolve().parents[2]
class PackageTest(unittest.TestCase):
 def test_rootless_payload_ownership_paths_and_credentials(self):
  path=ROOT/'dist/v3/com.cfluid.cardash.v3_3.0.0~beta.4_iphoneos-arm64.deb';data=path.read_bytes();self.assertEqual(data[:8],b'!<arch>\n');at=8;members={}
  while at<len(data):
   header=data[at:at+60];n=int(header[48:58]);name=header[:16].decode().strip().rstrip('/');members[name]=data[at+60:at+60+n];at+=60+n+(n%2)
  with tarfile.open(fileobj=io.BytesIO(members['data.tar.xz'])) as tar:
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
   self.assertEqual(tar.extractfile('./var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.dylib').read(4),b'\xcf\xfa\xed\xfe')
   for item in tar.getmembers():
    self.assertEqual((item.uid,item.gid),(0,0));self.assertFalse(item.issym() or item.islnk());self.assertNotIn('..',Path(item.name).parts)
    if not item.isfile():continue
    n=item.name.removeprefix('./')
    self.assertTrue(n.startswith(('var/jb/usr/lib/cardash-v3/','var/jb/Applications/CarDashV3.app/')) or n in ('var/jb/usr/libexec/cardash-v3-session','var/jb/usr/libexec/cardash-v3-download','var/jb/usr/libexec/cardash-v3-service','var/jb/Library/LaunchDaemons/com.cfluid.cardash.v3.plist','var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.dylib','var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.plist'),n)
    self.assertFalse(n.endswith(('.pk8','.p7b','.apk')) or n.endswith('/identity.json'),n)
  with tarfile.open(fileobj=io.BytesIO(members['control.tar.xz'])) as tar:
   control=tar.extractfile('./control').read().decode();self.assertIn('Package: com.cfluid.cardash.v3\n',control)
   for name in ('preinst','postinst','prerm','postrm'):
    script=tar.extractfile('./'+name).read().decode();self.assertNotIn('killall',script);self.assertNotIn('com.cfluid.cardash.v2',script);self.assertNotIn('sbreload',script)
if __name__=='__main__':unittest.main()
