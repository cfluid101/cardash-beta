import unittest,sys,tempfile,subprocess,json
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

 def test_late_pictures_reduce_source_once_per_event_and_recovery_is_staged(self):
  b=VideoBudget();self.assertEqual(b.bps,3000000)
  # Lag persisting across reports is one congestion event per four seconds,
  # not a 35% cut on every report.
  for now in [2,4,6,8,10]:b.feedback({'heartbeatRttMs':900,'streamLagMs':2000},now)
  self.assertEqual(b.bps,823875)
  for now in range(12,400,4):b.feedback({'heartbeatRttMs':900,'streamLagMs':2000},now)
  self.assertEqual(b.bps,750000)
  # Recovery waits for sustained health, returns quickly toward the rate that
  # worked before the event, then probes slowly.
  b=VideoBudget();b.feedback({'heartbeatRttMs':60,'streamLagMs':2000},2);b.feedback({'heartbeatRttMs':60,'streamLagMs':2000},6)
  self.assertEqual(b.bps,1267500)
  b.feedback({'heartbeatRttMs':25,'streamLagMs':0},8);self.assertEqual(b.bps,1267500)
  for now in range(10,26,2):b.feedback({'heartbeatRttMs':25,'streamLagMs':0},now)
  self.assertGreaterEqual(b.bps,2100000);fast=b.bps
  for now in range(26,36,2):b.feedback({'heartbeatRttMs':25,'streamLagMs':0},now)
  self.assertLessEqual(b.bps,fast+150000)
  for now in range(36,400,2):b.feedback({'heartbeatRttMs':25,'streamLagMs':0},now)
  self.assertEqual(b.bps,3000000)
 def test_slow_heartbeat_alone_is_not_congestion(self):
  # November 2026 owner log: 45 of 51 cuts had an empty send queue.
  b=VideoBudget()
  for now in range(2,60,2):self.assertIsNone(b.feedback({'heartbeatRttMs':4000,'streamLagMs':40},now,queued_bytes=0,measured_bps=900000))
  self.assertEqual(b.bps,3000000)
  # One slow sample never cuts, even with the stream at its budget.
  b=VideoBudget();b.feedback({'heartbeatRttMs':900,'streamLagMs':40},2,measured_bps=2900000);self.assertEqual(b.bps,3000000)
  b.feedback({'heartbeatRttMs':60,'streamLagMs':40},4,measured_bps=2900000)
  b.feedback({'heartbeatRttMs':900,'streamLagMs':40},6,measured_bps=2900000);self.assertEqual(b.bps,3000000)
  # Repeated slow heartbeats while the stream is near its budget cut gently.
  self.assertEqual(b.feedback({'heartbeatRttMs':900,'streamLagMs':40},8,measured_bps=2900000),'slow_link')
  self.assertEqual(b.bps,2550000)
 def test_unsent_video_is_congestion_without_browser_lag(self):
  b=VideoBudget()
  self.assertIsNone(b.feedback({'heartbeatRttMs':40,'streamLagMs':40},2,queued_bytes=100000))
  self.assertEqual(b.feedback({'heartbeatRttMs':40,'streamLagMs':40},4,queued_bytes=200000),'send_backlog')
  self.assertEqual(b.bps,1950000)
  # The floor is never undercut and an unusable count is ignored.
  b.bps=750000;b.cut_at=-100;self.assertIsNone(b.feedback({'heartbeatRttMs':40,'streamLagMs':5000},20));self.assertEqual(b.bps,750000)
  b=VideoBudget();b.feedback({'heartbeatRttMs':40,'streamLagMs':40},2,queued_bytes='many');self.assertEqual(b.bps,3000000)
 def test_hidden_bad_data_and_duplicate_feedback_cannot_drive_rate(self):
  b=VideoBudget()
  for data in [{},{'heartbeatRttMs':float('nan'),'streamLagMs':0},{'heartbeatRttMs':9999,'streamLagMs':9999,'hidden':True}]:b.feedback(data,2)
  self.assertEqual(b.bps,3000000)
  b.feedback({'heartbeatRttMs':800,'streamLagMs':1000},4);first=b.bps
  b.feedback({'heartbeatRttMs':800,'streamLagMs':1000},4.1);self.assertEqual(b.bps,first)
 def test_unpresented_timeline_is_not_used_as_network_congestion(self):
  b=VideoBudget();b.feedback({'heartbeatRttMs':20,'streamLagMs':99999,'frameReady':False},2)
  self.assertEqual(b.bps,3000000)
  # Before a first picture only repeated slow round trips can reduce the rate.
  b.feedback({'heartbeatRttMs':900,'streamLagMs':99999,'frameReady':False},4);self.assertEqual(b.bps,3000000)
  b.feedback({'heartbeatRttMs':900,'streamLagMs':99999,'frameReady':False},6);self.assertEqual(b.bps,2550000)
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
   events=[json.loads(line) for line in (Path(folder)/'diagnostic.ndjson').read_text().splitlines()]
   change=[e for e in events if e['event']=='video_budget']
   self.assertEqual((len(change),change[0]['reason'],change[0]['previous'],change[0]['bps']),(1,'stream_lag',3000000,1950000))
 async def test_heartbeat_reports_unsent_video_to_the_budget(self):
  from server import Receiver
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.active=True;r.generation='session'
   r.viewers={object():{'bytes':500000,'closed':False},object():{'bytes':900000,'closed':True}}
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':40,'streamLagMs':40}})
   self.assertEqual((r.video_budget.bps,r.video_budget.reason),(1950000,'send_backlog'))
