# SPDX-License-Identifier: GPL-3.0-only
"""Loopback native PCM streams; no media files or microphone capture."""
import asyncio
import socket
import struct
import time
from audio import PCMDecoder
from audio_rtp import AACPacketDecoder
import crypto
from protocol import need

class DrainControl(asyncio.DatagramProtocol):
    pass

class AudioChannel(asyncio.DatagramProtocol):
    def __init__(self,owner,offer,lane):
        self.owner=owner;self.generation=owner.generation;self.type=int(offer['type'])
        self.audio_type=str(offer.get('audioType','default')).lower();self.lane=lane
        self.ident=int(offer['streamConnectionID'])&0xffffffffffffffff
        key=crypto.hkdf(owner.pair.shared,'DataStream-Salt'+str(self.ident),'DataStream-Output-Encryption-Key')
        self.decoder=(AACPacketDecoder if self.type==102 else PCMDecoder)(key,int(offer['audioFormat']))
        self.latency=max(0,min(1000,int(offer.get('audioLatencyMs',150))))/1000
        self.data_transport=None;self.control_transport=None;self.closed=False
        self.pending=bytearray();self.reset=True;self.serial=0;self.timer=None
        self.first_sample=None;self.origin=None;self.packets=0;self.frames=0;self.nonzero=0;self.errors=0;self.last_error=''
        self.input_timer=None;self.input_key=None;self.input_packets=0;self.input_timestamp=0
        port=offer.get('dataPort');purpose=self.audio_type in ('telephony','speechrecognition') or (self.audio_type in ('default','compatibility') and offer.get('input',True))
        if self.type==100 and purpose and type(port) is int and 1<=port<=65535:
            need(int(offer['audioFormat']) in (0x10,0x40),'Unsupported muted input format')
            frames=int(offer.get('framesPerPacket',round(self.decoder.rate*.02)))
            need(round(self.decoder.rate*.005)<=frames<=round(self.decoder.rate*.06),'Muted input packet duration')
            self.input_frames=frames;self.input_interval=frames/self.decoder.rate;self.input_port=port
            self.input_key=crypto.hkdf(owner.pair.shared,'DataStream-Salt'+str(self.ident),'DataStream-Input-Encryption-Key')
    async def listen(self):
        loop=asyncio.get_running_loop()
        try:
            self.data_transport,_=await loop.create_datagram_endpoint(lambda:self,local_addr=('::1',0),family=socket.AF_INET6)
            self.data_transport.get_extra_info('socket').setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,512*1024)
            self.control_transport,_=await loop.create_datagram_endpoint(DrainControl,local_addr=('::1',0),family=socket.AF_INET6)
            if self.input_key:self.input_timer=loop.call_later(.5,self.send_muted_input)
            return {'type':self.type,'dataPort':self.data_transport.get_extra_info('sockname')[1],'controlPort':self.control_transport.get_extra_info('sockname')[1],'streamConnectionID':self.ident}
        except BaseException:self.close();raise
    def send_muted_input(self):
        self.input_timer=None
        if self.closed or not self.owner.active or self.generation!=self.owner.generation:return
        # iOS16 requires duplex format declarations even for music output.
        # This beta has no microphone capture: a requested uplink is muted.
        header=struct.pack('>BBHII',0x80,100,self.input_packets&0xffff,self.input_timestamp,0)
        tail=struct.pack('<Q',self.input_packets)
        wire=header+crypto.encrypt(self.input_key,b'\0'*4+tail,bytes(self.input_frames*2),header[4:12])+tail
        self.data_transport.sendto(wire,('::1',self.input_port))
        self.input_packets+=1;self.input_timestamp=(self.input_timestamp+self.input_frames)&0xffffffff
        if self.input_packets==1:self.owner.log('audio_input_muted',lane=self.lane,rate=self.decoder.rate)
        self.input_timer=asyncio.get_running_loop().call_later(self.input_interval,self.send_muted_input)
    def datagram_received(self,data,address):
        if self.closed or not self.owner.active or self.generation!=self.owner.generation or address[0]!='::1':return
        try:value=self.decoder.decode(data)
        except ValueError as e:
            self.errors+=1;self.last_error=str(e)
            if self.errors==1 or self.errors%100==0:self.owner.log('audio_packet_rejected',lane=self.lane,count=self.errors,error=str(e))
            return
        if self.first_sample is None and value['pcm']:self.first_sample=value['timestamp'];self.origin=time.monotonic()
        self.packets+=1;self.frames+=value['sampleFrames'];self.nonzero+=value['nonzeroSamples']
        if value['reset'] and self.pending:self.flush()
        self.reset=self.reset or value['reset'];self.pending.extend(value['pcm'])
        if len(self.pending)>=int(self.decoder.rate*.02)*self.decoder.channels*2:self.flush()
        elif not self.timer:self.timer=asyncio.get_running_loop().call_later(.03,self.flush)
        if self.packets==1 or self.packets%1000==0:self.owner.log('native_audio',**self.status())
    def flush(self):
        if self.timer:self.timer.cancel();self.timer=None
        if not self.pending or self.closed:return
        self.serial=(self.serial+1)&0xffffffff
        flags=int(self.reset)|(2 if self.audio_type=='media' else 0)|(4 if self.owner.audio_ducked else 0)
        body=struct.pack('>IBBHI',self.decoder.rate,self.decoder.channels,self.lane,flags,self.serial)+bytes(self.pending)
        self.pending.clear();self.reset=False
        need(len(body)<=65548,'Audio batch overflow')
        self.owner.publish_audio(struct.pack('>I',len(body))+body)
    def status(self):
        return {'lane':self.lane,'type':self.type,'audioType':self.audio_type,'rate':self.decoder.rate,'channels':self.decoder.channels,'packets':self.packets,'sampleFrames':self.frames,'nonzeroSamples':self.nonzero,'rejectedPackets':self.errors,'lastError':self.last_error,'mutedInput':bool(self.input_key),'mutedInputPackets':self.input_packets}
    def feedback(self,offset=0):
        result={'type':self.type,'sampleRate':self.decoder.rate}
        if self.origin is not None:
            now=time.time()+offset;seconds=int(now)+2208988800;fraction=int((now-int(now))*4294967296)
            result.update(streamConnectionID=self.ident,timestamp=((seconds&0xffffffff)<<32)|fraction,timestampRawNs=time.monotonic_ns(),sampleTime=(self.first_sample+round(max(0,time.monotonic()-self.origin-self.latency)*self.decoder.rate))&0xffffffff)
        return result
    def close(self):
        self.closed=True
        if self.input_timer:self.input_timer.cancel();self.input_timer=None
        if self.timer:self.timer.cancel();self.timer=None
        self.pending.clear()
        if self.data_transport:self.data_transport.close()
        if self.control_transport:self.control_transport.close()
        if hasattr(self.decoder,'close'):self.decoder.close()
