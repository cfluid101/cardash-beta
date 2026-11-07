# SPDX-License-Identifier: GPL-3.0-only
# H264 remux only; pixels are never synthesized, decoded, or re-encoded here.
import struct
from protocol import need
u16=lambda n:struct.pack('>H',n)
u32=lambda n:struct.pack('>I',n)
u64=lambda n:struct.pack('>Q',n)
zero=lambda n:b'\0'*n

def box(kind,*parts):
 b=b''.join(parts);return u32(len(b)+8)+kind.encode('ascii')+b
def full(kind,version,flags,*parts):return box(kind,bytes([version,(flags>>16)&255,(flags>>8)&255,flags&255]),*parts)
MATRIX=b''.join(u32(n) for n in [65536,0,0,0,65536,0,0,0,0x40000000])
def inspect(config):
 need(9<=len(config)<=65536 and config[0]==1 and config[4]&3==3,'AVC configuration');at=6
 for count,kind in [(config[5]&31,7),(None,8)]:
  if count is None:need(at<len(config),'PPS count');count=config[at];at+=1
  need(count>0,'empty parameter sets')
  for _ in range(count):
   need(at+2<=len(config),'truncated configuration');n=struct.unpack_from('>H',config,at)[0];at+=2
   need(n>0 and at+n<=len(config) and config[at]&31==kind,'parameter set');at+=n
 return 'avc1.'+config[1:4].hex()
def keyframe(data):
 need(4<len(data)<=8388608,'NAL data size');at=0;key=False
 while at<len(data):
  need(at+4<=len(data),'NAL size');n=struct.unpack_from('>I',data,at)[0];at+=4
  need(0<n<=4194304 and at+n<=len(data),'NAL length');kind=data[at]&31
  need(1<=kind<=23,'NAL type');key=key or kind==5;at+=n
 return key
class Muxer:
 def __init__(self,config,width,height):
  self.codec=inspect(config);need(2<=width<=4096 and 2<=height<=4096,'dimensions')
  self.config=config;self.width=width;self.height=height;self.base=None;self.last=None;self.sequence=1
 def initialization(self):
  sample=box('avc1',zero(6),u16(1),zero(16),u16(self.width),u16(self.height),u32(0x00480000),u32(0x00480000),zero(4),u16(1),zero(32),u16(24),u16(65535),box('avcC',self.config))
  stbl=box('stbl',full('stsd',0,0,u32(1),sample),full('stts',0,0,u32(0)),full('stsc',0,0,u32(0)),full('stsz',0,0,u32(0),u32(0)),full('stco',0,0,u32(0)))
  minf=box('minf',full('vmhd',0,1,zero(8)),box('dinf',full('dref',0,0,u32(1),full('url ',0,1))),stbl)
  mdia=box('mdia',full('mdhd',0,0,zero(8),u32(90000),u32(0),u16(0x55c4),u16(0)),full('hdlr',0,0,u32(0),b'vide',zero(12),b'CarDash native CarPlay\0'),minf)
  trak=box('trak',full('tkhd',0,7,zero(8),u32(1),u32(0),u32(0),zero(8),zero(8),MATRIX,u32(self.width*65536),u32(self.height*65536)),mdia)
  mvhd=full('mvhd',0,0,zero(8),u32(90000),u32(0),u32(65536),u16(256),zero(10),MATRIX,zero(24),u32(2))
  moov=box('moov',mvhd,trak,box('mvex',full('trex',0,0,u32(1),u32(1),u32(3000),u32(0),u32(0))))
  return box('ftyp',b'iso6',u32(1),b'iso6isommp41avc1')+moov
 def fragment(self,data,timestamp,next_timestamp):
  key=keyframe(data);need(isinstance(timestamp,int) and timestamp>=0,'timestamp')
  if self.base is None:
   if not key:return None
   self.base=timestamp
  need(self.last is None or timestamp>self.last,'timestamp did not advance');self.last=timestamp
  dts=(timestamp-self.base)*90000//1000000
  need(next_timestamp>timestamp,'next timestamp');duration=(next_timestamp-self.base)*90000//1000000-dts
  need(0<duration<=54000000,'sample duration')
  def make(offset):return box('moof',full('mfhd',0,0,u32(self.sequence)),box('traf',full('tfhd',0,0x020000,u32(1)),full('tfdt',1,0,u64(dts)),full('trun',0,0x000f01,u32(1),u32(offset),u32(duration),u32(len(data)),u32(0x02000000 if key else 0x01010000),u32(0))))
  header=make(len(make(0))+8);self.sequence+=1
  return header+box('mdat',data)
