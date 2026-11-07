# SPDX-License-Identifier: GPL-3.0-only
"""Session-scoped native display declarations and bounded AVC geometry parsing."""
from dataclasses import dataclass
import math
from media import inspect
from protocol import need

MAX_PIXELS=1280*720

@dataclass(frozen=True)
class DisplayGeometry:
    width: int=1280
    height: int=720
    requested_width: int=1280
    requested_height: int=720
    @property
    def viewport(self):return {'width':self.requested_width,'height':self.requested_height}
    @property
    def physical_height(self):return round(260*self.height/self.width)


def geometry(viewport=None):
    if viewport is None:return DisplayGeometry()
    need(isinstance(viewport,dict),'Viewport must provide width and height')
    w,h=viewport.get('width'),viewport.get('height')
    need(all(type(v) in (int,float) and math.isfinite(v) and 100<=v<=16384 for v in (w,h)),'Viewport dimensions invalid')
    requested_w,requested_h=round(w),round(h)
    # Keep the display landscape in a narrow/portrait preview. Tesla's observed
    # 773x601 area is wider than square and must retain its actual aspect ratio.
    aspect=max(1,w/h);need(aspect<=5,'Viewport aspect ratio unsupported')
    w,h=aspect,1
    scale=min(1280/w,960/h,math.sqrt(MAX_PIXELS/(w*h)))
    width=int(math.floor(w*scale/2))*2;height=int(math.floor(h*scale/2))*2
    return DisplayGeometry(width,height,requested_w,requested_h)


def apply_geometry(info,display):
    """Mutate only a fresh /info dictionary; preserve audio/auth declarations."""
    width,height=display.width,display.height
    d=info['displays'][0];d.update(widthPixels=width,heightPixels=height,widthPhysical=260,heightPhysical=display.physical_height)
    area={'widthPixels':width,'heightPixels':height,'originXPixels':0,'originYPixels':0}
    d['viewAreas']=[dict(area,safeArea=dict(area,drawUIOutsideSafeArea=True))];d['initialViewArea']=0
    finger=[0x05,0x0d,0x09,0x22,0xa1,0x02,0x09,0x38,0x75,0x08,0x95,0x01,0x81,0x02,0x15,0x00,0x25,0x01,0x09,0x33,0x75,0x01,0x95,0x01,0x81,0x02,0x95,0x07,0x81,0x03,0x05,0x01,0x26,width&255,width>>8,0x09,0x30,0x75,0x10,0x95,0x01,0x81,0x02,0x26,height&255,height>>8,0x09,0x31,0x81,0x02,0xc0]
    info['hidDevices'][0]['hidDescriptor']=bytes([0x05,0x0d,0x09,0x04,0xa1,0x01,*finger,*finger,0xc0])
    return info


class Bits:
    def __init__(self,data):self.data=data;self.position=0
    def read(self,count=1):
        need(0<=count<=32 and self.position+count<=len(self.data)*8,'Truncated H.264 SPS')
        value=0
        for _ in range(count):
            value=(value<<1)|((self.data[self.position//8]>>(7-self.position%8))&1);self.position+=1
        return value
    def ue(self):
        zeros=0
        while not self.read():
            zeros+=1;need(zeros<=31,'H.264 SPS integer overflow')
        return (1<<zeros)-1+(self.read(zeros) if zeros else 0)
    def se(self):
        value=self.ue();return (value+1)//2 if value&1 else -(value//2)


def sps_dimensions(nal):
    need(nal and nal[0]&31==7,'Missing H.264 SPS')
    rbsp=bytearray();zeros=0
    for i,b in enumerate(nal[1:],1):
        if zeros>=2 and b==3:
            need(i+1<len(nal) and nal[i+1]<=3,'Invalid SPS emulation prevention');zeros=0;continue
        rbsp.append(b);zeros=zeros+1 if b==0 else 0
    bits=Bits(rbsp);profile=bits.read(8);bits.read(8);bits.read(8);need(bits.ue()<=31,'SPS identifier')
    chroma=1;separate=False
    if profile in (100,110,122,244,44,83,86,118,128,138,139,134,135):
        chroma=bits.ue();need(chroma<=3,'SPS chroma format')
        if chroma==3:separate=bool(bits.read())
        need(bits.ue()<=6 and bits.ue()<=6,'SPS bit depth');bits.read()
        if bits.read():
            for i in range(12 if chroma==3 else 8):
                if bits.read():
                    last=next_scale=8
                    for _ in range(16 if i<6 else 64):
                        if next_scale:next_scale=(last+bits.se()+256)%256
                        last=next_scale or last
    need(bits.ue()<=12,'SPS frame number range');order=bits.ue();need(order<=2,'SPS picture order')
    if order==0:need(bits.ue()<=12,'SPS picture order range')
    elif order==1:
        bits.read();bits.se();bits.se();cycle=bits.ue();need(cycle<=255,'SPS picture order cycle')
        for _ in range(cycle):bits.se()
    need(bits.ue()<=16,'SPS reference frames');bits.read()
    columns,rows=bits.ue()+1,bits.ue()+1;need(columns<=256 and rows<=256,'SPS coded dimensions')
    frame_only=bits.read()
    if not frame_only:bits.read()
    bits.read();left=right=top=bottom=0
    if bits.read():left,right,top,bottom=(bits.ue() for _ in range(4))
    array_type=0 if separate else chroma
    crop_x=1 if array_type in (0,3) else 2
    crop_y=(2-frame_only)*(2 if array_type==1 else 1)
    width=columns*16-(left+right)*crop_x;height=(2-frame_only)*rows*16-(top+bottom)*crop_y
    need(0<width<=4096 and 0<height<=4096,'SPS cropped dimensions')
    return width,height


def avc_dimensions(config):
    inspect(config);at=6;sizes=[]
    for _ in range(config[5]&31):
        size=int.from_bytes(config[at:at+2],'big');at+=2;sizes.append(sps_dimensions(config[at:at+size]));at+=size
    need(sizes and len(set(sizes))==1,'Conflicting SPS display dimensions')
    return sizes[0]
