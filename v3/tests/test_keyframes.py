import asyncio
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import DISPLAY, Receiver

CONFIG=bytes.fromhex('0164001fffe100046764001f01000268ee')
KEY=bytes.fromhex('000000026501')
DELTA=bytes.fromhex('000000024101')


class KeyframesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/unused'))
        self.r.active=True;self.r.generation='current';self.r.audio_lease=Mock()

    async def asyncTearDown(self):self.tmp.cleanup()

    async def test_only_emitted_random_access_points_are_exposed_on_muxer_clock(self):
        r=self.r;r.configure(CONFIG)
        origin=1234567
        r.frame(KEY,origin)
        self.assertEqual(r.status()['videoKeyframes'],[],'A pending frame has not reached a browser yet')
        r.frame(DELTA,origin+33333)
        self.assertEqual(r.status()['videoKeyframes'],[0])
        self.assertEqual(r.status()['videoTimelineTicks'],2999)
        r.frame(KEY,origin+100000)
        self.assertEqual(r.status()['videoKeyframes'],[0])
        r.frame(DELTA,origin+133333)
        self.assertEqual(r.status()['videoKeyframes'],[0,9000])
        self.assertEqual(r.status()['videoTimelineTicks'],11999)
        self.assertEqual(r.video_gop_bytes,len(KEY))

    async def test_keyframe_history_is_bounded_and_config_change_resets_clock(self):
        r=self.r;r.configure(CONFIG)
        for i in range(36):r.frame(KEY,1000000+i*1000000)
        self.assertEqual(r.status()['videoKeyframes'],[i*90000 for i in range(3,35)])
        changed=bytearray(CONFIG);changed[3]=0x20;r.configure(bytes(changed))
        self.assertEqual(r.status()['videoKeyframes'],[])
        self.assertEqual(r.status()['videoTimelineTicks'],0)

    async def tick(self,now):
        r=self.r;r.started=r.last_heartbeat=now;r.had_viewer=True;r.frames=10
        with patch('server.time.monotonic',return_value=now),patch('server.asyncio.sleep',side_effect=[None,asyncio.CancelledError()]):
            with self.assertRaises(asyncio.CancelledError):await r.ticker()

    async def test_long_or_large_gop_requests_are_demand_driven_and_cooldown_bounded(self):
        r=self.r;r.viewers={object():{'session':'current'}};r.event=object();r.command=AsyncMock()
        r.video_last_idr_at=60;r.video_gop_bytes=100;r.last_keyframe_request=85
        await self.tick(100);r.command.assert_not_awaited()
        await self.tick(115)
        r.command.assert_awaited_once_with({'type':'forceKeyFrame','params':{'uuid':DISPLAY}},'current')
        self.assertEqual(r.last_keyframe_request,115)
        await self.tick(117);self.assertEqual(r.command.await_count,1)
        r.video_last_idr_at=140;r.video_gop_bytes=8*1024*1024+1
        await self.tick(145);self.assertEqual(r.command.await_count,2)
        r.video_last_idr_at=174;r.video_gop_bytes=100
        await self.tick(175);self.assertEqual(r.command.await_count,2)

    async def test_viewer_join_records_cooldown_and_stale_request_cannot_change_it(self):
        r=self.r;r.video=object();r.muxer=object();r.command=AsyncMock()
        writer=types.SimpleNamespace(write=Mock(),drain=AsyncMock())
        with patch('server.time.monotonic',return_value=200):
            await r.viewer(writer,types.SimpleNamespace(at_eof=lambda:True))
        self.assertEqual(r.last_keyframe_request,200)
        with self.assertRaisesRegex(ValueError,'Stale'):
            await r.request_keyframe('old','long_gop')
        self.assertEqual(r.last_keyframe_request,200)


if __name__=='__main__':unittest.main()
