# SPDX-License-Identifier: GPL-3.0-only
"""Pure CarPlay RTP/PCM decoder; no sockets, playback, or global session state.

The UDP AEAD layout and PCM formats follow DiPlay 0.2.22 AudioStream.kt.
Provenance is recorded in ../NOTICE.md. Audio packets carry a fixed 12-byte RTP
header, sealed payload with a 16-byte tag, and an 8-byte little-endian nonce.
"""
from array import array
import struct
import crypto

PCM_FORMATS={
    0x4:(8000,1),0x8:(8000,2),
    0x10:(16000,1),0x20:(16000,2),
    0x40:(24000,1),0x80:(24000,2),
    0x100:(32000,1),0x200:(32000,2),
    0x400:(44100,1),0x800:(44100,2),
    0x4000:(48000,1),0x8000:(48000,2),
}
MAX_PCM_BYTES=16384
PACKET_OVERHEAD=12+16+8

class PCMDecoder:
    """One negotiated stream. Strict nonce ordering is for loopback transport.

    ``reset`` marks the first packet or a discontinuity in the RTP sample clock.
    Sequence numbers are diagnostic only: they are not authenticated by this
    wire protocol. Nonce counters are authenticated and never reused here.
    """
    def __init__(self,key:bytes,format_bits:int):
        if not isinstance(key,bytes) or len(key)!=32:
            raise ValueError('Audio key must contain 32 bytes')
        if type(format_bits) is not int or format_bits not in PCM_FORMATS:
            raise ValueError('Unsupported PCM audioFormat')
        self.rate,self.channels=PCM_FORMATS[format_bits]
        self._key=key
        self._last_nonce=None
        self._next_timestamp=None

    def decode(self,wire:bytes)->dict:
        if not isinstance(wire,bytes) or not PACKET_OVERHEAD<=len(wire)<=MAX_PCM_BYTES+PACKET_OVERHEAD:
            raise ValueError('Invalid audio packet length')
        # V=2, no padding, extension or CSRC list: the AAD layout assumes this.
        if wire[0]!=0x80:
            raise ValueError('Unsupported RTP header')
        nonce_tail=wire[-8:]
        nonce_counter=struct.unpack('<Q',nonce_tail)[0]
        payload=crypto.decrypt(self._key,b'\0'*4+nonce_tail,wire[12:-8],wire[4:12])
        frame_bytes=2*self.channels
        if not payload or len(payload)%frame_bytes:
            raise ValueError('PCM payload is empty or not frame-aligned')
        if self._last_nonce is not None and nonce_counter<=self._last_nonce:
            raise ValueError('Audio nonce replay or out-of-order packet')

        sequence,timestamp=struct.unpack_from('>HI',wire,2)
        sample_frames=len(payload)//frame_bytes
        reset=self._next_timestamp is None or timestamp!=self._next_timestamp

        # Zero is endian-independent. array.count/byteswap do the bulk work in C;
        # swapping each input pair converts wire S16BE to S16LE on any host.
        samples=array('h');samples.frombytes(payload)
        nonzero=len(samples)-samples.count(0)
        samples.byteswap()
        pcm=samples.tobytes()

        # Malformed or unauthenticated packets cannot consume a nonce or clock.
        self._last_nonce=nonce_counter
        self._next_timestamp=(timestamp+sample_frames)&0xffffffff
        return {'pcm':pcm,'timestamp':timestamp,'sequence':sequence,'reset':reset,
                'sampleFrames':sample_frames,'nonzeroSamples':nonzero}
