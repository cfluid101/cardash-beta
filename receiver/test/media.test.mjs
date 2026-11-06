import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomBytes} from 'node:crypto';
import {ScreenReceiver} from '../lib/protocol.mjs';
const {AvcMuxer} = await import('../lib/mp4.mjs').catch(()=>assert.fail('H264 remux implementation is missing'));
const {SyntheticPeer} = await import('../lib/synthetic-peer.mjs');
const config=Buffer.from('0142c01fffe100046742c01f01000268ce','hex');
test('remuxer requires a keyframe and rejects malformed NALs and time reversal',()=>{
  const m=new AvcMuxer(config,640,360);
  assert.equal(m.fragment(Buffer.from('000000024188','hex'),0),null);
  assert(m.fragment(Buffer.from('000000026588','hex'),1000000));
  assert.throws(()=>m.fragment(Buffer.from('000000024188','hex'),999999),/time/i);
  assert.throws(()=>new AvcMuxer(config,640,360).fragment(Buffer.from('000010006588','hex'),0),/NAL/i);
  assert.throws(()=>new AvcMuxer(Buffer.from([1,66]),640,360),/config/i);
});
test('encrypted synthetic frames remux and independently decode; HID changes the encoded image', {timeout:20000},async()=>{
  const key=randomBytes(32),chunks=[];let mux,frames=0,peer;
  const first=[];
  const completion=new Promise((resolve,reject)=>{
    const receiver=new ScreenReceiver(key,{
      onConfig:c=>{mux=new AvcMuxer(c,320,180);chunks.push(mux.initialization());},
      onFrame:({data,timestampUs})=>{try{
        const f=mux.fragment(data,timestampUs);if(f)chunks.push(f);
        frames++;if(frames===8){const report=Buffer.from('0001a0005a00010000000000','hex');peer.input(report);}
        if(frames===22)resolve();
      }catch(e){reject(e);}}
    });
    peer=new SyntheticPeer({width:320,height:180,key,onPacket:b=>{try{receiver.push(b);}catch(e){reject(e);}},onError:reject});peer.start();
  });
  let timer;const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('synthetic frame timeout')),12000);});
  const dir=await mkdtemp(join(tmpdir(),'cardash-media-'));
  try{
    await Promise.race([completion,deadline]);await peer.stop();assert(peer.inputCount===1);assert.equal(peer.running,false);
    const file=join(dir,'stream.mp4');await writeFile(file,Buffer.concat(chunks));
    const probe=spawnSync('ffprobe',['-v','error','-count_frames','-show_entries','stream=width,height,nb_read_frames,codec_name','-of','json',file],{encoding:'utf8',timeout:8000});
    assert.equal(probe.status,0,probe.stderr);const stream=JSON.parse(probe.stdout).streams[0];
    assert.equal(stream.codec_name,'h264');assert.equal(stream.width,320);assert.equal(stream.height,180);assert(Number(stream.nb_read_frames)>=22);
    const decode=spawnSync('ffmpeg',['-v','error','-i',file,'-vf','format=rgb24,crop=1:1:160:90','-f','rawvideo','-'],{timeout:8000,maxBuffer:1024*1024});
    assert.equal(decode.status,0,decode.stderr.toString());
    const pixels=decode.stdout;assert(pixels.length>=22*3);assert(pixels[1]>pixels[0]+80,'initial center must be green');
    const last=pixels.subarray(-3);assert(last[0]>last[1]+80,'peer must turn encoded center red after HID input');
  }finally{clearTimeout(timer);await peer.stop();await rm(dir,{recursive:true,force:true});}
});
