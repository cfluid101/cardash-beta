// SPDX-License-Identifier: GPL-3.0-only
// H.264 AVCC -> fragmented ISO BMFF. No pixel decode or re-encode.
const need=(x,m)=>{if(!x)throw new Error(m);};
const u16=n=>{const b=Buffer.alloc(2);b.writeUInt16BE(n);return b;};
const u32=n=>{const b=Buffer.alloc(4);b.writeUInt32BE(n);return b;};
const u64=n=>{const b=Buffer.alloc(8);b.writeBigUInt64BE(BigInt(n));return b;};
const zero=n=>Buffer.alloc(n), ascii=s=>Buffer.from(s,'ascii');
const box=(type,...data)=>{const b=Buffer.concat(data);return Buffer.concat([u32(b.length+8),ascii(type),b]);};
const full=(type,version,flags,...data)=>box(type,Buffer.from([version,(flags>>>16)&255,(flags>>>8)&255,flags&255]),...data);
const matrix=Buffer.concat([u32(65536),u32(0),u32(0),u32(0),u32(65536),u32(0),u32(0),u32(0),u32(0x40000000)]);
export function inspectAvcc(c){
  need(Buffer.isBuffer(c)&&c.length>=9&&c.length<=65536&&c[0]===1&&(c[4]&3)===3,'invalid AVC configuration');
  let at=6;const sps=c[5]&31;need(sps>0,'configuration has no SPS');
  function sets(count,type){for(let i=0;i<count;i++){need(at+2<=c.length,'truncated configuration');const n=c.readUInt16BE(at);at+=2;need(n>0&&at+n<=c.length&&(c[at]&31)===type,'invalid configuration NAL');at+=n;}}
  sets(sps,7);need(at<c.length,'configuration has no PPS');const pps=c[at++];need(pps>0,'configuration has no PPS');sets(pps,8);
  return `avc1.${c.subarray(1,4).toString('hex')}`;
}
export class AvcMuxer{
  constructor(config,width,height,{fps=30}={}){
    this.codec=inspectAvcc(config);need(Number.isInteger(width)&&Number.isInteger(height)&&width>=2&&height>=2&&width<=4096&&height<=4096,'invalid dimensions');
    need(Number.isInteger(fps)&&fps>=1&&fps<=60,'invalid frame rate');this.config=Buffer.from(config);this.width=width;this.height=height;this.duration=90000/fps;this.sequence=1;this.base=null;this.last=null;
  }
  initialization(){
    const sample=box('avc1',zero(6),u16(1),zero(16),u16(this.width),u16(this.height),u32(0x00480000),u32(0x00480000),zero(4),u16(1),zero(32),u16(24),u16(65535),box('avcC',this.config));
    const stbl=box('stbl',full('stsd',0,0,u32(1),sample),full('stts',0,0,u32(0)),full('stsc',0,0,u32(0)),full('stsz',0,0,u32(0),u32(0)),full('stco',0,0,u32(0)));
    const minf=box('minf',full('vmhd',0,1,zero(8)),box('dinf',full('dref',0,0,u32(1),full('url ',0,1))),stbl);
    const mdia=box('mdia',full('mdhd',0,0,zero(8),u32(90000),u32(0),u16(0x55c4),u16(0)),full('hdlr',0,0,u32(0),ascii('vide'),zero(12),ascii('CarDash native CarPlay\0')),minf);
    const trak=box('trak',full('tkhd',0,7,zero(8),u32(1),u32(0),u32(0),zero(8),zero(8),matrix,u32(this.width*65536),u32(this.height*65536)),mdia);
    const mvhd=full('mvhd',0,0,zero(8),u32(90000),u32(0),u32(65536),u16(256),zero(10),matrix,zero(24),u32(2));
    const moov=box('moov',mvhd,trak,box('mvex',full('trex',0,0,u32(1),u32(1),u32(this.duration),u32(0),u32(0))));
    return Buffer.concat([box('ftyp',ascii('iso6'),u32(1),ascii('iso6isommp41avc1')),moov]);
  }
  fragment(data,timestampUs,nextTimestampUs=null){
    need(Buffer.isBuffer(data)&&data.length>4&&data.length<=8388608,'invalid NAL data');let at=0,key=false;
    while(at<data.length){need(at+4<=data.length,'truncated NAL size');const n=data.readUInt32BE(at);at+=4;need(n>0&&n<=4194304&&at+n<=data.length,'invalid NAL length');const type=data[at]&31;need(type>=1&&type<=23,'invalid NAL type');if(type===5)key=true;at+=n;}
    need(Number.isSafeInteger(timestampUs)&&timestampUs>=0,'invalid timestamp');
    if(this.base===null){if(!key)return null;this.base=timestampUs;}
    need(this.last===null||timestampUs>this.last,'timestamp did not advance');this.last=timestampUs;
    const dts=(BigInt(timestampUs-this.base)*90000n)/1000000n;
    let duration=this.duration;if(nextTimestampUs!==null){need(Number.isSafeInteger(nextTimestampUs)&&nextTimestampUs>timestampUs,'invalid next timestamp');duration=Number((BigInt(nextTimestampUs-this.base)*90000n)/1000000n-dts);need(duration>0&&duration<=54000000,'invalid sample duration');}
    const make=offset=>box('moof',full('mfhd',0,0,u32(this.sequence)),box('traf',full('tfhd',0,0x020000,u32(1)),full('tfdt',1,0,u64(dts)),full('trun',0,0x000f01,u32(1),u32(offset),u32(duration),u32(data.length),u32(key?0x02000000:0x01010000),u32(0))));
    const header=make(make(0).length+8);this.sequence++;return Buffer.concat([header,box('mdat',data)]);
  }
}
