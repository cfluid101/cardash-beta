# SPDX-License-Identifier: GPL-3.0-only
"""Authenticated type102 AAC-LC RTP access units to browser PCM."""
from array import array
import struct
import crypto
from aac import AACDecoder, AAC_FORMATS, MAX_PACKET_BYTES

class AACPacketDecoder:
    def __init__(self,key,format_bits):
        if not isinstance(key,bytes) or len(key)!=32:raise ValueError('Audio key must contain 32 bytes')
        if type(format_bits) is not int or format_bits not in AAC_FORMATS:raise ValueError('Unsupported AAC audioFormat')
        self.rate,self.channels=AAC_FORMATS[format_bits]
        self.key=key;self.codec=AACDecoder(self.rate,self.channels)
        self.last_nonce=None;self.next_timestamp=None
    def decode(self,wire):
        if not isinstance(wire,bytes) or not 37<=len(wire)<=MAX_PACKET_BYTES+36:raise ValueError('Invalid audio packet length')
        if wire[0]!=0x80:raise ValueError('Unsupported RTP header')
        tail=wire[-8:];counter=struct.unpack('<Q',tail)[0]
        payload=crypto.decrypt(self.key,b'\0'*4+tail,wire[12:-8],wire[4:12])
        if self.last_nonce is not None and counter<=self.last_nonce:raise ValueError('Audio nonce replay or out-of-order packet')
        sequence,timestamp=struct.unpack_from('>HI',wire,2)
        reset=self.next_timestamp is None or timestamp!=self.next_timestamp
        if reset:self.codec.reset()
        self.last_nonce=counter
        try:pcm=self.codec.decode(payload)
        except ValueError:self.next_timestamp=None;raise
        # AAC-LC carries 1024 samples per access unit, even when the converter
        # buffers output. A dropped datagram must reset decoder continuity.
        self.next_timestamp=(timestamp+1024)&0xffffffff
        samples=array('h');samples.frombytes(pcm)
        return dict(pcm=pcm,timestamp=timestamp,sequence=sequence,reset=reset,sampleFrames=len(pcm)//(self.channels*2),nonzeroSamples=len(samples)-samples.count(0))
    def close(self):self.codec.close()
