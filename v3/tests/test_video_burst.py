import asyncio
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import crypto
from protocol import ScreenReceiver, nonce
from server import Receiver


def burst(key, count):
    config = bytes.fromhex('0164001fffe100016701000168')
    header = bytearray(128)
    struct.pack_into('<I', header, 0, len(config))
    header[4] = 1
    data = bytes(header) + config
    for i in range(count):
        plain = bytes.fromhex('000000026501')
        header = bytearray(128)
        struct.pack_into('<I', header, 0, len(plain) + 16)
        struct.pack_into('<Q', header, 8, int(i / 30 * 2**32))
        data += bytes(header) + crypto.encrypt(key, nonce(i), plain, bytes(header))
    return data


class VideoBurstTest(unittest.IsolatedAsyncioTestCase):
    async def test_buffered_native_burst_does_not_drop_healthy_viewer(self):
        # 220 small native frames fit inside one read. An unbounded synchronous
        # parser fills the 90-fragment HTTP queue before its consumer can run.
        with tempfile.TemporaryDirectory() as folder:
            r = Receiver(SimpleNamespace(state=folder, port=0, capture=None, helper='/unused'))
            r.active = True
            r.generation = 'burst'
            r.screen_key = bytes(range(32))
            r.stop = AsyncMock()
            r.configure = lambda config: setattr(r, 'muxer', SimpleNamespace(base=0,fragment=lambda *args: b'frame'))
            r.initial = b'init'
            q = asyncio.Queue(maxsize=90)
            state = {'bytes': 0, 'closed': False, 'session': r.generation, 'ready': True}
            r.viewers[q] = state
            reader = asyncio.StreamReader()
            reader.feed_data(burst(r.screen_key, 220))
            reader.feed_eof()
            writer = SimpleNamespace(close=lambda: None)
            delivered = []

            async def consume():
                while True:
                    value = await q.get()
                    state['bytes'] -= len(value)
                    delivered.append(value)
                    # Simulate a writable network with asynchronous drain.
                    await asyncio.sleep(.0001)

            task = asyncio.create_task(consume())
            try:
                await asyncio.wait_for(r.video_client(reader, writer), 3)
                deadline = asyncio.get_running_loop().time() + 1
                while not q.empty() and asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(.001)
                self.assertFalse(state['closed'])
                self.assertEqual(len(delivered), 219)
                self.assertEqual(r.frames, 220)
                self.assertEqual(state['bytes'], 0)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_stalled_viewer_cannot_stop_native_ingress(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Receiver(SimpleNamespace(state=folder,port=0,capture=None,helper='/unused'))
            r.active=True;r.generation='stalled';r.screen_key=bytes(range(32));r.stop=AsyncMock()
            r.configure=lambda config:setattr(r,'muxer',SimpleNamespace(base=0,fragment=lambda *args:b'frame'))
            r.initial=b'init';q=asyncio.Queue(maxsize=90)
            state={'bytes':0,'closed':False,'session':r.generation,'ready':True};r.viewers[q]=state
            reader=asyncio.StreamReader();reader.feed_data(burst(r.screen_key,220));reader.feed_eof()
            writer=SimpleNamespace(close=lambda:None)
            await asyncio.wait_for(r.video_client(reader,writer),.8)
            self.assertEqual(r.frames,220);self.assertTrue(state['closed'])

    async def test_budget_preserves_partial_packet_and_cipher_counter(self):
        key = bytes(range(32))
        frames = []
        parser = ScreenReceiver(key, lambda config: None, lambda data, ts: frames.append(data))
        wire = burst(key, 24)
        more = parser.push(wire[:-5], max_packets=8)
        while more:
            more = parser.push(b'', max_packets=8)
        self.assertEqual(len(frames), 23)
        self.assertFalse(parser.push(wire[-5:], max_packets=8))
        self.assertEqual(len(frames), 24)
        self.assertEqual(parser.counter, 24)
        self.assertFalse(parser.buffer)


if __name__ == '__main__':
    unittest.main()
