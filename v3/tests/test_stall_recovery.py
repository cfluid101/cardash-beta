# SPDX-License-Identifier: GPL-3.0-only
"""Beta 6/7: survive link blips, service stalls and a suspended browser without ending native CarPlay."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import server
from server import DISPLAY, Receiver

KEYFRAME={'type':'forceKeyFrame','params':{'uuid':DISPLAY}}


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/unused'))
        r=self.r;r.active=True;r.generation='current';r.frames=100;r.had_viewer=True
        r.audio_lease=Mock();r.video_lease=Mock();r.command=AsyncMock();r.stop=AsyncMock()

    async def asyncTearDown(self):self.tmp.cleanup()

    def events(self,name):
        path=Path(self.tmp.name)/'diagnostic.ndjson'
        return [e for e in map(json.loads,path.read_text().splitlines()) if e['event']==name]

    async def tick(self,now,heartbeat_age,pulse_age=1):
        r=self.r;r.started=now-300;r.last_heartbeat=now-heartbeat_age;r.pulse_at=now-pulse_age
        with patch('server.time.monotonic',return_value=now),patch('server.asyncio.sleep',side_effect=[None,asyncio.CancelledError()]):
            with self.assertRaises(asyncio.CancelledError):await r.ticker()


class WatchdogTest(Base):
    async def test_brief_browser_silence_keeps_the_native_session(self):
        # Beta 5 ended the session at 12 seconds and beta 6 at 90. A shrunk Tesla
        # browser is suspended for minutes: both November 15 "disconnects".
        for age in (13,91,595,899):
            await self.tick(2000,age);self.r.stop.assert_not_awaited()
        self.assertEqual(server.BROWSER_GRACE_SECONDS,900)

    async def test_sustained_silence_still_ends_the_session(self):
        await self.tick(2000,server.BROWSER_GRACE_SECONDS+1)
        self.r.stop.assert_awaited_once_with('browser_timeout',generation='current')

    async def test_first_viewer_deadline_is_unchanged(self):
        self.r.had_viewer=False
        await self.tick(1000,44);self.r.stop.assert_not_awaited()
        await self.tick(1000,46);self.r.stop.assert_awaited_once_with('browser_timeout',generation='current')

    async def test_time_the_service_did_not_run_is_not_browser_silence(self):
        # The periodic task woke 60 seconds late: no heartbeat could have been
        # processed, so 100 seconds of apparent silence is 40 seconds of real silence.
        await self.tick(2000,server.BROWSER_GRACE_SECONDS+10,pulse_age=61)
        self.r.stop.assert_not_awaited()
        stall=self.events('service_stall')
        self.assertEqual(len(stall),1);self.assertEqual(stall[0]['seconds'],60);self.assertTrue(stall[0]['active'])
        self.assertIn('cpuSeconds',stall[0]);self.assertEqual((self.r.stalls,self.r.stall_seconds),(1,60))
        self.assertEqual(self.r.status()['service'],{'stalls':1,'stallSeconds':60})

    async def test_stall_credit_cannot_hide_real_silence_or_move_contact_into_the_future(self):
        await self.tick(2000,server.BROWSER_GRACE_SECONDS+100,pulse_age=61)
        self.r.stop.assert_awaited_once_with('browser_timeout',generation='current')
        r=self.r;r.last_heartbeat=999;r.pulse_at=900
        with patch('server.time.monotonic',return_value=1000):self.assertEqual(r.pulse(),99)
        self.assertEqual(r.last_heartbeat,1000)

    async def test_stalled_startup_is_given_the_time_it_lost(self):
        r=self.r;r.frames=0;r.had_viewer=False
        r.started=950;r.last_heartbeat=990;r.pulse_at=969
        with patch('server.time.monotonic',return_value=1000),patch('server.asyncio.sleep',side_effect=[None,asyncio.CancelledError()]):
            with self.assertRaises(asyncio.CancelledError):await r.ticker()
        r.stop.assert_not_awaited();self.assertEqual(r.startup_credit,30)

    async def test_ordinary_scheduling_jitter_is_not_a_stall(self):
        r=self.r;r.pulse_at=1000
        with patch('server.time.monotonic',return_value=1002.4):self.assertEqual(r.pulse(),0)
        self.assertEqual(r.stalls,0);self.assertFalse(self.events('service_stall'))

    async def test_touch_video_and_status_requests_prove_presence(self):
        r=self.r;r.event=object();r.ec=object();r.last_heartbeat=0;r.command=AsyncMock(return_value=7)
        with patch('server.time.monotonic',return_value=500):
            await r.touch({'session':'current','x':.5,'y':.5,'down':True})
        self.assertEqual(r.last_heartbeat,500)
        r.active=False;r.last_heartbeat=0;r.seen();self.assertEqual(r.last_heartbeat,0)


class RobustnessTest(Base):
    async def test_unwritable_log_never_raises_into_the_service(self):
        r=self.r
        with patch('pathlib.Path.open',side_effect=OSError(28,'No space left on device')):
            r.log('anything',value=1)
            r.pulse_at=time.monotonic()-60;self.assertGreater(r.pulse(),50)
        self.assertGreaterEqual(r.log_failures,2)

    async def test_actual_bitrate_is_current_on_a_still_screen(self):
        r=self.r;r.video_bps=2900000;r.video_rate_at=100;r.video_rate_bytes=1000
        # Inside the measuring window the last completed window stands.
        self.assertEqual(r.current_video_bps(103),2900000)
        # Twenty quiet seconds later the stream is plainly not near its budget.
        self.assertEqual(r.current_video_bps(120),400)
        r.frames=0;self.assertIsNone(r.current_video_bps(120))

    async def test_slow_heartbeats_on_a_still_screen_do_not_reduce_the_budget(self):
        r=self.r;r.video_bps=2900000;r.video_rate_bytes=1000
        for step in range(8):
            now=1000+step*2;r.video_rate_at=now-30
            with patch('server.time.monotonic',return_value=now):
                await r.action({'action':'heartbeat','session':'current','link':{'heartbeatRttMs':2000,'streamLagMs':30}})
        self.assertEqual(r.video_budget.bps,3000000)


class KeepaliveTest(Base):
    async def run_keepalive(self,ticks=3):
        r=self.r;count=0
        async def delay(seconds):
            nonlocal count
            self.assertEqual(seconds,server.KEEPALIVE_SECONDS);count+=1
            if count>ticks:raise asyncio.CancelledError()
        with patch('server.asyncio.sleep',side_effect=delay):
            with self.assertRaises(asyncio.CancelledError):await r.keepalive()

    async def test_leases_and_helper_heartbeat_refresh_every_second_without_awaiting(self):
        r=self.r;writer=types.SimpleNamespace(write=Mock(),drain=AsyncMock());r.helper=types.SimpleNamespace(stdin=writer)
        r.video_budget.bps=1950000
        await self.run_keepalive()
        self.assertEqual(writer.write.call_count,3);writer.drain.assert_not_awaited()
        self.assertEqual(r.audio_lease.refresh.call_count,3)
        self.assertEqual([c.args for c in r.video_lease.refresh.call_args_list],[(1950000,)]*3)

    async def test_inactive_service_writes_no_lease(self):
        r=self.r;r.active=False
        await self.run_keepalive()
        r.audio_lease.refresh.assert_not_called();r.video_lease.refresh.assert_not_called()

    async def test_lease_failure_is_recorded_and_does_not_end_the_task(self):
        r=self.r;r.video_lease.refresh.side_effect=OSError('notify unavailable')
        await self.run_keepalive()
        self.assertEqual(r.video_lease.refresh.call_count,3)
        self.assertEqual(len(self.events('keepalive_failed')),3)

    async def test_unexpected_failure_does_not_end_the_task_either(self):
        r=self.r;r.audio_lease.refresh.side_effect=TypeError('unexpected')
        await self.run_keepalive()
        self.assertEqual(r.audio_lease.refresh.call_count,3)


class ResyncTest(Base):
    def viewer(self,continuous=True,queued=0):
        r=self.r;q=asyncio.Queue(maxsize=server.VIDEO_QUEUE_FRAGMENTS)
        state={'ready':True,'bytes':0,'closed':False,'session':'current','continuous_decode':continuous,'initialized':True,'draining':False,'awaiting_key':None,'resyncs':[]}
        for _ in range(queued):q.put_nowait(b'x'*100);state['bytes']+=100
        r.viewers[q]=state;return q,state

    def feed(self,key=False,count=1,size=6):
        r=self.r
        r.muxer=types.SimpleNamespace(base=0,fragment=lambda data,ts,nxt:b'F'+data)
        r.initial=b'INIT'
        for _ in range(count):
            self.clock+=33333
            r.frame((b'\x00\x00\x00\x02\x65\x01' if key else b'\x00\x00\x00\x02\x41\x01')+b'\x00'*(size-6),self.clock)

    async def asyncSetUp(self):
        await super().asyncSetUp();self.clock=0

    async def test_full_queue_resynchronizes_in_place_instead_of_closing(self):
        r=self.r;q,state=self.viewer(queued=server.VIDEO_QUEUE_FRAGMENTS)
        self.feed();self.feed()
        self.assertFalse(state['closed']);self.assertFalse(state['ready']);self.assertEqual((q.qsize(),state['bytes']),(0,0))
        self.assertFalse(self.events('video_viewer_dropped'))
        resync=self.events('video_viewer_resync')
        self.assertEqual((len(resync),resync[0]['reason'],resync[0]['dropped_bytes']),(1,'queue_limit',100*server.VIDEO_QUEUE_FRAGMENTS))
        await asyncio.sleep(0);r.command.assert_awaited_once_with(KEYFRAME,'current')
        # Delta frames are withheld; the next IDR resumes without a second
        # initialization segment, which the browser parser rejects.
        self.feed(count=3);self.assertEqual(q.qsize(),0)
        self.feed(key=True);self.feed()
        self.assertTrue(state['ready']);self.assertIsNone(state['awaiting_key'])
        first=q.get_nowait();self.assertTrue(first.startswith(b'F\x00\x00\x00\x02\x65'));self.assertNotIn(b'INIT',first)

    async def test_viewer_flushed_before_its_first_write_still_receives_initialization(self):
        q,state=self.viewer(queued=server.VIDEO_QUEUE_FRAGMENTS);state['initialized']=False
        self.feed();self.feed();self.feed(key=True);self.feed()
        self.assertTrue(q.get_nowait().startswith(b'INITF'))

    async def test_byte_limit_also_resynchronizes(self):
        q,state=self.viewer();state['bytes']=2*1024*1024
        self.feed();self.feed()
        self.assertFalse(state['closed']);self.assertEqual(self.events('video_viewer_resync')[0]['reason'],'byte_limit')

    async def test_blocked_socket_defers_the_keyframe_until_it_can_carry_one(self):
        r=self.r;q,state=self.viewer(queued=server.VIDEO_QUEUE_FRAGMENTS);state['draining']=True
        self.feed();self.feed();await asyncio.sleep(0)
        r.command.assert_not_awaited();self.assertTrue(self.events('video_viewer_resync')[0]['blocked'])

    async def test_persistent_overflow_falls_back_to_closing(self):
        q,state=self.viewer(queued=server.VIDEO_QUEUE_FRAGMENTS)
        for _ in range(4):
            self.feed();self.feed();state['ready']=True
            for _ in range(server.VIDEO_QUEUE_FRAGMENTS):q.put_nowait(b'x')
        self.assertFalse(state['closed']);self.assertEqual(len(self.events('video_viewer_resync')),4)
        self.feed();self.feed()
        self.assertTrue(state['closed']);self.assertEqual(len(self.events('video_viewer_dropped')),1)

    async def test_media_source_viewer_keeps_the_closing_behavior(self):
        q,state=self.viewer(continuous=False,queued=server.VIDEO_QUEUE_FRAGMENTS)
        self.feed();self.feed()
        self.assertTrue(state['closed']);self.assertFalse(self.events('video_viewer_resync'))

    async def test_shutdown_sentinel_is_never_discarded(self):
        q,state=self.viewer(queued=server.VIDEO_QUEUE_FRAGMENTS-1);q.put_nowait(None)
        self.feed();self.feed()
        self.assertTrue(state['closed']);self.assertIsNone(q.get_nowait())

    async def test_resync_keyframes_are_bounded_and_joins_share_a_pending_keyframe(self):
        r=self.r
        with patch('server.time.monotonic',return_value=100):self.assertTrue(await r.request_keyframe('current','viewer_resync'))
        with patch('server.time.monotonic',return_value=104):self.assertFalse(await r.request_keyframe('current','viewer_resync'))
        with patch('server.time.monotonic',return_value=105):self.assertTrue(await r.request_keyframe('current','viewer_resync'))
        # A join one second later shares the IDR that has not been emitted yet...
        r.video_last_idr_at=90
        with patch('server.time.monotonic',return_value=106):self.assertFalse(await r.request_keyframe('current','viewer_join'))
        # ...but once that IDR has passed, a joining viewer needs its own.
        r.video_last_idr_at=105.5
        with patch('server.time.monotonic',return_value=106):self.assertTrue(await r.request_keyframe('current','viewer_join'))
        self.assertEqual(r.command.await_count,3)

    async def test_ticker_recovers_a_viewer_whose_keyframe_never_arrived(self):
        r=self.r;q,state=self.viewer();state['ready']=False;state['awaiting_key']=995;r.event=object()
        r.last_keyframe_request=990
        await self.tick(1000,1)
        r.command.assert_awaited_once_with(KEYFRAME,'current')
        r.command.reset_mock();state['draining']=True;r.last_keyframe_request=990
        await self.tick(1000,1);r.command.assert_not_awaited()

    async def test_written_video_marks_initialization_and_presence(self):
        r=self.r;r.video=object();r.muxer=object();r.last_heartbeat=0;seen=[]
        async def drain():seen.append(dict(next(iter(r.viewers.values()))))
        writer=types.SimpleNamespace(write=Mock(),drain=drain,is_closing=lambda:False)
        eof=[False]
        reader=types.SimpleNamespace(at_eof=lambda:eof[0])
        task=asyncio.create_task(r.viewer(writer,reader,continuous_decode=True))
        for _ in range(5):await asyncio.sleep(0)
        q,state=next(iter(r.viewers.items()))
        self.assertFalse(state['initialized']);self.assertIsNotNone(state['awaiting_key'])
        state['ready']=True;state['awaiting_key']=None;state['bytes']=4;q.put_nowait(b'data')
        for _ in range(5):await asyncio.sleep(0)
        self.assertTrue(seen[-1]['draining']);self.assertTrue(state['initialized']);self.assertFalse(state['draining'])
        self.assertGreater(r.last_heartbeat,0)
        eof[0]=True;q.put_nowait(None);await asyncio.wait_for(task,2)


class LastFrameTest(Base):
    """iOS sends nothing while the screen is still; the newest frame must not wait for the next change."""
    def setUp(self):self.sent=[]
    def attach(self,continuous=True):
        r=self.r;q=asyncio.Queue(maxsize=60)
        r.viewers[q]={'ready':True,'bytes':0,'closed':False,'session':'current','continuous_decode':continuous,'initialized':True,'draining':False,'awaiting_key':None,'resyncs':[]}
        def fragment(data,ts,nxt):self.sent.append((ts,nxt));return b'F'+data
        r.muxer=types.SimpleNamespace(base=0,fragment=fragment);r.initial=b'INIT';return q

    async def test_last_frame_of_a_change_is_sent_without_waiting_for_the_next(self):
        r=self.r;q=self.attach()
        r.frame(b'\x00\x00\x00\x02\x41\x01',1000000);r.frame(b'\x00\x00\x00\x02\x41\x02',1033333)
        self.assertEqual(q.qsize(),1);self.assertEqual(self.sent,[(1000000,1033333)])
        await asyncio.sleep(server.PENDING_FLUSH_SECONDS+.05)
        # The second frame went out on its own, with a nominal duration, and the
        # timeline the browser compares itself with is that frame, not a later one.
        self.assertEqual(q.qsize(),2);self.assertEqual(self.sent[-1],(1033333,1033333+server.NOMINAL_FRAME_MICROS))
        self.assertIsNone(r.pending);self.assertEqual(r.video_ticks,1033333*90000//1000000)
        # The next change is not sent twice and keeps its own time.
        r.frame(b'\x00\x00\x00\x02\x41\x03',9000000);self.assertEqual(q.qsize(),2)
        await asyncio.sleep(server.PENDING_FLUSH_SECONDS+.05)
        self.assertEqual(q.qsize(),3);self.assertEqual(self.sent[-1][0],9000000)

    async def test_continuous_frames_keep_exact_durations_and_are_never_flushed_early(self):
        r=self.r;q=self.attach()
        for index in range(5):
            r.frame(b'\x00\x00\x00\x02\x41\x01',1000000+index*33333);await asyncio.sleep(.005)
        self.assertEqual(self.sent,[(1000000+i*33333,1000000+(i+1)*33333) for i in range(4)])

    async def test_media_source_viewer_keeps_waiting_for_the_next_frame(self):
        r=self.r;q=self.attach(continuous=False)
        r.frame(b'\x00\x00\x00\x02\x41\x01',1000000)
        await asyncio.sleep(server.PENDING_FLUSH_SECONDS+.05)
        self.assertEqual(q.qsize(),0);self.assertIsNotNone(r.pending);self.assertIsNone(r.pending_timer)

    async def test_no_viewer_or_a_stopped_session_sends_nothing_late(self):
        r=self.r;r.muxer=types.SimpleNamespace(base=0,fragment=lambda *a:self.sent.append(a) or b'F')
        r.frame(b'\x00\x00\x00\x02\x41\x01',1000000);self.assertIsNone(r.pending_timer)
        q=self.attach();r.frame(b'\x00\x00\x00\x02\x41\x01',2000000);count=len(self.sent)
        r.generation='another'
        await asyncio.sleep(server.PENDING_FLUSH_SECONDS+.05)
        self.assertEqual(len(self.sent),count)

    async def test_time_that_does_not_advance_shifts_the_timeline_instead_of_ending_the_session(self):
        # "video_error: next timestamp" ended a session after 8 seconds on November 15.
        r=self.r;q=self.attach()
        r.frame(b'\x00\x00\x00\x02\x41\x01',5000000);r.frame(b'\x00\x00\x00\x02\x41\x02',5000000)
        r.frame(b'\x00\x00\x00\x02\x41\x03',1000);r.frame(b'\x00\x00\x00\x02\x41\x04',34333)
        times=[ts for ts,_ in self.sent]
        self.assertEqual(times,sorted(set(times)));self.assertTrue(all(nxt>ts for ts,nxt in self.sent))
        # After the jump the native spacing (33.333 ms) is preserved.
        self.assertEqual(self.sent[-1][1]-self.sent[-1][0],33333)
        self.assertEqual(r.video_rebases,2);self.assertEqual(len(self.events('video_timestamp_rebased')),1)
        # A new video configuration starts a new timeline.
        r.reset_video_history();self.assertEqual((r.video_last_ts,r.video_ts_offset,r.video_rebases),(None,0,0))

    async def test_real_muxer_accepts_a_flushed_frame_followed_by_a_later_one(self):
        from h264_fixture import configuration
        from media import Muxer
        r=self.r;q=self.attach();r.muxer=Muxer(configuration(),1088,846)
        key=bytes.fromhex('000000026501');delta=bytes.fromhex('000000024101')
        r.frame(key,1000000);await asyncio.sleep(server.PENDING_FLUSH_SECONDS+.05)
        r.frame(delta,1005000);r.frame(delta,7000000);await asyncio.sleep(server.PENDING_FLUSH_SECONDS+.05)
        self.assertEqual(q.qsize(),3);self.assertFalse(self.events('video_flush_error'))


class VideoSocketTest(Base):
    async def test_video_response_gets_a_small_send_buffer(self):
        import socket
        r=self.r;calls=[];limits=[]
        sock=types.SimpleNamespace(setsockopt=lambda *a:calls.append(a))
        writer=types.SimpleNamespace(get_extra_info=lambda name:sock if name=='socket' else None,transport=types.SimpleNamespace(set_write_buffer_limits=lambda **k:limits.append(k)))
        r.tune_video_socket(writer)
        self.assertEqual(calls,[(socket.SOL_SOCKET,socket.SO_SNDBUF,server.VIDEO_SEND_BUFFER)])
        self.assertEqual(limits,[{'high':server.VIDEO_WRITE_HIGH,'low':server.VIDEO_WRITE_HIGH//4}])
        self.assertLessEqual(server.VIDEO_SEND_BUFFER,128*1024)

    async def test_a_socket_that_refuses_tuning_still_streams(self):
        r=self.r
        def refuse(*a):raise OSError(22,'Invalid argument')
        r.tune_video_socket(types.SimpleNamespace(get_extra_info=lambda name:types.SimpleNamespace(setsockopt=refuse)))
        r.tune_video_socket(types.SimpleNamespace())
        self.assertEqual(len(self.events('video_socket_tuning_failed')),2)

    async def test_real_connection_reports_the_requested_buffer(self):
        import socket
        r=self.r;seen={}
        async def handle(reader,writer):
            r.tune_video_socket(writer);seen['size']=writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF)
            seen['limits']=writer.transport.get_write_buffer_limits();writer.close()
        listener=await asyncio.start_server(handle,'127.0.0.1',0)
        port=listener.sockets[0].getsockname()[1]
        reader,writer=await asyncio.open_connection('127.0.0.1',port);await reader.read();writer.close()
        listener.close();await listener.wait_closed()
        self.assertEqual(seen['size'],server.VIDEO_SEND_BUFFER);self.assertEqual(seen['limits'],(server.VIDEO_WRITE_HIGH//4,server.VIDEO_WRITE_HIGH))
        self.assertFalse(self.events('video_socket_tuning_failed'))


class PresenceStatusTest(Base):
    async def test_status_reports_viewers_and_how_long_the_browser_has_been_silent(self):
        r=self.r;r.started=time.monotonic()-500;r.last_heartbeat=time.monotonic()-125
        r.viewers={object():{'closed':False},object():{'closed':True}}
        status=r.status()
        self.assertEqual(status['viewers'],1);self.assertIn(status['browserSilentSeconds'],(125,126))
        r.had_viewer=False;self.assertEqual(r.status()['browserSilentSeconds'],0)
        r.had_viewer=True;r.active=False;self.assertEqual(r.status()['browserSilentSeconds'],0)


class StopStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_status_reports_why_and_which_session_ended(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Receiver(types.SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'))
            self.assertIsNone(r.status()['lastStop']);self.assertEqual(r.status()['browserGraceSeconds'],900)
            r.active=True;r.generation='abc';r.started=r.last_heartbeat=time.monotonic()
            await r.stop('browser_timeout')
            value=r.status()['lastStop']
            self.assertEqual((value['session'],value['reason']),('abc','browser_timeout'));self.assertLessEqual(value['secondsAgo'],2)
            # A second stop with nothing active must not overwrite the record.
            await r.stop('user_stop');self.assertEqual(r.status()['lastStop']['reason'],'browser_timeout')

    async def test_companion_that_left_is_not_recorded_as_a_rejected_request(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Receiver(types.SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'))
            sock=types.SimpleNamespace(fileno=lambda:0)
            writer=types.SimpleNamespace(get_extra_info=lambda name:sock,write=Mock(),drain=AsyncMock(side_effect=ConnectionResetError('Connection lost')),close=Mock())
            reader=types.SimpleNamespace(readline=AsyncMock(return_value=b'{"action":"status"}\n'))
            class Libc:
                def getpeereid(self,fd,uid,gid):uid._obj.value=501;return 0
            with patch('server.ctypes.CDLL',return_value=Libc()):await r.ipc(reader,writer)
            writer.close.assert_called_once()
            log=(Path(folder)/'diagnostic.ndjson').read_text()
            self.assertNotIn('local_request_rejected',log)


if __name__=='__main__':unittest.main()
