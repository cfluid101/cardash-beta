import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from provision import provision
class ProvisionTest(unittest.TestCase):
 def test_bad_download_cannot_create_identity(self):
  with tempfile.TemporaryDirectory() as root:
   with self.assertRaisesRegex(ValueError,"checksum mismatch"):provision(root,b"not the pinned APK")
   self.assertFalse((Path(root)/"accessory").exists())
