# SPDX-License-Identifier: GPL-3.0-only
"""Lazy AudioToolbox raw AAC-LC decoder; no socket, playback or file access.

Input is one raw AAC access unit after RTP decryption, with no ADTS header.
Output is interleaved signed 16-bit little-endian PCM at the negotiated rate.
An empty output is valid while the converter primes, buffers, or discards an
incomplete access unit. This wrapper does not claim to validate all AAC syntax.
"""
import ctypes as C
import os
from pathlib import Path
import threading

MAX_PACKET_BYTES = 8192
MAX_OUTPUT_FRAMES = 8192
AAC_FORMATS = {0x400000: (44100, 2), 0x800000: (48000, 2)}


class AACError(ValueError):
    def __init__(self, operation, status):
        self.status = status
        super().__init__(f'AAC {operation} failed (OSStatus {status})')


def _library():
    # Loading this module alone never loads a native bridge. PCM-only operation
    # and tests do not require AudioToolbox, this dylib, or CDV3_AUDIO.
    path = Path(os.environ.get('CDV3_AUDIO', str(Path(__file__).with_name('libcardashaudio.dylib'))))
    lib = C.CDLL(str(path))
    lib.cd_aac_create.argtypes = [C.c_uint32, C.c_uint32, C.POINTER(C.c_int32)]
    lib.cd_aac_create.restype = C.c_void_p
    lib.cd_aac_decode.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p,
                                 C.c_uint32, C.POINTER(C.c_uint32)]
    lib.cd_aac_decode.restype = C.c_int32
    lib.cd_aac_flush.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32)]
    lib.cd_aac_flush.restype = C.c_int32
    lib.cd_aac_reset.argtypes = [C.c_void_p]
    lib.cd_aac_reset.restype = C.c_int32
    lib.cd_aac_destroy.argtypes = [C.c_void_p]
    lib.cd_aac_destroy.restype = None
    return lib


class AACDecoder:
    def __init__(self, rate, channels=2):
        if type(rate) is not int or rate not in (44100, 48000):
            raise ValueError('AAC-LC sample rate must be 44100 or 48000')
        if type(channels) is not int or channels not in (1, 2):
            raise ValueError('AAC-LC channels must be 1 or 2')
        self.rate, self.channels = rate, channels
        self._lock = threading.Lock()
        self._handle = None
        self._lib = _library()
        error = C.c_int32()
        self._handle = self._lib.cd_aac_create(rate, channels, C.byref(error))
        if not self._handle:
            raise AACError('create', error.value)

    def _check_open(self):
        if not self._handle:
            raise ValueError('AAC decoder is closed')

    def decode(self, packet):
        if not isinstance(packet, bytes) or not 0 < len(packet) <= MAX_PACKET_BYTES:
            raise ValueError('AAC packet must contain 1..8192 bytes')
        with self._lock:
            self._check_open()
            output = C.create_string_buffer(MAX_OUTPUT_FRAMES * self.channels * 2)
            frames = C.c_uint32()
            status = self._lib.cd_aac_decode(self._handle, packet, len(packet), output,
                                            MAX_OUTPUT_FRAMES, C.byref(frames))
            if status:
                raise AACError('decode', status)
            if frames.value > MAX_OUTPUT_FRAMES:
                raise ValueError('AAC output exceeded frame budget')
            return output.raw[:frames.value * self.channels * 2]

    def flush(self):
        """End this stream and return any delayed PCM; reset before new input."""
        with self._lock:
            self._check_open()
            output = C.create_string_buffer(MAX_OUTPUT_FRAMES * self.channels * 2)
            frames = C.c_uint32()
            status = self._lib.cd_aac_flush(self._handle, output, MAX_OUTPUT_FRAMES, C.byref(frames))
            if status:
                raise AACError('flush', status)
            if frames.value > MAX_OUTPUT_FRAMES:
                raise ValueError('AAC output exceeded frame budget')
            return output.raw[:frames.value * self.channels * 2]

    def reset(self):
        with self._lock:
            self._check_open()
            status = self._lib.cd_aac_reset(self._handle)
            if status:
                raise AACError('reset', status)

    def close(self):
        with self._lock:
            if self._handle:
                self._lib.cd_aac_destroy(self._handle)
                self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
