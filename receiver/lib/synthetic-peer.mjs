// SPDX-License-Identifier: GPL-3.0-only
// Generated pixels are TEST DATA, not Apple UI or an emulated iPhone.
import {spawn} from 'node:child_process';
import {seal} from './protocol.mjs';
const lengthNAL=b=>{const h=Buffer.alloc(4);h.writeUInt32BE(b.length);return Buffer.concat([h,b]);};
class AnnexB{
  constructor(onNal){this.buffer=Buffer.alloc(0);this.onNal=onNal;}
  push(chunk){
    this.buffer=Buffer.concat([this.buffer,chunk]);if(this.buffer.length>8388608)throw new Error('encoder NAL buffer exceeded');
    const starts=[];for(let i=0;i+3<this.buffer.length;i++)if(this.buffer[i]===0&&this.buffer[i+1]===0){
      if(this.buffer[i+2]===1){starts.push([i,3]);i+=2;}
      else if(this.buffer[i+2]===0&&this.buffer[i+3]===1){starts.push([i,4]);i+=3;}
    }
    for(let i=0;i+1<starts.length;i++)this.onNal(Buffer.from(this.buffer.subarray(starts[i][0]+starts[i][1],starts[i+1][0])));
    if(starts.length)this.buffer=this.buffer.subarray(starts.at(-1)[0]);
  }
}
export class SyntheticPeer{
  constructor({width,height,key,onPacket,onError=()=>{}}){
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<2||height<2||width*height>1048576||width%2||height%2)throw new Error('invalid synthetic geometry');
    if(key.length!==32)throw new Error('invalid synthetic key');Object.assign(this,{width,height,key:Buffer.from(key),onPacket,onError});this.running=false;this.inputCount=0;this.frameCount=0;this.sentFrames=0;this.counter=0n;this.au=[];this.sps=null;this.pps=null;this.configured=false;this.red=false;
  }
  start(){
    if(this.child)throw new Error('peer already started');
    const args=['-hide_banner','-loglevel','error','-f','rawvideo','-pixel_format','rgb24','-video_size',`${this.width}x${this.height}`,'-framerate','30','-i','pipe:0','-an','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-profile:v','baseline','-pix_fmt','yuv420p','-bf','0','-g','15','-keyint_min','15','-sc_threshold','0','-x264-params','aud=1:repeat-headers=1','-flush_packets','1','-f','h264','pipe:1'];
    this.child=spawn('ffmpeg',args,{stdio:['pipe','pipe','pipe']});this.running=true;this.stderr='';
    this.closed=new Promise(resolve=>this.child.once('close',()=>{this.running=false;clearInterval(this.timer);resolve();}));
    this.child.on('error',e=>this.fail(e));this.child.stdin.on('error',e=>{if(this.running)this.fail(e);});
    this.child.stderr.on('data',b=>{this.stderr=(this.stderr+b.toString()).slice(-2048);});
    const parser=new AnnexB(nal=>this.nal(nal));this.child.stdout.on('data',b=>{if(!this.running)return;try{parser.push(b);}catch(e){this.fail(e);}});
    this.child.on('exit',code=>{if(this.running&&code!==0)this.fail(new Error('synthetic encoder exited: '+this.stderr));});
    this.timer=setInterval(()=>this.tick(),1000/30);this.tick();
  }
  fail(e){if(!this.running)return;this.onError(e);void this.stop();}
  tick(){
    if(!this.running||this.child.stdin.writableNeedDrain)return;
    const color=this.red?[200,25,30]:[20,170,45],pixels=Buffer.alloc(this.width*this.height*3);for(let i=0;i<pixels.length;i+=3){pixels[i]=color[0];pixels[i+1]=color[1];pixels[i+2]=color[2];}
    const x=(this.frameCount*7)%this.width;
    for(let y=0;y<Math.min(24,this.height);y++)for(let xx=x;xx<Math.min(x+12,this.width);xx++){const i=(y*this.width+xx)*3;pixels[i]=pixels[i+1]=pixels[i+2]=240;}
    this.frameCount++;this.child.stdin.write(pixels);
  }
  nal(nal){
    if(!nal.length)return;const type=nal[0]&31;
    if(type===9){if(this.au.length)this.flush();this.au=[];return;}
    if(type===7)this.sps=nal;if(type===8)this.pps=nal;this.au.push(nal);
  }
  packet(op,body,timeUs){
    const header=Buffer.alloc(128);header[4]=op;header.writeUInt32LE(body.length+(op===0?16:0));
    header.writeBigUInt64LE((BigInt(timeUs)<<32n)/1000000n,8);
    this.onPacket(Buffer.concat([header,op===0?seal(this.key,this.counter++,body,header):body]));
  }
  flush(){
    if(!this.running||!this.sps||!this.pps||!this.au.some(n=>(n[0]&31)===1||(n[0]&31)===5))return;
    if(!this.configured){const s=Buffer.alloc(2),p=Buffer.alloc(2);s.writeUInt16BE(this.sps.length);p.writeUInt16BE(this.pps.length);
      this.packet(1,Buffer.concat([Buffer.from([1,this.sps[1],this.sps[2],this.sps[3],255,225]),s,this.sps,Buffer.from([1]),p,this.pps]),0);this.configured=true;}
    this.packet(0,Buffer.concat(this.au.map(lengthNAL)),Math.round(this.sentFrames++*1000000/30));
  }
  input(report){
    if(!this.running||!Buffer.isBuffer(report)||report.length!==12)throw new Error('invalid peer HID input');
    for(let at=0;at<12;at+=6)if(report[at+1]){this.inputCount++;this.red=!this.red;break;}
  }
  async stop(){
    if(!this.child)return;this.running=false;clearInterval(this.timer);this.child.stdin.destroy();this.child.kill('SIGTERM');
    const force=setTimeout(()=>this.child.kill('SIGKILL'),1500);try{await this.closed;}finally{clearTimeout(force);}
  }
}
