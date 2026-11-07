import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../web/client.js',import.meta.url),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
class Events{
 constructor(){this.events=new Map();}
 addEventListener(type,fn){const list=this.events.get(type)||[];list.push(fn);this.events.set(type,list);}
 removeEventListener(type,fn){this.events.set(type,(this.events.get(type)||[]).filter(f=>f!==fn));}
 emit(type,...args){for(const fn of [...(this.events.get(type)||[])])fn(...args);}
}
function fixture({muted=false,audioError='',session='first',autoOpen=true,active=true,audioOutput='browser'}={}){
 const media=[],streams=[],videoCallbacks=[],touches=[],requests=[],urls=new Map(),elements=new Map();
 let service={active,identityReady:true,session:active?session:null,sessionSeconds:1,error:'',codec:'avc1.64001f',videoConnected:active,audioOutput};
 let failAudio=audioError,failEnable='',deferTouch=null;
 const classSet=new Set(),body={classList:{add(v){classSet.add(v);},remove(v){classSet.delete(v);}}};
 function element(){return {textContent:'',title:'',disabled:false,setAttribute(k,v){this[k]=v;}};}
 const video={...element(),paused:true,currentTime:0,buffered:{length:0},pause(){this.paused=true;},load(){},removeAttribute(){this.url=null;},play(){this.paused=false;return Promise.resolve();},requestVideoFrameCallback(fn){videoCallbacks.push(fn);},getBoundingClientRect(){return {left:0,top:0,width:1280,height:720};},setPointerCapture(){}};
 Object.defineProperty(video,'src',{set(value){this.url=value;if(autoOpen)queueMicrotask(()=>urls.get(value)?.emit('sourceopen'));},get(){return this.url;}});
 elements.set('video',video);for(const id of ['status','start','stop','sound','audioOutput','full','exitFull'])elements.set('#'+id,element());
 class SourceBuffer extends Events{constructor(){super();this.updating=false;this.buffered={length:0};this.appended=[];}appendBuffer(data){this.appended.push(data);}remove(){}}
 class Media extends Events{constructor(){super();media.push(this);}addSourceBuffer(){this.buffer=new SourceBuffer();return this.buffer;}}
 const audioState={enabled:true,muted,contextState:'running',connectionState:'idle',error:audioError};
 const audioCalls={enable:0,stop:0,mute:0,connect:[]};
 const audio={get stats(){return {...audioState};},enable(){audioCalls.enable++;if(failEnable){audioState.error=failEnable;audioState.enabled=false;audioState.contextState='suspended';return Promise.reject(new Error(failEnable));}audioState.enabled=true;audioState.contextState='running';audioState.error='';return Promise.resolve(true);},stop(){audioCalls.stop++;audioState.connectionState='idle';},muteToggle(){audioCalls.mute++;audioState.muted=!audioState.muted;return audioState.muted;},connect(s){audioCalls.connect.push(s);if(!audioState.enabled){audioState.connectionState='awaiting-gesture';return Promise.resolve(false);}audioState.error=failAudio;audioState.connectionState=failAudio?'disconnected':'connected';return Promise.resolve(!failAudio);}};
 function stream(){const waiting=[],chunks=[];const s={cancelled:false,read(){if(chunks.length)return Promise.resolve(chunks.shift());return new Promise(r=>waiting.push(r));},push(value){const item={done:false,value};waiting.length?waiting.shift()(item):chunks.push(item);},cancel(){s.cancelled=true;return Promise.resolve();}};streams.push(s);return s;}
 async function fetch(url,options={}){
  if(url==='/api/status')return {ok:true,json:async()=>({...service})};
  if(url==='/video'){const s=stream();s.session=options.headers['X-CarDash-Session'];return {ok:true,body:{getReader(){return s;}}};}
  const value=options.body?JSON.parse(options.body):{};
  requests.push({url,value});
  if(url==='/api/start')service={...service,active:true,session:'started',videoConnected:true};
  if(url==='/api/stop')service={...service,active:false,session:null,videoConnected:false};
  if(url==='/api/audio_output')service={...service,audioOutput:value.mode};
  if(url==='/api/touch'){touches.push(value);if(deferTouch){const current=deferTouch;deferTouch=null;return current;}}
  return {ok:true,json:async()=>({...service})};
 }
 const globals={document:{querySelector(s){return elements.get(s);},body},MediaSource:Media,URL:{createObjectURL(m){const u='blob:'+urls.size;urls.set(u,m);return u;},revokeObjectURL(){}},AbortController,DOMException,CarDashAudio:audio,fetch,setInterval(){},performance:{now:()=>100},console};
 globals.window=globals;globals.addEventListener=()=>{};
 const context=vm.createContext(globals);vm.runInContext(code,context);
 return {elements,media,streams,videoCallbacks,audioState,audioCalls,touches,requests,classSet,
  run(s){return vm.runInContext(s,context);},set service(v){service={...service,...v};},set failAudio(v){failAudio=v;},set failEnable(v){failEnable=v;},deferNextTouch(p){deferTouch=p;}};
}

test('failed sound displays its real error; Retry reconnects without changing explicit mute',async()=>{
 for(const muted of [false,true]){
  const f=fixture({muted,audioError:'Native audio connection failed (503)'});await settle();
  assert.match(f.elements.get('#status').textContent,/503/);assert.equal(f.elements.get('#sound').textContent,'Retry sound');
  f.failAudio='';const enabledBefore=f.audioCalls.enable;await f.elements.get('#sound').onclick();await settle();
  assert.equal(f.audioCalls.enable,enabledBefore+1);assert.equal(f.audioCalls.mute,0);assert.equal(f.audioState.muted,muted);
  assert.equal(f.elements.get('#sound').textContent,muted?'Unmute':'Mute');assert.doesNotMatch(f.elements.get('#status').textContent,/503/);
  f.run('end()');
 }
});

test('audio activation error remains visible while native video starts',async()=>{
 const f=fixture({active:false});await settle();f.failEnable='Browser audio permission denied';
 await f.elements.get('#start').onclick();await settle();
 assert.match(f.elements.get('#status').textContent,/Browser audio permission denied/);
 assert(f.classSet.has('live'));assert.equal(f.run('closed'),false);assert.equal(f.streams[0].session,'started');f.run('end()');
});

test('late video bytes, decoder errors and frame callbacks cannot end replacement session',async()=>{
 const f=fixture({});await settle();const old=f.streams[0],oldBuffer=f.media[0].buffer,oldFrame=f.videoCallbacks[0];
 f.service={session:'replacement'};await f.run('poll()');await settle();
 const stops=f.audioCalls.stop;assert.equal(f.streams[1].session,'replacement');assert(old.cancelled);
 old.push(new Uint8Array([1,2,3]));oldBuffer.emit('error');oldFrame(0,{presentedFrames:999,mediaTime:999});await settle();
 assert.equal(f.run('inputSession'),'replacement');assert.equal(f.run('closed'),false);assert.equal(f.audioCalls.stop,stops);
 assert.equal(f.run('nativeStats.decodedFrames'),0);assert.equal(f.media[1].buffer.appended.length,0);f.run('end()');
});

test('queued old input and rejected old requests cannot alter a replacement session',async()=>{
 const f=fixture({});await settle();let release;
 f.deferNextTouch(new Promise(r=>{release=r;}));f.run('send(.5,.5,true);send(.5,.5,false)');await settle();assert.equal(f.touches.length,1);
 f.service={session:'replacement'};await f.run('poll()');await settle();const stops=f.audioCalls.stop;
 release({ok:false,json:async()=>({error:'Stale native session'})});await settle();assert.equal(f.touches.length,1);
 assert.equal(f.run('inputSession'),'replacement');assert.equal(f.run('closed'),false);assert.equal(f.audioCalls.stop,stops);
 f.run('send(.3,.3,true)');await settle();assert.equal(f.touches.length,2);assert.equal(f.touches[1].session,'replacement');f.run('end()');
});

test('an old delayed sourceopen cannot attach its video to the new session',async()=>{
 const f=fixture({autoOpen:false});await settle();const old=f.media[0];
 f.service={session:'replacement'};await f.run('poll()');await settle();
 old.emit('sourceopen');f.media[1].emit('sourceopen');await settle();
 assert.equal(f.streams.length,1);assert.equal(f.streams[0].session,'replacement');assert.equal(f.run('closed'),false);f.run('end()');
});

test('video error reason, time and count survive same-session reconnect and ignore stale errors',async()=>{
 const f=fixture({});await settle();const first=f.media[0].buffer;
 first.emit('error');await settle();
 const failure=f.run('nativeStats.lastVideoErrorTime');
 assert.equal(f.run('nativeStats.videoErrors'),1);assert.match(f.run('nativeStats.lastVideoError'),/decoder/);assert(Number.isFinite(Date.parse(failure)));
 assert.equal(f.run('nativeStats.lastVideoErrorDetails.stage'),'source-buffer-error');assert.equal(f.run('closed'),true);
 await f.run('poll()');await settle();
 assert.equal(f.run('closed'),false);assert.equal(f.run('nativeStats.videoConnections'),2);assert.equal(f.run('nativeStats.lastVideoErrorTime'),failure);
 first.emit('error');assert.equal(f.run('nativeStats.videoErrors'),1);
 f.media[1].buffer.appendBuffer=()=>{throw new Error('QuotaExceededError: source buffer full');};
 f.streams[1].push(new Uint8Array([7]));await settle();
 assert.equal(f.run('nativeStats.videoErrors'),2);assert.equal(f.run('nativeStats.lastVideoErrorDetails.stage'),'append');assert.match(f.run('nativeStats.lastVideoError'),/QuotaExceeded/);
 f.run('end()');
});

test('queued updateend does not trim a source buffer while another append is updating',async()=>{
 const f=fixture({});await settle();f.service={videoKeyframes:[0,5*90000],videoTimelineTicks:12*90000};await f.run('poll()');await settle();const source=f.media[0].buffer,video=f.elements.get('video');let removals=0;
 source.buffered={length:1,start:()=>0,end:()=>12};video.currentTime=10;
 source.remove=()=>{removals++;if(source.updating)throw new Error('SourceBuffer is still processing appendBuffer or remove');};
 source.updating=true;source.emit('updateend');
 assert.equal(removals,0);assert.equal(f.run('nativeStats.videoErrors'),0);assert.equal(f.run('closed'),false);
 source.updating=false;source.emit('updateend');
 assert.equal(removals,1);assert.equal(f.run('nativeStats.trims'),1);assert.equal(f.run('nativeStats.videoErrors'),0);
 f.run('end()');
});

test('an active request with zero native frames is not labelled connected',async()=>{
 const f=fixture({active:false});await settle();
 f.service={active:true,session:'pending',codec:null,videoConnected:false,nativeFrames:0,native:{present:false,authenticated:false,activated:false}};
 await f.run('poll()');await settle();
 assert.match(f.elements.get('#status').textContent,/starting native session/i);
 assert.doesNotMatch(f.elements.get('#status').textContent,/connected/);
 f.service={native:{present:true,authenticated:true,activated:true}};
 await f.run('poll()');await settle();
 assert.match(f.elements.get('#status').textContent,/waiting for native video/i);
 f.run('end()');
});

test('stretched video maps edge and center touches across wide and tall viewports',async()=>{
 const f=fixture();await settle();const video=f.elements.get('video');
 for(const [width,height] of [[1920,700],[1280,720],[900,950]]){
  video.getBoundingClientRect=()=>({left:15,top:55,width,height});
  for(const [x,y] of [[0,0],[1,1],[.052,.92],[.5,.5]]){
   const p=f.run(`coordinate({clientX:${15+x*width},clientY:${55+y*height}})`);
   assert(p,`valid edge rejected in ${width}x${height}`);
   assert(Math.abs(p.x-x)<1e-8);assert(Math.abs(p.y-y)<1e-8);
  }
  assert.equal(f.run('coordinate({clientX:14,clientY:55})'),null);
 }
 video.getBoundingClientRect=()=>({left:0,top:0,width:0,height:0});
 assert.equal(f.run('coordinate({clientX:0,clientY:0})'),null);f.run('end()');
});

test('phone output never enables or connects browser audio on Start or native touch',async()=>{
 const f=fixture({active:false,audioOutput:'phone'});await settle();
 await f.elements.get('#start').onclick();await settle();
 f.elements.get('video').onpointerdown({pointerId:1,clientX:100,clientY:100});await settle();
 assert.equal(f.audioCalls.enable,0);assert.equal(f.audioCalls.connect.length,0);
 assert.equal(f.elements.get('#sound').hidden,true);
 assert.match(f.elements.get('#status').textContent,/phone.*Bluetooth/i);f.run('end()');
});

test('changing audio output performs stop-configure-start and keeps phone choice on reconnect',async()=>{
 const f=fixture({audioOutput:'browser'});await settle();
 f.elements.get('#audioOutput').value='phone';await f.elements.get('#audioOutput').onchange();await settle();
 assert.deepEqual(f.requests.filter(r=>['/api/stop','/api/audio_output','/api/start'].includes(r.url)).map(r=>r.url),['/api/stop','/api/audio_output','/api/start']);
 assert.equal(f.requests.find(r=>r.url==='/api/stop').value.session,'first');
 assert.equal(f.elements.get('#audioOutput').value,'phone');
 const connections=f.audioCalls.connect.length;
 f.service={session:'new-session'};await f.run('poll()');await settle();
 assert.equal(f.audioCalls.connect.length,connections);f.run('end()');
});

for(const active of [false,true])test(`Start and Stop cannot interrupt a pending audio change (${active?'active':'stopped'} session)`,async()=>{
 const f=fixture({active,audioOutput:'browser'});await settle();
 const heldURL=active?'/api/stop':'/api/audio_output';
 f.run(`let releaseAudioChange,heldAudioChange=false;const originalFetch=fetch;
  fetch=(url,options)=>{if(url===${JSON.stringify(heldURL)}&&!heldAudioChange){heldAudioChange=true;return new Promise(resolve=>{releaseAudioChange=()=>resolve(originalFetch(url,options));});}return originalFetch(url,options);};`);
 f.elements.get('#audioOutput').value='phone';
 const pending=f.elements.get('#audioOutput').onchange();await settle();
 try{
  const epoch=f.run('commandEpoch'),requests=f.requests.length;
  await f.elements.get('#start').onclick();await f.elements.get('#stop').onclick();
  assert.equal(f.run('commandEpoch'),epoch,'A competing button cancelled the output-change transaction');
  assert.equal(f.requests.length,requests,'A competing native command was sent');
  assert.equal(f.elements.get('#start').disabled,true);assert.equal(f.elements.get('#stop').disabled,true);
 }finally{f.run('releaseAudioChange()');await pending;await settle();}
 assert.equal(f.elements.get('#audioOutput').value,'phone');
 assert.deepEqual(f.requests.filter(r=>['/api/stop','/api/audio_output','/api/start'].includes(r.url)).map(r=>r.url),active?['/api/stop','/api/audio_output','/api/start']:['/api/audio_output']);
 f.run('end()');
});

test('a long GOP keeps its only decode chain instead of trimming through the playhead',async()=>{
 const f=fixture();await settle();
 f.service={videoKeyframes:[0],videoTimelineTicks:52*90000};await f.run('poll()');await settle();
 const source=f.media[0].buffer,video=f.elements.get('video');let removals=0;
 source.buffered={length:1,start:()=>0,end:()=>52};video.currentTime=51;source.remove=()=>{removals++;};
 source.emit('updateend');
 assert.equal(removals,0,'Removing inside the only GOP destroys current decoding');
 assert.equal(f.run('closed'),false);f.run('end()');
});

test('buffer trimming preserves a confirmed IDR before the playhead with a one-tick margin',async()=>{
 const f=fixture();await settle();
 f.service={videoKeyframes:[0,30*90000,60*90000],videoTimelineTicks:61*90000};await f.run('poll()');await settle();
 const source=f.media[0].buffer,video=f.elements.get('video'),removals=[];
 source.buffered={length:1,start:()=>0,end:()=>61};video.currentTime=59;source.remove=(start,end)=>removals.push([start,end]);
 source.emit('updateend');
 assert.deepEqual(removals,[[0,(30*90000-1)/90000]]);
 assert.equal(f.run('nativeStats.trims'),1);f.run('end()');
});

test('retained history without a safe random-access point fails boundedly after ninety seconds',async()=>{
 const f=fixture();await settle();
 f.service={videoKeyframes:[0],videoTimelineTicks:91*90000};await f.run('poll()');await settle();
 const source=f.media[0].buffer,video=f.elements.get('video');let removals=0;
 source.buffered={length:1,start:()=>0,end:()=>91};video.currentTime=90;source.remove=()=>{removals++;};
 source.emit('updateend');
 assert.equal(removals,0);assert.equal(f.run('closed'),true);
 assert.match(f.run('nativeStats.lastVideoError'),/90 seconds|random.access/i);
 f.run('end()');
});
