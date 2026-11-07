import ctypes
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import memory_budget

class BudgetTest(unittest.TestCase):
 def run_budget(self,mismatch=False,failure=False,machine='iPhone10,2'):
  calls=[]
  def api(command,pid,flags,buffer,size):
   values=ctypes.cast(buffer,ctypes.POINTER(ctypes.c_int32*4)).contents
   calls.append((command,pid,flags,size,list(values)))
   if failure:return -1
   if command==8:
    for i,v in enumerate([6 if mismatch else 128,1,128,1]):values[i]=v
   return 0
  with patch.object(memory_budget.sys,'platform','darwin'),patch.object(memory_budget.os,'uname',return_value=types.SimpleNamespace(machine=machine)),patch.object(memory_budget.os,'getuid',return_value=0),patch.object(memory_budget.os,'getpid',return_value=4321),patch.object(memory_budget.ctypes,'CDLL',return_value=types.SimpleNamespace(memorystatus_control=api)):
   result=memory_budget.configure()
  return result,calls
 def test_sets_only_self_and_verifies_effective_budget(self):
  result,calls=self.run_budget();self.assertTrue(result['verified'])
  self.assertEqual([c[:4] for c in calls],[(7,4321,0,16),(8,4321,0,16)])
  self.assertEqual(calls[0][4],[128,1,128,1])
 def test_ignored_policy_prevents_service_start(self):
  with self.assertRaisesRegex(RuntimeError,'did not take effect'):self.run_budget(mismatch=True)
 def test_kernel_rejection_prevents_service_start(self):
  with self.assertRaises(OSError):self.run_budget(failure=True)
 def test_other_models_can_attempt_the_same_verified_self_budget(self):
  for machine in ('iPhone10,5','iPhone14,2','iPad13,1'):
   with self.subTest(machine=machine):
    result,calls=self.run_budget(machine=machine)
    self.assertTrue(result['verified']);self.assertEqual([c[1] for c in calls],[4321,4321])
 def test_non_darwin_and_non_root_cannot_call_kernel_policy(self):
  for platform,uid,error in (('linux',0,'Darwin'),('darwin',501,'root')):
   with self.subTest(platform=platform,uid=uid),patch.object(memory_budget.sys,'platform',platform),patch.object(memory_budget.os,'getuid',return_value=uid),patch.object(memory_budget.ctypes,'CDLL') as loader:
    with self.assertRaisesRegex(RuntimeError,error):memory_budget.configure()
    loader.assert_not_called()

if __name__=='__main__':unittest.main()
