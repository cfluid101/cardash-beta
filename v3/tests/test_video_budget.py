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

 def test_late_pictures_reduce_source_once_per_event(self):
  b=VideoBudget();self.assertEqual(b.bps,3000000)
  # Lag persisting across reports is one congestion event per four seconds.
  for now in [2,4,6,8,10]:b.feedback({'heartbeatRttMs':900,'streamLagMs':2000},now)
  self.assertEqual(b.bps,1536000)
  for now in range(12,400,4):b.feedback({'heartbeatRttMs':900,'streamLagMs':2000},now)
  self.assertEqual(b.bps,750000)
 def test_cut_starts_from_what_is_actually_sent(self):
  # November 15: 2.44 Mbps budget, 1.59 Mbps stream, 402 KB waiting. Beta 6
  # cut the budget to 1.59 Mbps, which changed nothing.
  b=VideoBudget();b.bps=2443200
  self.assertEqual(b.feedback({'heartbeatRttMs':387,'streamLagMs':100},10,queued_bytes=402362,measured_bps=1592107),'send_backlog')
  self.assertEqual((b.bps,b.limit),(1273685,1592107))
  # A stream at its budget is cut from the budget; a rate below the floor is not a base.
  b=VideoBudget();b.feedback({'heartbeatRttMs':40,'streamLagMs':900},2,measured_bps=3100000);self.assertEqual(b.bps,2400000)
  b=VideoBudget();b.feedback({'heartbeatRttMs':40,'streamLagMs':900},2,measured_bps=400000);self.assertEqual(b.bps,2400000)
 def test_congested_rate_is_held_before_it_is_approached_again(self):
  b=VideoBudget();healthy={'heartbeatRttMs':40,'streamLagMs':40}
  b.feedback({'heartbeatRttMs':40,'streamLagMs':900},2,measured_bps=1600000)
  self.assertEqual((b.bps,b.limit,b.hold),(1280000,1600000,120))
  for now in range(4,120,2):b.feedback(healthy,now,measured_bps=1200000)
  # Recovery stops under the rate that congested and stays there for the hold.
  self.assertEqual(b.bps,1440000)
  for now in range(120,150,2):b.feedback(healthy,now,measured_bps=1400000)
  self.assertGreater(b.bps,1440000);self.assertLessEqual(b.bps,1440000+3*150000)
  # The probe fails soon after release: the next hold is twice as long.
  self.assertEqual(b.feedback({'heartbeatRttMs':40,'streamLagMs':900},150,measured_bps=1650000),'stream_lag')
  self.assertEqual(b.hold,240)
  for now in range(152,152+238,2):b.feedback(healthy,now,measured_bps=1300000)
  self.assertEqual(b.bps,int(1650000*.9))
  # A probe that survives ninety seconds restores the ordinary hold.
  b.released_at=1000
  b.cut_at=-100;b.feedback({'heartbeatRttMs':40,'streamLagMs':900},1200,measured_bps=2000000);self.assertEqual(b.hold,120)
  # A clean link is never held below the ceiling.
  b=VideoBudget()
  for now in range(2,400,2):b.feedback(healthy,now,measured_bps=1400000)
  self.assertEqual(b.bps,3000000)
 def test_pause_or_join_is_not_mistaken_for_late_pictures(self):
  # 02:24:06 on November 15: 1.7 s "lag" two seconds after joining, stream at 277 bps.
  b=VideoBudget();self.assertIsNone(b.feedback({'heartbeatRttMs':51,'streamLagMs':1667},2,measured_bps=277));self.assertEqual(b.bps,3000000)
  b=VideoBudget();self.assertIsNone(b.feedback({'heartbeatRttMs':118,'streamLagMs':2000},2,queued_bytes=8291,measured_bps=521986,settling=True));self.assertEqual(b.bps,3000000)
  # The same report from a settled, flowing stream is congestion.
  self.assertEqual(b.feedback({'heartbeatRttMs':118,'streamLagMs':2000},4,measured_bps=521986),'stream_lag')
  # Unsent video counts even while settling, and so does a deep queue of small frames.
  b=VideoBudget();self.assertEqual(b.feedback({'heartbeatRttMs':40,'streamLagMs':40},2,queued_bytes=250000,settling=True),'send_backlog')
  b=VideoBudget();self.assertIsNone(b.feedback({'heartbeatRttMs':40,'streamLagMs':40},2,queued_bytes=30000,queued_fragments=19))
  self.assertEqual(b.feedback({'heartbeatRttMs':40,'streamLagMs':40},4,queued_bytes=30000,queued_fragments=20),'send_backlog')
 def test_slow_heartbeat_alone_is_not_congestion(self):
  # First owner log: 45 of 51 cuts had an empty send queue.
  b=VideoBudget()
  for now in range(2,60,2):self.assertIsNone(b.feedback({'heartbeatRttMs':4000,'streamLagMs':40},now,queued_bytes=0,measured_bps=900000))
  self.assertEqual(b.bps,3000000)
  # One slow sample never cuts, even with the stream at its budget.
  b=VideoBudget();b.feedback({'heartbeatRttMs':900,'streamLagMs':40},2,measured_bps=2900000);self.assertEqual(b.bps,3000000)
  b.feedback({'heartbeatRttMs':60,'streamLagMs':40},4,measured_bps=2900000)
  b.feedback({'heartbeatRttMs':900,'streamLagMs':40},6,measured_bps=2900000);self.assertEqual(b.bps,3000000)
  # Repeated slow heartbeats while the stream is near its budget cut gently.
  self.assertEqual(b.feedback({'heartbeatRttMs':900,'streamLagMs':40},8,measured_bps=2900000),'slow_link')
  self.assertEqual(b.bps,2610000)
 def test_floor_and_unusable_counts(self):
  b=VideoBudget();b.bps=750000;self.assertIsNone(b.feedback({'heartbeatRttMs':40,'streamLagMs':5000},20));self.assertEqual(b.bps,750000)
  b=VideoBudget();b.feedback({'heartbeatRttMs':40,'streamLagMs':40},2,queued_bytes='many',queued_fragments=None,measured_bps=float('nan'));self.assertEqual(b.bps,3000000)
  b=VideoBudget();b.feedback({'heartbeatRttMs':40,'streamLagMs':900},2,measured_bps=float('inf'));self.assertEqual(b.bps,2400000)
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
  b.feedback({'heartbeatRttMs':900,'streamLagMs':99999,'frameReady':False},6);self.assertEqual(b.bps,2700000)
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
   r.viewers={object():{'bytes':0,'closed':False}}
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':900,'streamLagMs':2000,'hidden':False}})
   self.assertLess(r.video_budget.bps,3000000)
   events=[json.loads(line) for line in (Path(folder)/'diagnostic.ndjson').read_text().splitlines()]
   change=[e for e in events if e['event']=='video_budget']
   self.assertEqual((len(change),change[0]['reason'],change[0]['previous'],change[0]['bps']),(1,'stream_lag',3000000,2400000))
   self.assertEqual((change[0]['limitBps'],change[0]['holdSeconds']),(3000000,120))
 async def test_heartbeat_reports_unsent_video_to_the_budget(self):
  from server import Receiver
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.active=True;r.generation='session'
   r.viewers={object():{'bytes':500000,'closed':False},object():{'bytes':900000,'closed':True}}
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':40,'streamLagMs':40}})
   self.assertEqual((r.video_budget.bps,r.video_budget.reason),(2400000,'send_backlog'))
 async def test_heartbeat_reports_queue_depth_and_a_settling_viewer(self):
  import asyncio,time
  from server import Receiver
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as folder:
   r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.active=True;r.generation='session'
   q=asyncio.Queue(maxsize=60)
   for _ in range(25):q.put_nowait(b'x')
   r.viewers={q:{'bytes':25,'closed':False,'joined':time.monotonic()-60,'awaiting_key':None}}
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':40,'streamLagMs':40}})
   self.assertEqual(r.video_budget.reason,'send_backlog')
   # A viewer that joined a moment ago reports the pause before its keyframe as lag.
   r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.active=True;r.generation='session'
   r.viewers={asyncio.Queue():{'bytes':0,'closed':False,'joined':time.monotonic()-2,'awaiting_key':None}}
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':40,'streamLagMs':2000}})
   self.assertEqual(r.video_budget.bps,3000000)
   next(iter(r.viewers.values()))['joined']-=60;r.video_budget.last=-100
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':40,'streamLagMs':2000}})
   self.assertEqual(r.video_budget.reason,'stream_lag')
   # Back from suspension: three minutes of "lag" reported before the stream is reattached.
   r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'));r.active=True;r.generation='session';r.had_viewer=True;r.frames=5000
   await r.action({'action':'heartbeat','session':'session','link':{'heartbeatRttMs':40,'streamLagMs':180000}})
   self.assertEqual(r.video_budget.bps,3000000)
