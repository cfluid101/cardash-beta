# SPDX-License-Identifier: GPL-3.0-only
"""Bounded native AVC-to-JPEG adapter for the HTTP canvas display path.

This decodes the native CarPlay stream; it never captures the iPhone screen.
The native decoder owns at most eight pending access units, one latest decoded
pixel buffer, one JPEG worker and one latest JPEG. JPEG work is capped at 10 fps.
Loading this module alone does not load VideoToolbox or start a worker.
"""
import ctypes as C
import os
from pathlib import Path
import threading

MAX_BYTES = 4 * 1024 * 1024
MAX_PIXELS = 921600
FAILURE_STAGES = {0:'none', 1:'access_unit_validation', 2:'block_buffer_create',
                  3:'block_buffer_copy', 4:'sample_buffer_create',
                  5:'decoder_submit', 6:'decoder_callback', 7:'jpeg_encode'}


class VideoImageError(ValueError):
    def __init__(self, operation, status):
        self.status = status
        super().__init__(f'Native video {operation} failed (OSStatus {status})')


class _Stats(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in (
        'submitted', 'decoded', 'jpegFrames', 'inputDrops', 'decodedDrops',
        'outputReplaced', 'decodeFailures', 'jpegFailures', 'pending',
        'maxPending', 'latestSequence', 'latestBytes', 'workerBusy',
        'waitingForKeyframe')] + [('hardwareAcceleration', C.c_int64), ('lastStatus', C.c_int64)] + [
        (name, C.c_uint64) for name in ('lastFailureStage', 'lastInputBytes', 'lastInputTimestamp',
            'lastInputKeyframe', 'lastDecodeFlags', 'lastCallbackFlags', 'hardwareSupported')] + [
        (name, C.c_int64) for name in ('lastSubmitStatus', 'lastCallbackStatus', 'realTimeStatus')]


class _Frame(C.Structure):
    _fields_ = [('sequence', C.c_uint64), ('timestamp', C.c_uint64),
                ('size', C.c_uint32), ('width', C.c_uint32), ('height', C.c_uint32)]


def _library():
    default = Path(__file__).with_name('libcardashvideo.dylib')
    lib = C.CDLL(os.environ.get('CDV3_VIDEO', str(default)))
    try:
        version = lib.cd_video_abi_version
    except AttributeError as error:
        raise OSError('Native video library is outdated; ABI 2 is required') from error
    version.argtypes = []; version.restype = C.c_uint32
    if version() != 2:
        raise OSError('Native video library ABI mismatch; ABI 2 is required')
    lib.cd_video_create.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32,
                                   C.c_uint32, C.POINTER(C.c_int32)]
    lib.cd_video_create.restype = C.c_void_p
    lib.cd_video_feed.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint64]
    lib.cd_video_feed.restype = C.c_int32
    lib.cd_video_latest.argtypes = [C.c_void_p, C.c_uint64, C.c_void_p, C.c_uint32, C.POINTER(_Frame)]
    lib.cd_video_latest.restype = C.c_int32
    lib.cd_video_stats.argtypes = [C.c_void_p, C.POINTER(_Stats)]
    lib.cd_video_stats.restype = C.c_int32
    lib.cd_video_destroy.argtypes = [C.c_void_p, C.POINTER(_Stats)]
    lib.cd_video_destroy.restype = None
    return lib


class JPEGDecoder:
    def __init__(self, config, width, height, fps=10):
        if not isinstance(config, bytes) or not 9 <= len(config) <= 65536:
            raise ValueError('AVC configuration must contain 9..65536 bytes')
        if any(type(v) is not int or not 2 <= v <= 4096 for v in (width, height)) or width * height > MAX_PIXELS:
            raise ValueError('Native JPEG dimensions exceed the supported pixel budget')
        if type(fps) is not int or not 1 <= fps <= 10:
            raise ValueError('Native JPEG frame rate must be 1..10')
        self.width, self.height, self.fps = width, height, fps
        self._lock = threading.Lock()
        self._handle = None
        self._closing = False
        self._closed_event = threading.Event()
        self._final = _Stats()
        self._lib = _library()
        self._output = C.create_string_buffer(MAX_BYTES)
        error = C.c_int32()
        self._handle = self._lib.cd_video_create(config, len(config), width, height, fps, C.byref(error))
        if not self._handle:
            raise VideoImageError('create', error.value)

    def feed(self, data, timestamp_us):
        """Submit one AVCC access unit without waiting for decoding/JPEG work.

        False means a dropped or invalid access unit; inspect stats for details.
        After overload or decode failure, deltas are dropped until a new IDR.
        """
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
            raise ValueError('AVC access unit must contain 1..4194304 bytes')
        if type(timestamp_us) is not int or not 0 <= timestamp_us <= 0x7fffffffffffffff:
            raise ValueError('Native video timestamp is invalid')
        with self._lock:
            if not self._handle:
                return False
            return self._lib.cd_video_feed(self._handle, data, len(data), timestamp_us) > 0

    def latest(self, after_sequence=0):
        if type(after_sequence) is not int or not 0 <= after_sequence <= 0xffffffffffffffff:
            raise ValueError('JPEG sequence is invalid')
        with self._lock:
            if not self._handle:
                return None
            frame = _Frame()
            status = self._lib.cd_video_latest(self._handle, after_sequence, self._output, MAX_BYTES, C.byref(frame))
            if status < 0:
                raise VideoImageError('read JPEG', status)
            if not status:
                return None
            if not 0 < frame.size <= MAX_BYTES or (frame.width, frame.height) != (self.width, self.height):
                raise ValueError('Native JPEG output is invalid')
            return {'sequence': frame.sequence, 'data': C.string_at(self._output, frame.size),
                    'width': frame.width, 'height': frame.height, 'timestamp': frame.timestamp}

    @property
    def stats(self):
        with self._lock:
            current = _Stats()
            if self._handle:
                if self._lib.cd_video_stats(self._handle, C.byref(current)):
                    raise VideoImageError('stats', -1)
            else:
                current = self._final
            return {**{name: getattr(current, name) for name, _ in _Stats._fields_},
                    'width': self.width, 'height': self.height, 'fps': self.fps,
                    'failureStage': FAILURE_STAGES.get(current.lastFailureStage, 'unknown'),
                    'closed': not bool(self._handle), 'closing': self._closing}

    def close(self):
        # Detach under the short Python lock, then drain native callbacks and
        # the JPEG worker outside it. Old HTTP polls/feed calls return promptly.
        with self._lock:
            handle = self._handle
            if handle:
                self._lib.cd_video_stats(handle, C.byref(self._final))
                self._handle = None
                self._output = None
                self._closing = True
            closing = self._closing
        if not handle:
            if closing:
                self._closed_event.wait()
            return
        final = _Stats()
        try:
            self._lib.cd_video_destroy(handle, C.byref(final))
        finally:
            with self._lock:
                self._final = final
                self._closing = False
            self._closed_event.set()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
