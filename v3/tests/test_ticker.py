import asyncio
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import DISPLAY, Receiver


class TickerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/unused'))
        self.r.active=True;self.r.generation='current';self.r.frames=100
        self.r.started=self.r.last_heartbeat=time.monotonic();self.r.had_viewer=True
        self.r.audio_lease=Mock();self.r.video_lease=Mock();self.r.command=AsyncMock();self.r.stop=AsyncMock()

    async def asyncTearDown(self):self.tmp.cleanup()

    async def test_healthy_viewer_refreshes_leases_without_restarting_encoder(self):
        r=self.r;r.viewers={object():{'session':'current'}};r.event=object()
        writer=types.SimpleNamespace(write=Mock(),drain=AsyncMock())
        r.helper=types.SimpleNamespace(stdin=writer)
        ticks=0
        async def tick_delay(seconds):
            nonlocal ticks
            self.assertEqual(seconds,2);ticks+=1
            if ticks>3:raise asyncio.CancelledError()
        with patch('server.asyncio.sleep',side_effect=tick_delay):
            with self.assertRaises(asyncio.CancelledError):await r.ticker()
        self.assertEqual(writer.write.call_args_list,[call(b'H')]*3)
        self.assertEqual(writer.drain.await_count,3)
        self.assertEqual(r.audio_lease.refresh.call_args_list,[call(True)]*3)
        r.stop.assert_not_awaited()
        r.command.assert_not_awaited()

    async def test_new_viewer_still_requests_one_keyframe_for_its_session(self):
        r=self.r;r.video=object();r.muxer=object()
        writer=types.SimpleNamespace(write=Mock(),drain=AsyncMock())
        reader=types.SimpleNamespace(at_eof=lambda:True)
        await r.viewer(writer,reader)
        r.command.assert_awaited_once_with({'type':'forceKeyFrame','params':{'uuid':DISPLAY}},'current')
        self.assertFalse(r.viewers)


if __name__=='__main__':unittest.main()
