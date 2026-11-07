import importlib.util
import unittest
import sys
import subprocess
import json
import base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
ROOT=Path(__file__).resolve().parents[2]
class MediaTest(unittest.TestCase):
 def test_muxer_byte_identical_to_device_verified_js(self):
  self.assertIsNotNone(importlib.util.find_spec('media'),'Missing native remuxer port')
  from media import Muxer
  script="""import {AvcMuxer} from './receiver/lib/mp4.mjs';const c=Buffer.from('0164001fffe100046764001f01000268ee','hex'),m=new AvcMuxer(c,1280,720),d=Buffer.from('000000026501','hex');console.log(JSON.stringify([m.initialization().toString('base64'),m.fragment(d,1234567,1267900).toString('base64'),m.fragment(d,1267900,61267900).toString('base64')]));"""
  expected=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],cwd=ROOT,text=True))
  m=Muxer(bytes.fromhex('0164001fffe100046764001f01000268ee'),1280,720);data=bytes.fromhex('000000026501')
  actual=[m.initialization(),m.fragment(data,1234567,1267900),m.fragment(data,1267900,61267900)]
  self.assertEqual(actual,[base64.b64decode(s) for s in expected])
  with self.assertRaises(ValueError):m.fragment(data,1267900,1268000)
if __name__=='__main__':unittest.main()
