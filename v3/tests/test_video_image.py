"""Actual VideoToolbox/JPEG checks using independently encoded synthetic AVC.

Build the host bridge first, or set CDV3_VIDEO to its absolute path. FFmpeg is
only a fixture generator/reference decoder; it is never a runtime dependency.
"""
import ctypes as C
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'v3/backend'))
from video_image import JPEGDecoder, MAX_BYTES, VideoImageError, _Frame


def split_avc(data):
    nals = [n for n in re.split(b'\x00\x00\x00?\x01', data) if n]
    sps = next(n for n in nals if n[0] & 31 == 7)
    pps = next(n for n in nals if n[0] & 31 == 8)
    config = (b'\x01'+sps[1:4]+b'\xff\xe1'+len(sps).to_bytes(2, 'big')+sps+
              b'\x01'+len(pps).to_bytes(2, 'big')+pps)
    frames, current = [], []
    for nal in nals:
        kind = nal[0] & 31
        if kind == 9 and current:
            frames.append(b''.join(len(n).to_bytes(4, 'big')+n for n in current)); current = []
        if kind not in (7, 8, 9):
            current.append(nal)
    if current:
        frames.append(b''.join(len(n).to_bytes(4, 'big')+n for n in current))
    return config, frames


def fixture(width, height, count=30):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
        f'testsrc2=size={width}x{height}:rate=30', '-frames:v', str(count), '-c:v',
        'libx264', '-preset', 'veryfast', '-profile:v', 'high', '-level:v', '3.1',
        '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        '-colorspace', 'bt709', '-bf', '0', '-x264-params',
        'keyint=30:scenecut=0:repeat-headers=1:aud=1', '-f', 'h264', 'pipe:1'])
    config, frames = split_avc(raw)
    return raw, config, frames


def wait_for(predicate, seconds=3):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.01)
    raise AssertionError('Timed out waiting for native decoder')


class LazyVideoImageTest(unittest.TestCase):
    def test_import_does_not_load_native_library(self):
        subprocess.run([sys.executable, '-c',
            'import sys;sys.path.insert(0,"v3/backend");import video_image'], cwd=ROOT,
            env={**os.environ, 'CDV3_VIDEO':'/missing/libcardashvideo.dylib'},
            check=True, capture_output=True)

    def test_argument_limits_fail_before_library_load(self):
        for config, width, height, fps in ((b'', 320, 240, 10), (b'1'*65537, 320, 240, 10),
                (b'1'*12, 1280, 721, 10), (b'1'*12, True, 240, 10),
                (b'1'*12, 320, 240, 11), (b'1'*12, 320, 240, 0)):
            with self.subTest(width=width, height=height, fps=fps), self.assertRaises(ValueError):
                JPEGDecoder(config, width, height, fps)


HOST_LIBRARY = Path(os.environ.get('CDV3_VIDEO', ROOT/'build/v3/host/libcardashvideo.dylib'))


@unittest.skipUnless(sys.platform == 'darwin' and HOST_LIBRARY.is_file() and shutil.which('ffmpeg'),
                     'Requires a built host VideoToolbox bridge and FFmpeg')
class NativeVideoImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = os.environ.get('CDV3_VIDEO')
        os.environ['CDV3_VIDEO'] = str(HOST_LIBRARY.resolve())
        cls.fixtures = {size:fixture(*size) for size in ((320, 240), (1088, 846))}

    @classmethod
    def tearDownClass(cls):
        if cls.previous is None:
            os.environ.pop('CDV3_VIDEO', None)
        else:
            os.environ['CDV3_VIDEO'] = cls.previous

    def test_high_profile_and_cropped_frame_match_independent_reference(self):
        for (width, height), (raw, config, frames) in self.fixtures.items():
            with self.subTest(width=width, height=height), JPEGDecoder(config, width, height) as decoder:
                self.assertEqual(config[1:4], b'\x64\x00\x1f')
                start = time.monotonic()
                for i, frame in enumerate(frames):
                    self.assertTrue(decoder.feed(frame, i*33333))
                    time.sleep(1/30)
                wait_for(lambda:decoder.stats['pending'] == 0)
                latest = wait_for(lambda:decoder.latest())
                wait_for(lambda:decoder.latest()['timestamp'] == (len(frames)-1)*33333)
                latest = decoder.latest()
                stats = decoder.stats
                self.assertEqual(stats['decoded'], len(frames))
                self.assertEqual(stats['decodeFailures'], 0)
                self.assertEqual(stats['jpegFailures'], 0)
                self.assertEqual(stats['lastFailureStage'], 0)
                self.assertEqual(stats['lastSubmitStatus'], 0)
                self.assertEqual(stats['lastCallbackStatus'], 0)
                self.assertEqual(stats['failureStage'], 'none')
                self.assertEqual(stats['lastInputTimestamp'], (len(frames)-1)*33333)
                self.assertEqual(stats['lastInputBytes'], len(frames[-1]))
                self.assertIn(stats['hardwareSupported'], (0, 1))
                self.assertLessEqual(stats['maxPending'], 8)
                self.assertLessEqual(stats['jpegFrames'], (time.monotonic()-start)*10+2)
                self.assertGreater(stats['jpegFrames'], 2)
                self.assertLessEqual(len(latest['data']), MAX_BYTES)
                self.assertIsNone(decoder.latest(latest['sequence']))
                self.assertEqual((latest['width'], latest['height']), (width, height))
                info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-f', 'image2pipe',
                    '-show_entries', 'stream=width,height', '-of', 'json', 'pipe:0'], input=latest['data']))
                self.assertEqual(info['streams'][0], {'width':width, 'height':height})
                actual = subprocess.check_output(['ffmpeg', '-v', 'error', '-f', 'image2pipe', '-i',
                    'pipe:0', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], input=latest['data'])
                index = latest['timestamp']//33333
                expected = subprocess.check_output(['ffmpeg', '-v', 'error', '-f', 'h264', '-i', 'pipe:0',
                    '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', '-f', 'rawvideo',
                    '-pix_fmt', 'rgb24', 'pipe:1'], input=raw)
                self.assertEqual(len(actual), width*height*3)
                self.assertEqual(len(actual), len(expected))
                # Lossy JPEG/chroma conversion is expected; wrong geometry,
                # black output, or flipped images differ far more than this.
                difference = sum(abs(a-b) for a, b in zip(actual, expected))/len(actual)
                self.assertLess(difference, 8, f'RGB mean absolute error {difference}')

    def test_invalid_configuration_and_geometry(self):
        _, config, _ = self.fixtures[(320, 240)]
        for bad in (b'1'*16, config[:12], bytes([2])+config[1:], config[:4]+b'\xfc'+config[5:]):
            with self.assertRaises(VideoImageError):
                JPEGDecoder(bad, 320, 240)
        with self.assertRaises(VideoImageError):
            JPEGDecoder(config, 318, 240)

    def test_invalid_input_and_native_output_capacity(self):
        _, config, frames = self.fixtures[(320, 240)]
        with JPEGDecoder(config, 320, 240) as decoder:
            for bad in (b'', b'0'*(MAX_BYTES+1), bytearray(b'123'), None):
                with self.assertRaises(ValueError):
                    decoder.feed(bad, 0)
            for timestamp in (-1, True, 2**63):
                with self.assertRaises(ValueError):
                    decoder.feed(frames[0], timestamp)
            for bad in (b'\0\0\0\0\x65', b'\0\0\0\5\x65', b'\0\0\0\1\x7f'):
                self.assertFalse(decoder.feed(bad, 0))
            self.assertEqual(decoder.stats['decodeFailures'], 3)
            self.assertEqual(decoder.stats['lastFailureStage'], 1)
            self.assertEqual(decoder.stats['failureStage'], 'access_unit_validation')
            self.assertFalse(decoder.feed(frames[1], 33333)) # Needs initial IDR.
            for i, frame in enumerate(frames[:8]):
                self.assertTrue(decoder.feed(frame, i*33333)); time.sleep(.02)
            wait_for(decoder.latest)
            output = C.create_string_buffer(b'canary', 32); frame = _Frame()
            for capacity in (0, 2, MAX_BYTES+1):
                status = decoder._lib.cd_video_latest(decoder._handle, 0, output, capacity, C.byref(frame))
                self.assertLess(status, 0)
                self.assertEqual(output.raw[:6], b'canary')
            for sequence in (-1, True, 2**64):
                with self.assertRaises(ValueError):
                    decoder.latest(sequence)

    def test_burst_is_bounded_and_accepts_a_fresh_idr_chain(self):
        _, config, frames = self.fixtures[(320, 240)]
        with JPEGDecoder(config, 320, 240) as decoder:
            for i in range(400):
                decoder.feed(frames[i % len(frames)], i*33333)
            wait_for(lambda:decoder.stats['pending'] == 0)
            self.assertLessEqual(decoder.stats['maxPending'], 8)
            # Fast hardware may decode every access unit before the backlog
            # reaches eight; drops are not required for this real-device check.
            before = decoder.stats['submitted']
            # Force a fresh independent access-unit chain after overload.
            for i, frame in enumerate(frames[:12]):
                decoder.feed(frame, (400+i)*33333); time.sleep(.034)
            wait_for(lambda:decoder.stats['pending'] == 0)
            self.assertGreater(decoder.stats['submitted'], before)
            wait_for(lambda:decoder.latest() and decoder.latest()['timestamp'] >= 400*33333)

    def test_close_does_not_hold_python_mutex_during_native_drain(self):
        _, config, frames = self.fixtures[(320, 240)]
        decoder = JPEGDecoder(config, 320, 240)
        native = decoder._lib; entered, release = threading.Event(), threading.Event()
        class DelayedClose:
            def __getattr__(self, name):
                return getattr(native, name)
            def cd_video_destroy(self, *args):
                entered.set(); release.wait(3); native.cd_video_destroy(*args)
        decoder._lib = DelayedClose()
        closer = threading.Thread(target=decoder.close); closer.start()
        self.assertTrue(entered.wait(1))
        try:
            started = time.monotonic()
            self.assertFalse(decoder.feed(frames[0], 0)); self.assertIsNone(decoder.latest())
            self.assertTrue(decoder.stats['closed']); self.assertTrue(decoder.stats['closing'])
            self.assertLess(time.monotonic()-started, .1)
            second = threading.Thread(target=decoder.close); second.start()
            self.assertTrue(second.is_alive())
        finally:
            release.set(); closer.join(3); second.join(3)
        self.assertFalse(closer.is_alive()); self.assertFalse(second.is_alive())
        self.assertFalse(decoder.stats['closing'])

    def test_concurrent_feed_poll_stats_and_close(self):
        _, config, frames = self.fixtures[(320, 240)]
        errors = []
        for _ in range(6):
            decoder = JPEGDecoder(config, 320, 240)
            stop = threading.Event()
            def run_feed():
                try:
                    for i in range(100):
                        if stop.is_set():break
                        decoder.feed(frames[i % len(frames)], i*33333)
                        time.sleep(.001)
                except Exception as error:errors.append(error)
            def run_poll():
                try:
                    while not stop.is_set():
                        decoder.latest(); decoder.stats; time.sleep(.001)
                except Exception as error:errors.append(error)
            workers = [threading.Thread(target=run_feed), threading.Thread(target=run_poll)]
            for worker in workers:worker.start()
            time.sleep(.025); decoder.close(); stop.set()
            for worker in workers:worker.join(2); self.assertFalse(worker.is_alive())
            self.assertIsNone(decoder.latest()); self.assertFalse(decoder.feed(frames[0], 0))
            self.assertEqual(decoder.stats['pending'], 0); self.assertEqual(decoder.stats['workerBusy'], 0)
            decoder.close()
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
