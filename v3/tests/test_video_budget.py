import unittest,sys,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from video_budget import VideoBudget, VideoBudgetLease
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

class FeedbackIntegrationTest(unittest.IsolatedAsyncioTestCase):
 async def test_heartbeat_feedback_does_not_wait_for_diagnostic_payload(self):
  from server import Receiver
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.active=True;r.generation='session'
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':900,'streamLagMs':2000,'hidden':False}})
   self.assertLess(r.video_budget.bps,3000000)
