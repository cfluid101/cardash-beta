import asyncio
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from server import Receiver


class HeaderWriter:
    def __init__(self, receiver, failure=None):
        self.receiver = receiver
        self.failure = failure
        self.written = bytearray()

    def write(self, data):
        self.written.extend(data)

    async def drain(self):
        if self.failure:
            raise self.failure
        # A normal completion while headers drain must also release the slot.
        self.receiver.active = False

    def is_closing(self):
        return False


class ViewerCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        args = types.SimpleNamespace(state=self.tmp.name, port=0, capture=None, helper='/unused')
        self.receiver = Receiver(args)
        self.receiver.generation = 'test-generation'
        self.receiver.video = object()
        self.receiver.muxer = object()
        self.receiver.command = AsyncMock(return_value=1)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def check_repeated_header_disconnects(self, audio):
        r = self.receiver
        viewers = r.audio_viewers if audio else r.viewers
        for _ in range(3):
            r.active = True
            writer = HeaderWriter(r, ConnectionResetError('client disconnected during headers'))
            with self.assertRaises(ConnectionResetError):
                if audio:
                    await r.audio_viewer(writer, r.generation)
                else:
                    await r.viewer(writer)
            self.assertFalse(viewers, 'A failed header write leaked a viewer slot')
        r.active = True
        writer = HeaderWriter(r)
        if audio:
            await r.audio_viewer(writer, r.generation)
        else:
            await r.viewer(writer)
        self.assertIn(b'HTTP/1.1 200 OK', writer.written)
        self.assertFalse(viewers)

    async def test_audio_reconnect_after_repeated_header_disconnects(self):
        await self.check_repeated_header_disconnects(audio=True)

    async def test_video_reconnect_after_repeated_header_disconnects(self):
        await self.check_repeated_header_disconnects(audio=False)

    async def test_cancellation_during_headers_releases_both_viewer_slots(self):
        for audio in (False, True):
            r = self.receiver
            r.active = True
            writer = HeaderWriter(r, asyncio.CancelledError())
            with self.assertRaises(asyncio.CancelledError):
                if audio:
                    await r.audio_viewer(writer, r.generation)
                else:
                    await r.viewer(writer)
            self.assertFalse(r.audio_viewers if audio else r.viewers)

    async def test_video_header_completion_cannot_command_replacement_session(self):
        r = self.receiver
        r.active = True
        r.command = types.MethodType(Receiver.command, r)
        writer = HeaderWriter(r)
        async def replace_session():
            r.generation = 'replacement'
        writer.drain = replace_session
        with self.assertRaisesRegex(ValueError, 'Stale native session'):
            await r.viewer(writer)
        self.assertFalse(r.viewers)

    async def test_video_does_not_write_a_queued_old_frame_after_session_replacement(self):
        r = self.receiver
        r.active = True
        writer = HeaderWriter(r)
        headers = asyncio.Event()
        async def drained():
            headers.set()
        writer.drain = drained
        task = asyncio.create_task(r.viewer(writer))
        await headers.wait()
        for _ in range(3):
            await asyncio.sleep(0)
        queue, state = next(iter(r.viewers.items()))
        state['bytes'] = 9
        queue.put_nowait(b'old-frame')
        r.generation = 'replacement'
        await asyncio.wait_for(task, 1)
        self.assertNotIn(b'old-frame', writer.written)
        self.assertFalse(r.viewers)

    async def test_new_video_frames_skip_retired_viewer_queues(self):
        r = self.receiver
        r.generation = 'replacement'
        old, new = asyncio.Queue(), asyncio.Queue()
        for queue, session in ((old, 'retired'), (new, 'replacement')):
            r.viewers[queue] = {'closed': False, 'session': session, 'ready': True, 'bytes': 0}
        nal = bytes.fromhex('000000026501')
        r.pending = (nal, 0, True)
        r.muxer = types.SimpleNamespace(fragment=lambda *args: b'new-frame')
        r.frame(nal, 33333)
        self.assertTrue(old.empty())
        self.assertEqual(new.get_nowait(), b'new-frame')


    async def test_quiet_http_disconnect_releases_audio_and_video_slots(self):
        r = self.receiver
        r.active = True
        server = await asyncio.start_server(r.http, '127.0.0.1', 0)
        r.args.port = server.sockets[0].getsockname()[1]
        try:
            # Both media queues remain silent; no later packet can discover EOF.
            for path in ('audio', 'video'):
                for _ in range(2):
                    reader, writer = await asyncio.open_connection('127.0.0.1', r.args.port)
                    request = (f'GET /{path} HTTP/1.1\r\nHost: 127.0.0.1:{r.args.port}\r\n'
                               f'Cookie: cdv3={r.token}\r\nX-CarDash-Session: {r.generation}\r\n\r\n')
                    writer.write(request.encode())
                    await writer.drain()
                    headers = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 1)
                    self.assertIn(b'200 OK', headers)
                    writer.close()
                    await writer.wait_closed()
            deadline = asyncio.get_running_loop().time() + 5
            while (r.audio_viewers or r.viewers) and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(.02)
            self.assertFalse(r.audio_viewers, 'Silent audio clients retain both slots after TCP EOF')
            self.assertFalse(r.viewers, 'Silent video clients retain both slots after TCP EOF')
        finally:
            r.active = False
            for queue in [*r.audio_viewers, *r.viewers]:
                queue.put_nowait(None)
            server.close()
            await asyncio.wait_for(server.wait_closed(), 2)


    async def test_slow_video_viewer_logs_the_queue_limit_once(self):
        r = self.receiver
        r.log = Mock()
        video = asyncio.Queue(maxsize=1)
        video.put_nowait(b'video')
        r.viewers[video] = {'bytes': 5, 'closed': False, 'session': r.generation, 'ready': True}
        nal = bytes.fromhex('000000026501')
        r.pending = (nal, 0, True)
        r.muxer = types.SimpleNamespace(fragment=lambda *args: b'next')
        r.frame(nal, 33333)
        r.frame(nal, 66666)
        drops = [call for call in r.log.call_args_list if call.args[0] == 'video_viewer_dropped']
        self.assertEqual(len(drops), 1)
        self.assertEqual(drops[0].kwargs, {'reason': 'queue_limit', 'queued_bytes': 5, 'queued_fragments': 1})
        self.assertTrue(r.viewers[video]['closed'])


if __name__ == '__main__':
    unittest.main()
