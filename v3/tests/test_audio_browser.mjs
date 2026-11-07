import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const code = await readFile(new URL('../web/audio.js', import.meta.url), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

function frame({rate=48000, channels=2, lane=0, flags=2, sequence=1, samples=[32767,-32768,0,100]}={}) {
  const data=Buffer.alloc(4+12+samples.length*2);
  data.writeUInt32BE(data.length-4,0);data.writeUInt32BE(rate,4);
  data[8]=channels;data[9]=lane;data.writeUInt16BE(flags,10);data.writeUInt32BE(sequence,12);
  samples.forEach((value,i)=>data.writeInt16LE(value,16+2*i));return data;
}
function fixture() {
  const instances=[], requests=[];
  class Context {
    constructor() { this.currentTime=0;this.state='suspended';this.destination={};this.sources=[];this.gains=[];instances.push(this); }
    resume() { this.state='running';return Promise.resolve(); }
    createGain() { const gain={gain:{value:1,values:[],setTargetAtTime(v){this.value=v;this.values.push(v);}},connect(){},disconnect(){}};this.gains.push(gain);return gain; }
    createAnalyser() { return {fftSize:256,connect(){},getFloatTimeDomainData(a){a.fill(0);}}; }
    createBuffer(channels,length,sampleRate) { const data=Array.from({length:channels},()=>new Float32Array(length));return {length,sampleRate,data,getChannelData(c){return data[c];}}; }
    createBufferSource() { const s={connect(){},disconnect(){this.disconnected=true;},start(at){this.at=at;},stop(){this.stopped=true;}};this.sources.push(s);return s; }
  }
  function fetch(url,options) {
    const chunks=[], waiting=[];
    const reader={
      read(){ if(chunks.length)return Promise.resolve(chunks.shift());return new Promise(resolve=>waiting.push(resolve)); },
      cancel(){while(waiting.length)waiting.shift()({done:true});return Promise.resolve();}
    };
    const request={url,options,push(value){const item={value:new Uint8Array(value),done:false};waiting.length?waiting.shift()(item):chunks.push(item);},end(){waiting.length?waiting.shift()({done:true}):chunks.push({done:true});}};
    requests.push(request);
    // Deliberately do not resolve reads on abort: tests can deliver a late old chunk.
    return Promise.resolve({ok:true,status:200,body:{getReader(){return reader;}}});
  }
  const window={AudioContext:Context,addEventListener(){}};
  vm.runInNewContext(code,{window,fetch,AbortController,Uint8Array,Float32Array,DataView,Map,Set,Math,Promise,Error});
  return {api:window.CarDashAudio,instances,requests};
}

test('audio waits for gesture, parses fragmented PCM and schedules correct signed channels',async()=>{
  const {api,instances,requests}=fixture();
  assert.equal(await api.connect('first'),false);assert.equal(instances.length,0);assert.equal(requests.length,0);
  const enabled=api.enable();assert.equal(instances.length,1);await enabled;await api.connect('first');
  assert.equal(requests.length,1);assert.equal(requests[0].options.headers['X-CarDash-Session'],'first');
  const data=frame();for(let at=0;at<data.length;at++)requests[0].push(data.subarray(at,at+1));await settle();
  const source=instances[0].sources[0];assert(source);assert.equal(source.buffer.sampleRate,48000);
  assert.deepEqual(Array.from(source.buffer.data[0]),[32767/32768,0]);
  assert.deepEqual(Array.from(source.buffer.data[1]),[-1,100/32768]);
  assert.equal(api.stats.sampleFrames,2);assert.equal(api.stats.nonzeroSamples,3);assert.equal(api.stats.parserBytes,0);
  api.stop();assert(source.stopped);assert.equal(api.stats.sources,0);
});

test('media duck flags change only the media lane and restore its gain',async()=>{
  const {api,instances,requests}=fixture();await api.enable();await api.connect('first');
  requests[0].push(frame({flags:6}));await settle();assert.equal(instances[0].gains[1].gain.value,.25);
  requests[0].push(frame({flags:2,sequence:2}));await settle();assert.equal(instances[0].gains[1].gain.value,1);
  requests[0].push(frame({lane:1,flags:4}));await settle();assert.equal(instances[0].gains[2].gain.value,1);
  assert.equal(api.muteToggle(),true);assert.equal(instances[0].gains[0].gain.value,0);
  assert.equal(api.muteToggle(),false);assert.equal(instances[0].gains[0].gain.value,.6);api.stop();
});

test('backlog is bounded and duplicate/out-of-order packets are not played',async()=>{
  const {api,instances,requests}=fixture();await api.enable();await api.connect('first');
  const samples=Array.from({length:1920},(_,i)=>i&1?100:-100);
  for(let sequence=1;sequence<=100;sequence++)requests[0].push(frame({sequence,samples}));
  for(let i=0;i<30;i++)await settle();
  assert(api.stats.scheduledAhead<=.5+1e-9);assert(api.stats.sources<=64);assert(api.stats.resets>1);
  const count=instances[0].sources.length;
  requests[0].push(frame({sequence:100,samples}));requests[0].push(frame({sequence:99,samples}));await settle();
  assert.equal(instances[0].sources.length,count);assert(api.stats.droppedFrames>=2);api.stop();
});

test('session replacement ignores late audio and disposes old scheduled nodes',async()=>{
  const {api,instances,requests}=fixture();await api.enable();await api.connect('first');
  requests[0].push(frame());await settle();const old=instances[0].sources[0];
  await api.connect('second');assert(old.stopped);assert(requests[0].options.signal.aborted);
  requests[0].push(frame({sequence:2}));requests[1].push(frame({sequence:55}));await settle();
  assert.equal(api.stats.receivedFrames,1);assert.equal(api.stats.connections,1);assert.equal(api.stats.connectionState,'connected');api.stop();
});

test('malformed size/flags/truncated PCM fail closed without retained nodes',async()=>{
  for(const kind of ['size','flags','channels','truncated']) {
    const {api,requests}=fixture();await api.enable();await api.connect('first');
    let data=frame();
    if(kind==='size')data=Buffer.from([0x7f,0xff,0xff,0xff]);
    if(kind==='flags')data.writeUInt16BE(8,10);
    if(kind==='channels')data[8]=3;
    if(kind==='truncated')data=data.subarray(0,data.length-1);
    requests[0].push(data);if(kind==='truncated')requests[0].end();await settle();
    assert(api.stats.error,kind);assert.equal(api.stats.sources,0);assert.equal(api.stats.parserBytes,0);api.stop();
  }
});

test('sequence wrap, explicit lane reset and context suspension discard stale sound',async()=>{
  const {api,instances,requests}=fixture();await api.enable();await api.connect('first');
  requests[0].push(frame({sequence:0xffffffff}));requests[0].push(frame({sequence:0}));await settle();
  assert.equal(api.stats.receivedFrames,2);assert.equal(api.stats.droppedFrames,0);
  requests[0].push(frame({sequence:0,flags:3}));await settle();assert.equal(api.stats.droppedFrames,0);
  instances[0].state='suspended';requests[0].push(frame({sequence:1}));await settle();
  assert.equal(api.stats.sources,0);assert.equal(api.stats.droppedFrames,1);
  await api.enable();requests[0].push(frame({sequence:2}));await settle();assert.equal(api.stats.sources,1);api.stop();
});
