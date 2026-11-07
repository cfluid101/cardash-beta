import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../../',import.meta.url));
const code=await readFile(new URL('../web/canvas-video.js',import.meta.url),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
// Exercise the actual shipping muxer without loading its unrelated crypto bridge.
const fixtureData=JSON.parse(execFileSync('python3',['-c',`
import sys,types,json,base64
sys.path.insert(0,'v3/backend')
def need(value,message):
 if not value:raise ValueError(message)
sys.modules['protocol']=types.SimpleNamespace(need=need)
from media import Muxer
m=Muxer(bytes.fromhex('0164001fffe100046764001f01000268ee'),1280,720)
k=bytes.fromhex('000000026501');d=bytes.fromhex('000000024101')
parts=[m.initialization(),m.fragment(k,1000000,1033334),m.fragment(d,1033334,1066667),m.fragment(k,1066667,1100000)]
parts.append(m.initialization()+b''.join(m.fragment(k if i==0 else d,2000000+i*33333,2000000+(i+1)*33333) for i in range(72)))
print(json.dumps([base64.b64encode(p).decode() for p in parts]))
`],{cwd:root,encoding:'utf8'})).map(s=>Buffer.from(s,'base64'));
const [init,key,delta,key2,burst]=fixtureData;

function fixture({secure=true,available=true,supported=true,configureError='',noContext=false}={}){
 const decoders=[],chunks=[],errors=[],frames=[],draws=[],timers=new Map();let timerId=0;
 const context2d={drawImage(...args){draws.push(args);}};
 const canvas={width:0,height:0,style:{},getContext(name){return name==='2d'&&!noContext?context2d:null;},addEventListener(){},removeEventListener(){}};
 class Decoder {
  static async isConfigSupported(config){return {supported,config};}
  constructor(callbacks){this.callbacks=callbacks;this.state='unconfigured';this.decodeQueueSize=0;this.listeners=new Map();decoders.push(this);}
  configure(config){if(configureError)throw new Error(configureError);this.config=config;this.state='configured';}
  decode(chunk){chunks.push(chunk);}
  close(){this.state='closed';}
  addEventListener(name,callback){if(!this.listeners.has(name))this.listeners.set(name,new Set());this.listeners.get(name).add(callback);}
  removeEventListener(name,callback){this.listeners.get(name)?.delete(callback);}
  drain(){this.decodeQueueSize=0;for(const callback of [...(this.listeners.get('dequeue')||[])])callback();}
 }
 class Chunk {constructor(value){Object.assign(this,value);}}
 const window={isSecureContext:secure,VideoDecoder:available?Decoder:undefined,EncodedVideoChunk:Chunk};
 const globals={window,Uint8Array,DataView,ArrayBuffer,Error,Math,Number,Promise,setTimeout(fn,delay=0){const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);}};
 vm.runInNewContext(code,globals);
 const api=window.CarDashCanvas;
 function create(options={}){return api.create({canvas,codec:'avc1.64001f',width:1280,height:720,onFrame:v=>frames.push(v),onError:e=>errors.push(e),...options});}
 function output(decoder=decoders.at(-1),timestamp=0){const frame={displayWidth:1280,displayHeight:720,timestamp,closed:0,close(){this.closed++;}};decoder.callbacks.output(frame);return frame;}
 function fireTimers(delay){for(const [id,task] of [...timers])if(task.delay===delay){timers.delete(id);task.fn();}}
 function render(){fireTimers(0);}
 return {api,create,canvas,decoders,chunks,errors,frames,draws,output,render,timers,fireTimers,Decoder};
}
async function configured(f){const player=f.create();await player.push(init);return player;}

test('availability requires a secure context and WebCodecs, and missing capabilities fail clearly',()=>{
 for(const options of [{secure:false},{available:false}]){const f=fixture(options);assert.equal(f.api.available(),false);assert.throws(()=>f.create(),/secure|WebCodecs/i);}
 const f=fixture();assert.equal(f.api.available(),true);assert.throws(()=>f.create({width:0}),/dimension/i);
 assert.throws(()=>fixture({noContext:true}).create(),/canvas|render/i);
});

test('actual muxer init and split/coalesced fragments configure AVCC and preserve 90 kHz timing',async()=>{
 const f=fixture(),player=f.create();const stream=Buffer.concat([init,key,delta]);
 for(let at=0;at<stream.length;at++)await player.push(new Uint8Array(stream.subarray(at,at+1)));
 await settle();assert.equal(f.errors.length,0);assert.equal(f.decoders.length,1);
 const config=f.decoders[0].config;assert.equal(config.codec,'avc1.64001f');assert.equal(config.codedWidth,1280);assert.equal(config.codedHeight,720);
 assert.deepEqual(Array.from(config.description),Array.from(Buffer.from('0164001fffe100046764001f01000268ee','hex')));
 assert.deepEqual(f.chunks.map(c=>[c.type,c.timestamp,c.duration]),[['key',0,33333],['delta',33333,33333]]);
 assert.equal(player.stats.parserBytes,0);assert.equal(player.stats.receivedFrames,2);player.close();
});

test('canvas retains source dimensions, paints only latest frame and closes every output',async()=>{
 const f=fixture(),player=await configured(f);await player.push(key);const a=f.output(undefined,0),b=f.output(undefined,33333),c=f.output(undefined,66666);
 assert.equal(a.closed,1);assert.equal(b.closed,1);assert.equal(c.closed,0);assert.equal(f.timers.size,1);
 f.render();assert.equal(c.closed,1);assert.equal(f.draws.length,1);assert.equal(f.draws[0][0],c);
 assert.equal(f.canvas.width,1280);assert.equal(f.canvas.height,720);assert.equal(f.canvas.style.objectFit,'contain');
 assert.equal(f.frames[0].presentedFrames,1);assert.equal(player.stats.decodedFrames,3);assert.equal(player.stats.droppedFrames,2);player.close();
});

test('close cancels scheduled output and late decoder callbacks cannot paint or report errors',async()=>{
 const f=fixture(),player=await configured(f);await player.push(key);const decoder=f.decoders[0],a=f.output();player.close();player.close();
 assert.equal(a.closed,1);assert.equal(f.timers.size,0);const b=f.output(decoder);decoder.callbacks.error(new Error('late'));
 assert.equal(b.closed,1);f.render();assert.equal(f.draws.length,0);assert.equal(f.errors.length,0);assert.equal(player.stats.closed,true);player.push(key);assert.equal(f.chunks.length,1);
});

test('unsupported or rejected decoder configuration produces one terminal error and releases state',async()=>{
 for(const options of [{supported:false},{configureError:'unsupported codec'}]){
  const f=fixture(options),player=f.create();player.push(Buffer.concat([init,key]));await settle();
  assert.equal(f.errors.length,1);assert.match(f.errors[0].message,/support|codec/i);assert.equal(player.stats.closed,true);assert.equal(player.stats.parserBytes,0);assert.equal(f.chunks.length,0);
  player.push(key);assert.equal(f.errors.length,1);
 }
});

test('close while support check is pending cannot configure a late decoder',async()=>{
 const f=fixture(),player=f.create();let release;f.Decoder.isConfigSupported=()=>new Promise(resolve=>{release=resolve;});
 const pending=player.push(init);await settle();assert.equal(typeof release,'function');player.close();await pending;
 release({supported:true});await settle();assert.equal(f.decoders.length,0);assert.equal(f.errors.length,0);assert.equal(f.timers.size,0);
});

test('decode backlog applies backpressure and preserves dependent frames without a new IDR',async()=>{
 const f=fixture(),player=await configured(f);await player.push(key);const decoder=f.decoders[0];decoder.decodeQueueSize=8;
 let completed=false;const pending=player.push(delta).then(()=>{completed=true;});await settle();
 assert.equal(completed,false);assert.equal(decoder.state,'configured');assert.equal(player.stats.resets,0);assert.equal(player.stats.waitingForKeyframe,false);assert.equal(f.chunks.length,1);
 decoder.drain();await pending;assert.equal(f.chunks.length,2);assert.equal(f.chunks[1].type,'delta');assert.equal(player.stats.droppedEncodedFrames,0);assert.equal(f.decoders.length,1);player.close();
});

test('a coalesced 72-frame muxer burst survives delayed support and repeated decoder backpressure',async()=>{
 const f=fixture(),player=f.create();let release;f.Decoder.isConfigSupported=()=>new Promise(resolve=>{release=resolve;});
 f.Decoder.prototype.decode=function(chunk){this.decodeQueueSize++;f.chunks.push(chunk);};
 let completed=false;const pending=player.push(burst).then(()=>{completed=true;});await settle();
 assert.equal(f.chunks.length,0);assert(player.stats.parserBytes<4*1024*1024);assert.equal(player.stats.droppedEncodedFrames,0);
 release({supported:true});await settle();let drains=0;
 while(!completed&&drains<20){assert.equal(f.decoders.length,1);assert(f.decoders[0].decodeQueueSize<=8);f.decoders[0].drain();drains++;await settle();}
 assert(completed,'Burst did not drain within twenty dequeue events');await pending;assert(drains>=8);assert.equal(f.chunks.length,72);assert.equal(f.chunks.filter(c=>c.type==='key').length,1);
 assert.equal(player.stats.resets,0);assert.equal(player.stats.droppedEncodedFrames,0);assert.equal(player.stats.parserBytes,0);assert.equal(player.stats.pendingBytes,0);assert.equal(f.errors.length,0);player.close();
});

test('decoder capacity timeout produces one terminal fallback error instead of waiting for an IDR',async()=>{
 const f=fixture(),player=await configured(f);await player.push(key);const decoder=f.decoders[0];decoder.decodeQueueSize=8;
 const pending=player.push(delta);await settle();f.fireTimers(2000);await pending;
 assert.equal(player.stats.closed,true);assert.equal(f.errors.length,1);assert.match(f.errors[0].message,/stalled.*2 seconds/);assert.equal(decoder.listeners.get('dequeue').size,0);assert.equal(f.timers.size,0);
 decoder.drain();await player.push(key2);assert.equal(f.errors.length,1);assert.equal(f.chunks.length,1);
});

test('close releases capacity waits and queued pushes without errors or late decode',async()=>{
 const f=fixture(),player=await configured(f);await player.push(key);const decoder=f.decoders[0];decoder.decodeQueueSize=8;
 const pending=player.push(delta),queued=player.push(key2);await settle();player.close();await Promise.all([pending,queued]);
 assert.equal(f.chunks.length,1);assert.equal(f.errors.length,0);assert.equal(decoder.listeners.get('dequeue').size,0);assert.equal(player.stats.pendingBytes,0);assert.equal(f.timers.size,0);decoder.drain();assert.equal(f.chunks.length,1);
});

test('queued callers cannot retain more than four MiB while configuration is pending',async()=>{
 const f=fixture(),player=f.create();f.Decoder.isConfigSupported=()=>new Promise(()=>{});
 const pending=player.push(init);await settle();const queued=player.push(new Uint8Array(4*1024*1024));
 await player.push(new Uint8Array([1]));await Promise.all([pending,queued]);
 assert.equal(f.errors.length,1);assert.match(f.errors[0].message,/4 MiB/);assert.equal(player.stats.pendingBytes,0);assert.equal(player.stats.parserBytes,0);assert.equal(f.timers.size,0);
});

test('configuration timeout releases the input parser and invokes fallback once',async()=>{
 const f=fixture(),player=f.create();f.Decoder.isConfigSupported=()=>new Promise(()=>{});
 const pending=player.push(init);await settle();f.fireTimers(2000);await pending;
 assert.equal(f.errors.length,1);assert.match(f.errors[0].message,/configuration timed out/);assert.equal(player.stats.closed,true);assert.equal(player.stats.parserBytes,0);assert.equal(f.decoders.length,0);
});

test('tiny concurrent pushes have a bounded promise queue and empty inputs allocate no work',async()=>{
 const f=fixture(),player=f.create();f.Decoder.isConfigSupported=()=>new Promise(()=>{});
 const pending=[player.push(init)];await settle();
 for(let i=0;i<200;i++)await player.push(new Uint8Array(0));
 assert.equal(player.stats.pendingFrames,0);
 for(let i=0;i<129;i++)pending.push(player.push(new Uint8Array([0])));
 await Promise.all(pending);assert.equal(f.errors.length,1);assert.match(f.errors[0].message,/unawaited/);assert.equal(player.stats.pendingBytes,0);assert.equal(f.timers.size,0);
});

test('invalid box sizes and unexpected MP4 layouts fail before unbounded allocation',async()=>{
 const invalid=[];
 for(const size of [0,1,7,4*1024*1024+1]){const b=Buffer.alloc(8);b.writeUInt32BE(size);b.write('moov',4);invalid.push(b);}
 const missingInit=key;invalid.push(missingInit);
 for(const bytes of invalid){const f=fixture(),player=f.create();player.push(bytes);await settle();assert.equal(f.errors.length,1);assert.equal(player.stats.closed,true);assert.equal(player.stats.parserBytes,0);}
});

test('sample offset, size, NAL length, duplicate init and dimension contradictions are rejected',async()=>{
 const badOffset=Buffer.from(key);const trunAt=badOffset.indexOf(Buffer.from('trun'));badOffset.writeUInt32BE(1,trunAt+12);
 const badSize=Buffer.from(key);badSize.writeUInt32BE(999,trunAt+20);
 const badNal=Buffer.from(key);const mdatAt=badNal.indexOf(Buffer.from('mdat'));badNal.writeUInt32BE(999,mdatAt+4);
 for(const bytes of [badOffset,badSize,badNal,init]){const f=fixture(),player=await configured(f);await player.push(bytes);assert.equal(f.errors.length,1);assert.equal(player.stats.closed,true);}
 const f=fixture(),player=f.create({width:960,height:720});player.push(init);await settle();assert.equal(f.errors.length,1);assert.match(f.errors[0].message,/dimension/i);
});

test('decoder errors and drawing failures close all resources exactly once',async()=>{
 const f=fixture(),player=await configured(f);await player.push(key);const pending=f.output();f.decoders[0].callbacks.error(new Error('hardware decoder failed'));
 assert.equal(pending.closed,1);assert.equal(f.errors.length,1);assert.equal(player.stats.closed,true);f.decoders[0].callbacks.error(new Error('duplicate'));assert.equal(f.errors.length,1);
 const g=fixture(),other=await configured(g);await other.push(key);const frame=g.output();g.canvas.getContext('2d').drawImage=()=>{throw new Error('paint failed');};g.render();assert.equal(frame.closed,1);assert.equal(g.errors.length,1);assert.equal(other.stats.closed,true);
});
