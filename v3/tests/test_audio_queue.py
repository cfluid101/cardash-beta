import asyncio
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from server import Receiver


def packet(lane, sequence, flags=2, pcm_bytes=3960):
    body = struct.pack('>IBBHI', 44100, 2, lane, flags, sequence) + bytes(pcm_bytes)
    return struct.pack('>I', len(body)) + body


class PausedWriter:
    def __init__(self, receiver, stop_after=2):
        self.receiver = receiver
        self.header_ready = asyncio.Event()
        self.release_headers = asyncio.Event()
        self.records = []
        self.stop_after = stop_after

    def write(self, value):
        if not value.startswith(b'HTTP/'):
            self.records.append(value)

    async def drain(self):
        if not self.header_ready.is_set():
            self.header_ready.set()
            await self.release_headers.wait()
        elif len(self.records) >= self.stop_after:
            self.receiver.active = False

    def is_closing(self):
        return False


class AudioQueueTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.receiver = Receiver(SimpleNamespace(state=self.tmp.name, port=0, capture=None, helper='/unused'))
        self.receiver.active = True
        self.receiver.generation = 'test-session'
        self.receiver.log = Mock()

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_dropped_channel_reset_survives_serial_restart_on_each_lane(self):
        r = self.receiver
        writer = PausedWriter(r)
        task = asyncio.create_task(r.audio_viewer(writer, r.generation))
        try:
            await writer.header_ready.wait()
            queue, state = next(iter(r.audio_viewers.items()))
            self.assertEqual(queue.maxsize, 64)
            # The browser may still remember serial 500 from each prior channel.
            # Each replacement starts at 1; its reset packet is evicted in a burst.
            for index in range(66):
                lane, sequence = index % 2, index // 2 + 1
                r.publish_audio(packet(lane, sequence, 6 | (1 if sequence == 1 else 0)))
            self.assertFalse(state['closed'])
            self.assertEqual(queue.qsize(), 64)
            self.assertEqual(state['dropped_packets'], 2)
            self.assertLessEqual(state['bytes'], 256 * 1024)
            writer.release_headers.set()
            await asyncio.wait_for(task, 1)
            self.assertEqual(len(writer.records), 2)
            for lane, value in enumerate(writer.records):
                self.assertEqual(value[9], lane)
                self.assertEqual(struct.unpack_from('>I', value, 12)[0], 2)
                self.assertEqual(struct.unpack_from('>H', value, 10)[0], 7,
                                 'Delivery must restore reset while preserving media/duck flags')
            self.assertFalse(r.audio_viewers)
        finally:
            writer.release_headers.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_inflight_old_packet_cannot_consume_new_channel_reset(self):
        r = self.receiver
        writer = PausedWriter(r)
        task = asyncio.create_task(r.audio_viewer(writer, r.generation))
        try:
            await writer.header_ready.wait()
            queue, state = next(iter(r.audio_viewers.items()))
            r.publish_audio(packet(0, 500))
            get = queue.get
            raced = False
            async def get_then_native_burst():
                nonlocal raced
                value = await get()
                if not raced:
                    raced = True
                    for sequence in range(1, 66):
                        r.publish_audio(packet(0, sequence, 2 | (1 if sequence == 1 else 0)))
                return value
            queue.get = get_then_native_burst
            writer.release_headers.set()
            await asyncio.wait_for(task, 1)
            self.assertEqual([struct.unpack_from('>I', value, 12)[0] for value in writer.records], [500, 2])
            self.assertEqual([struct.unpack_from('>H', value, 10)[0] for value in writer.records], [2, 3])
            self.assertFalse(state['closed'])
        finally:
            writer.release_headers.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_byte_budget_discards_oldest_and_aggregates_warnings(self):
        r = self.receiver
        queue = asyncio.Queue(maxsize=64)
        state = {'bytes': 0, 'closed': False, 'reset_lanes': {}, 'next_record': 0, 'dropped_packets': 0, 'dropped_bytes': 0}
        r.audio_viewers[queue] = state
        for sequence in range(1, 106):
            r.publish_audio(packet(0, sequence, pcm_bytes=65536))
            self.assertLessEqual(state['bytes'], 256 * 1024)
            self.assertLessEqual(queue.qsize(), 64)
        self.assertFalse(state['closed'])
        self.assertEqual(state['dropped_packets'], 102)
        self.assertEqual(queue.qsize(), 3)
        self.assertEqual(struct.unpack_from('>I', queue.get_nowait()[1], 12)[0], 103)
        drops = [call for call in r.log.call_args_list if call.args[0] == 'audio_viewer_lag']
        self.assertEqual(len(drops), 2)
        self.assertEqual([call.kwargs['dropped_packets'] for call in drops], [1, 100])

    async def test_oversized_record_never_enters_bounded_queue(self):
        r = self.receiver
        queue = asyncio.Queue(maxsize=64)
        state = {'bytes': 0, 'closed': False, 'reset_lanes': {}, 'next_record': 0, 'dropped_packets': 0, 'dropped_bytes': 0}
        r.audio_viewers[queue] = state
        r.publish_audio(bytes(65553))
        self.assertTrue(state['closed'])
        self.assertTrue(queue.empty())
        self.assertEqual(state['bytes'], 0)

    async def test_stop_sentinel_is_preserved_when_queue_is_full(self):
        r = self.receiver
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait(None)
        state = {'bytes': 0, 'closed': False, 'reset_lanes': {}, 'next_record': 0, 'dropped_packets': 0, 'dropped_bytes': 0}
        r.audio_viewers[queue] = state
        r.publish_audio(packet(0, 1))
        self.assertIsNone(queue.get_nowait())
        self.assertTrue(queue.empty())
        self.assertEqual(state['bytes'], 0)


if __name__ == '__main__':
    unittest.main()
