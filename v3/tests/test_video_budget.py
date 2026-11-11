import unittest,sys,tempfile,subprocess
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from video_budget import VideoBudget, VideoBudgetLease, budget_status
from test_audio_lease import Notify
class BudgetTest(unittest.TestCase):
 def test_lease_does_not_modify_audio_request_and_clears_on_stop(self):
  lib=Notify();lease=VideoBudgetLease(library=lib,clock=lambda:123,pid=9999);lease.refresh(3000000)
  self.assertEqual(lib.writes[-1],(lib.tokens[b'com.cfluid.cardash.v3.video.request'],(9999<<32)|3000000))
  self.assertNotIn(b'com.cfluid.cardash.v3.audio.request',lib.tokens)
  lease.clear();self.assertEqual(lib.writes[-2:],[(lib.tokens[b'com.cfluid.cardash.v3.video.request'],0),(lib.tokens[b'com.cfluid.cardash.v3.video.lease'],0)])
  for invalid in [0,749999,6000001,3.0]:
   with self.assertRaises(ValueError):lease.refresh(invalid)

 def test_congestion_reduces_source_and_recovery_is_slow(self):
  b=VideoBudget();self.assertEqual(b.bps,3000000)
  for now in [2,4,6,8,10]:b.feedback({'heartbeatRttMs':900,'streamLagMs':2000},now)
  self.assertEqual(b.bps,750000)
  b.feedback({'heartbeatRttMs':25,'streamLagMs':0},12)
  self.assertEqual(b.bps,750000)
  for now in range(14,38,2):b.feedback({'heartbeatRttMs':25,'streamLagMs':0},now)
  self.assertGreater(b.bps,750000);self.assertLess(b.bps,1100000)
 def test_hidden_bad_data_and_duplicate_feedback_cannot_drive_rate(self):
  b=VideoBudget()
  for data in [{},{'heartbeatRttMs':float('nan'),'streamLagMs':0},{'heartbeatRttMs':9999,'streamLagMs':9999,'hidden':True}]:b.feedback(data,2)
  self.assertEqual(b.bps,3000000)
  b.feedback({'heartbeatRttMs':800,'streamLagMs':1000},4);first=b.bps
  b.feedback({'heartbeatRttMs':800,'streamLagMs':1000},4.1);self.assertEqual(b.bps,first)
 def test_unpresented_timeline_is_not_used_as_network_congestion(self):
  b=VideoBudget();b.feedback({'heartbeatRttMs':20,'streamLagMs':99999,'frameReady':False},2)
  self.assertEqual(b.bps,3000000)
  b.feedback({'heartbeatRttMs':900,'streamLagMs':99999,'frameReady':False},4)
  self.assertLess(b.bps,3000000)
 def test_native_only_changes_our_display_and_preserves_other_properties(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'budget';source=Path(__file__).with_name('video_budget_harness.mm')
   subprocess.run(['xcrun','clang++','-std=c++17','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror',str(source),'-framework','Foundation','-o',str(path)],check=True)
   subprocess.run([str(path)],check=True,capture_output=True)

class BudgetStatusTest(unittest.TestCase):
 def status(self,reason,ready=1,pid=1234,again=None):
  values={b'com.cfluid.cardash.v3.video.ready':(pid<<8)|ready,
          b'com.cfluid.cardash.v3.video.state':(pid<<32)|3000000,
          b'com.cfluid.cardash.v3.video.observed':(25000000<<32)|3000000}
  reads=0
  def read(name):
   nonlocal reads
   if name==b'com.cfluid.cardash.v3.video.ready_reason':
    if isinstance(reason,Exception):raise reason
    return reason
   if name==b'com.cfluid.cardash.v3.video.ready':
    reads+=1
    if reads>1 and again is not None:return again
   return values[name]
  with patch('video_budget.notification_state',side_effect=read):return budget_status()
 def test_matching_reason_preserves_original_readiness_and_bitrate_fields(self):
  result=self.status((1234<<32)|(2<<16)|5,ready=2)
  self.assertEqual((result['ready'],result['pid'],result['code']),(False,1234,2))
  self.assertEqual((result['reasonCode'],result['reason']),(5,'entry_prologue_mismatch'))
  self.assertEqual((result['requestedBps'],result['nativeBps'],result['appliedBps']),(3000000,25000000,3000000))
  result=self.status((1234<<32)|(1<<16))
  self.assertTrue(result['ready']);self.assertEqual(result['reasonCode'],0);self.assertEqual(result['reason'],'ready')
 def test_missing_sideband_is_not_a_readiness_fault(self):
  for missing in (0,OSError('optional channel missing'),AttributeError('optional reader missing')):
   with self.subTest(missing=missing):
    result=self.status(missing)
    self.assertTrue(result['ready']);self.assertNotIn('error',result);self.assertNotIn('reasonCode',result)
 def test_stale_or_inconsistent_reason_is_not_attached(self):
  for reason in ((999<<32)|(1<<16),(1234<<32)|(2<<16)|5,(1234<<32)|(1<<16)|5):
   with self.subTest(reason=reason):
    result=self.status(reason)
    self.assertTrue(result['ready']);self.assertNotIn('reasonCode',result);self.assertNotIn('reason',result)
  result=self.status((999<<32)|(2<<16)|5,ready=2)
  self.assertFalse(result['ready']);self.assertNotIn('reasonCode',result)
 def test_readiness_transition_discards_sideband(self):
  result=self.status((1234<<32)|(1<<16),again=(5678<<8)|2)
  self.assertTrue(result['ready']);self.assertEqual(result['pid'],1234);self.assertNotIn('reasonCode',result)

class FeedbackIntegrationTest(unittest.IsolatedAsyncioTestCase):
 async def test_heartbeat_feedback_does_not_wait_for_diagnostic_payload(self):
  from server import Receiver
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.active=True;r.generation='session'
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':900,'streamLagMs':2000,'hidden':False}})
   self.assertLess(r.video_budget.bps,3000000)
