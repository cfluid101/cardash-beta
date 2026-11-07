import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from transport import AudioLease,audio_route_status,MachClock

class Notify:
 def __init__(self):self.tokens={};self.writes=[];self.fail=False
 def notify_register_check(self,name,out):
  token=len(self.tokens)+1;self.tokens[name]=token;out._obj.value=token;return 0
 def notify_set_state(self,token,value):
  self.writes.append((token,value.value));return 1 if self.fail else 0

class AudioLeaseTest(unittest.TestCase):
 def test_native_clock_uses_absolute_ticks_without_python_process_origin(self):
  class Mach:
   class Ticks:
    def __call__(self):return 90_000_000_000
   mach_absolute_time=Ticks()
   def mach_timebase_info(self,out):out._obj[0]=125;out._obj[1]=3;return 0
  self.assertEqual(MachClock(Mach())(),3750)

 def test_lease_is_opt_in_refreshed_and_cleared_without_pid_truncation(self):
  lib=Notify();clock=[12.5];lease=AudioLease(library=lib,clock=lambda:clock[0],pid=123456)
  lease.clear();self.assertEqual(lib.writes,[])
  lease.refresh(True)
  self.assertIn((lib.tokens[b'com.cfluid.cardash.v3.audio.request'],(123456<<8)|1),lib.writes)
  self.assertIn((lib.tokens[b'com.cfluid.cardash.v3.audio.lease'],12500),lib.writes)
  clock[0]=14.5;lease.refresh(True)
  self.assertIn((lib.tokens[b'com.cfluid.cardash.v3.audio.lease'],14500),lib.writes)
  lease.clear();self.assertEqual(lib.writes[-2:],[(lib.tokens[b'com.cfluid.cardash.v3.audio.request'],0),(lib.tokens[b'com.cfluid.cardash.v3.audio.lease'],0)])
 def test_route_status_reports_applied_device_policy_only_from_current_adapter(self):
  state=(123<<16)|15
  result=audio_route_status(probe=lambda:256*123+1,alive=lambda pid:None,state_probe=lambda:state)
  self.assertTrue(result['deviceOutputActive']);self.assertTrue(result['leaseValid'])
  result=audio_route_status(probe=lambda:256*123+1,alive=lambda pid:None,state_probe=lambda:(124<<16)|15)
  self.assertFalse(result['deviceOutputActive'])
 def test_failed_write_and_missing_adapter_are_explicit(self):
  lib=Notify();lease=AudioLease(library=lib,clock=lambda:12);lib.fail=True
  with self.assertRaises(OSError):lease.refresh(True)
  self.assertFalse(audio_route_status(probe=lambda:0)['ready'])
  self.assertTrue(audio_route_status(probe=lambda:256*123+1,alive=lambda pid:None)['ready'])

if __name__=='__main__':unittest.main()
