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
function fixture({muted=false,audioError='',session='first',autoOpen=true,active=true,audioOutput='browser',canvasMode=null,hosted=false}={}){
 const media=[],streams=[],videoCallbacks=[],touches=[],requests=[],fetchCalls=[],adapterCalls=[],connectionCalls=[],events=new Map(),urls=new Map(),elements=new Map();
 let service={active,identityReady:true,session:active?session:null,sessionSeconds:1,error:'',codec:'avc1.64001f',videoConnected:active,audioOutput};
 const renderers=[],canvases=[],images=[],bitmaps=[];let bitmapDeferred=null;
 let failAudio=audioError,failEnable='',deferTouch=null;
 const classSet=new Set(),body={classList:{add(v){classSet.add(v);},remove(v){classSet.delete(v);}}};
 function element(){return {textContent:'',title:'',disabled:false,setAttribute(k,v){this[k]=v;}};}
 const video={...element(),style:{},paused:true,currentTime:0,buffered:{length:0},pause(){this.paused=true;},load(){},removeAttribute(){this.url=null;},play(){this.paused=false;return Promise.resolve();},requestVideoFrameCallback(fn){videoCallbacks.push(fn);},getBoundingClientRect(){return {left:0,top:0,width:1280,height:720};},setPointerCapture(){}};
 Object.defineProperty(video,'src',{set(value){this.url=value;if(autoOpen)queueMicrotask(()=>urls.get(value)?.emit('sourceopen'));},get(){return this.url;}});
 function makeCanvas(){const c={hidden:true,width:0,height:0,draws:0,setPointerCapture(){},cloneNode(){return makeCanvas();},replaceWith(n){elements.set('#canvas',n);},getContext(){return {drawImage(){c.draws++;}}}};canvases.push(c);return c;}
 if(canvasMode)elements.set('#canvas',makeCanvas());
 elements.set('video',video);for(const id of ['status','start','stop','sound','audioOutput','full','exitFull','fitViewport'])elements.set('#'+id,element());
 class SourceBuffer extends Events{constructor(){super();this.updating=false;this.buffered={length:0};this.appended=[];}appendBuffer(data){this.appended.push(data);}remove(){}}
 class Media extends Events{constructor(){super();media.push(this);}addSourceBuffer(){this.buffer=new SourceBuffer();return this.buffer;}}
 const audioState={enabled:true,muted,contextState:'running',connectionState:'idle',error:audioError};
 const audioCalls={enable:0,stop:0,mute:0,connect:[]};
 const audio={get stats(){return {...audioState};},enable(){audioCalls.enable++;if(failEnable){audioState.error=failEnable;audioState.enabled=false;audioState.contextState='suspended';return Promise.reject(new Error(failEnable));}audioState.enabled=true;audioState.contextState='running';audioState.error='';return Promise.resolve(true);},stop(){audioCalls.stop++;audioState.connectionState='idle';},muteToggle(){audioCalls.mute++;audioState.muted=!audioState.muted;return audioState.muted;},connect(s){audioCalls.connect.push(s);if(!audioState.enabled){audioState.connectionState='awaiting-gesture';return Promise.resolve(false);}audioState.error=failAudio;audioState.connectionState=failAudio?'disconnected':'connected';return Promise.resolve(!failAudio);}};
 function stream(){const waiting=[],chunks=[];const s={cancelled:false,read(){if(chunks.length)return Promise.resolve(chunks.shift());return new Promise(r=>waiting.push(r));},push(value){const item={done:false,value};waiting.length?waiting.shift()(item):chunks.push(item);},finish(){const item={done:true};waiting.length?waiting.shift()(item):chunks.push(item);},cancel(){s.cancelled=true;return Promise.resolve();}};streams.push(s);return s;}
 async function fetch(url,options={}){
  fetchCalls.push({url,options});
  if(url==='/api/status')return {ok:true,json:async()=>({...service})};
  if(url==='/video'){const s=stream();s.session=options.headers['X-CarDash-Session'];return {ok:true,body:{getReader(){return s;}}};}
  if(url==='/image')return new Promise((resolve,reject)=>{images.push({resolve,options});options.signal?.addEventListener('abort',()=>reject(new DOMException('Cancelled','AbortError')),{once:true});});
  const value=options.body?JSON.parse(options.body):{};
  requests.push({url,value});
  if(url==='/api/start')service={...service,active:true,session:'started',videoConnected:true,requestedViewport:value.viewport};
  if(url==='/api/resize')service={...service,session:'resized',requestedViewport:value.viewport};
  if(url==='/api/stop')service={...service,active:false,session:null,videoConnected:false};
  if(url==='/api/audio_output')service={...service,audioOutput:value.mode};
  if(url==='/api/touch'){touches.push(value);if(deferTouch){const current=deferTouch;deferTouch=null;return current;}}
  return {ok:true,json:async()=>({...service})};
 }
 const globals={document:{querySelector(s){return elements.get(s);},body},MediaSource:Media,URL:{createObjectURL(m){const u='blob:'+urls.size;urls.set(u,m);return u;},revokeObjectURL(){}},AbortController,DOMException,CarDashAudio:audio,fetch,setInterval(){},setTimeout(){return 1;},clearTimeout(){},performance:{now:()=>100},console};
 if(canvasMode){
  globals.Blob=Blob;globals.createImageBitmap=async()=>{if(bitmapDeferred){const p=bitmapDeferred;bitmapDeferred=null;return p;}const b={width:1280,height:720,closed:0,close(){this.closed++;}};bitmaps.push(b);return b;};
  globals.CarDashCanvas={available:()=>canvasMode==='webcodecs',create(options){const r={options,closed:0,pushed:[],stats:{},async push(b){this.pushed.push(b);},close(){this.closed++;}};renderers.push(r);return r;}};
 }
 if(hosted){for(const id of ['connectionPanel','endpoint','connect','connectionStatus','buildLabel'])elements.set('#'+id,element());let ready=false;globals.CarDashTransport={get diagnostics(){return {mode:'hosted',endpoint:'http://100.99.10.2:8890/',ready,lastError:''};},connect(endpoint){connectionCalls.push(endpoint);ready=true;return Promise.resolve(true);},disconnect(){ready=false;},fetch(...args){adapterCalls.push(args[0]);return globals.fetch(...args);}};}
 globals.window=globals;globals.addEventListener=(name,fn)=>events.set(name,fn);
 const context=vm.createContext(globals);vm.runInContext(code,context);
 return {elements,media,streams,videoCallbacks,audioState,audioCalls,touches,requests,fetchCalls,adapterCalls,connectionCalls,events,classSet,renderers,canvases,images,bitmaps,
  deferBitmap(p){bitmapDeferred=p;},
  imageReply(index,{length=3,data=new Uint8Array([1,2,3]),sequence=1}={}){let sent=false;images[index].resolve({ok:true,headers:{get(k){return {'Content-Type':'image/jpeg','Content-Length':String(length),'X-CarDash-Frame':String(sequence),'X-CarDash-Time':'1000000'}[k]||null;}},body:{getReader(){return {async read(){if(sent)return {done:true};sent=true;return {value:data,done:false};},async cancel(){}};}}});},
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

test('native aspect-matched video maps edge and center touches across wide and tall viewports',async()=>{
 const f=fixture();await settle();const video=f.elements.get('video');
 for(const [width,height] of [[1920,700],[1280,720],[900,950]]){
  video.getBoundingClientRect=()=>({left:15,top:55,width,height});video.videoWidth=width;video.videoHeight=height;
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

test('native Start advertises the actual content viewport, including tall Tesla screens',async()=>{
 const f=fixture({active:false,audioOutput:'phone'});await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:75,width:773,height:601});
 await f.elements.get('#start').onclick();await settle();
 assert.deepEqual(f.requests.find(r=>r.url==='/api/start').value.viewport,{width:773,height:601});f.run('end()');
});

test('touch mapping preserves native aspect and rejects letterbox space during resize',async()=>{
 const f=fixture({});await settle();const v=f.elements.get('video');
 v.getBoundingClientRect=()=>({left:0,top:55,width:800,height:600});v.videoWidth=1280;v.videoHeight=720;
 assert.equal(f.run('coordinate({clientX:400,clientY:56})'),null);
 const center=f.run('coordinate({clientX:400,clientY:355})');assert.equal(center.x,.5);assert.equal(center.y,.5);
 const edge=f.run('coordinate({clientX:800,clientY:580})');assert.equal(edge.x,1);assert.equal(edge.y,1);f.run('end()');
});

test('owned viewport changes use one generation-checked native resize and preserve audio',async()=>{
 const f=fixture({active:false,audioOutput:'phone'});await settle();await f.elements.get('#start').onclick();await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:773,height:601});
 await f.run('reconcileLayout()');await settle();
 const resizes=f.requests.filter(r=>r.url==='/api/resize');assert.equal(resizes.length,1);
 assert.equal(resizes[0].value.session,'started');assert.deepEqual(resizes[0].value.viewport,{width:773,height:601});
 assert.equal(f.run('inputSession'),'resized');assert.equal(f.elements.get('#audioOutput').value,'phone');
 await f.run('reconcileLayout()');assert.equal(f.requests.filter(r=>r.url==='/api/resize').length,1);f.run('end()');
});

test('a joining observer does not resize another browser session',async()=>{
 const f=fixture({});await settle();await f.run('reconcileLayout()');
 assert.equal(f.requests.filter(r=>r.url==='/api/resize').length,0);f.run('end()');
});

test('an acknowledged native-geometry no-op does not repeat resize or reconnect',async()=>{
 const f=fixture({active:false,audioOutput:'phone'});await settle();await f.elements.get('#start').onclick();await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:640,height:360});
 f.run(`let noops=0;const oldFetch=fetch;fetch=(url,options)=>{if(url==='/api/resize'){noops++;return oldFetch('/api/status');}return oldFetch(url,options);};`);
 await f.run('reconcileLayout()');await settle();const connections=f.run('nativeStats.videoConnections');
 await f.run('reconcileLayout()');await settle();
 assert.equal(f.run('noops'),1);assert.equal(f.run('nativeStats.videoConnections'),connections);
 assert.deepEqual(JSON.parse(f.run('JSON.stringify(layoutViewport)')),{width:640,height:360});f.run('end()');
});

test('native resize error survives the recovery status poll and clears on explicit Start',async()=>{
 const f=fixture({active:false,audioOutput:'phone'});await settle();await f.elements.get('#start').onclick();await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:773,height:601});
 f.run(`const oldFetch=fetch;fetch=(url,options)=>url==='/api/resize'?Promise.resolve({ok:false,json:async()=>({error:'Native resize unavailable'})}):oldFetch(url,options);`);
 await f.run('reconcileLayout()');await settle();await f.run('poll()');
 assert.match(f.elements.get('#status').textContent,/Native resize unavailable/);assert.equal(f.run('layoutSession'),null);
 await f.elements.get('#stop').onclick();await settle();await f.elements.get('#start').onclick();await settle();
 assert.doesNotMatch(f.elements.get('#status').textContent,/Native resize unavailable/);f.run('end()');
});

test('actual window resize during audio restart is reconciled after the transaction',async()=>{
 const f=fixture({audioOutput:'browser'});await settle();
 f.run(`let releaseStart,scheduled=[];setTimeout=(fn,ms)=>{if(ms===1200)scheduled.push(fn);return scheduled.length;};clearTimeout=()=>{};
 const oldFetch=fetch;fetch=(url,options)=>url==='/api/start'?new Promise(resolve=>{releaseStart=()=>resolve(oldFetch(url,options));}):oldFetch(url,options);`);
 f.elements.get('#audioOutput').value='phone';const pending=f.elements.get('#audioOutput').onchange();await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:773,height:601});f.events.get('resize')();await f.run('scheduled.shift()()');
 assert.equal(f.requests.filter(r=>r.url==='/api/resize').length,0);
 f.run('releaseStart()');await pending;await settle();assert(f.run('scheduled.length')>0,'Transaction lost its pending viewport change');
 await f.run('scheduled.pop()()');await settle();const resize=f.requests.filter(r=>r.url==='/api/resize');
 assert.equal(resize.length,1);assert.deepEqual(resize[0].value.viewport,{width:773,height:601});assert.equal(f.elements.get('#audioOutput').value,'phone');f.run('end()');
});

test('an older pending status poll cannot lose a second viewport change during resize',async()=>{
 const f=fixture({active:false,audioOutput:'phone'});await settle();await f.elements.get('#start').onclick();await settle();
 f.run(`let releaseStatus,releaseResize,heldStatus=false,heldResize=false,scheduled=[];
 setTimeout=(fn,ms)=>{if(ms===1200)scheduled.push(fn);return scheduled.length;};clearTimeout=()=>{};
 const oldFetch=fetch;fetch=(url,options)=>{
  if(url==='/api/status'&&!heldStatus){heldStatus=true;return new Promise(resolve=>{releaseStatus=()=>resolve(oldFetch(url,options));});}
  if(url==='/api/resize'&&!heldResize){heldResize=true;return new Promise(resolve=>{releaseResize=()=>resolve(oldFetch(url,options));});}
  return oldFetch(url,options);
 };`);
 const oldPoll=f.run('poll()');await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:773,height:526});const resize=f.run('reconcileLayout()');await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:773,height:601});f.events.get('resize')();await f.run('scheduled.shift()()');
 f.run('releaseResize()');await resize;await settle();f.run('releaseStatus()');await oldPoll;await f.run('poll()');await settle();
 assert(f.run('scheduled.length')>0,'Adopting the replacement session lost its pending viewport change');
 await f.run('scheduled.pop()()');await settle();const calls=f.requests.filter(r=>r.url==='/api/resize');
 assert.equal(calls.length,2);assert.deepEqual(calls.at(-1).value.viewport,{width:773,height:601});f.run('end()');
});

test('secure canvas mode paints native frames and labels the renderer accurately',async()=>{
 const f=fixture({canvasMode:'webcodecs'});await settle();assert.equal(f.media.length,0);assert.equal(f.renderers.length,1);
 const r=f.renderers[0];f.streams[0].push(new Uint8Array([1,2]));await settle();assert.equal(r.pushed.length,1);
 r.options.onFrame({presentedFrames:12,timestamp:2000000,renderer:'webgl'});await f.run('poll()');await settle();
 assert.equal(f.run('nativeStats.renderer'),'webcodecs-webgl');assert.match(f.elements.get('#status').textContent,/H.264 canvas/);
 f.run('end()');assert.equal(r.closed,1);r.options.onFrame({presentedFrames:100,timestamp:9000000,renderer:'webgl'});assert.equal(f.run('nativeStats.presentedFrames'),12);
});

test('unavailable WebCodecs uses native images and closes every painted bitmap',async()=>{
 const f=fixture({canvasMode:'images',audioOutput:'phone'});await settle();assert.equal(f.media.length,0);assert.equal(f.images.length,1);
 f.imageReply(0);await settle();await settle();assert.equal(f.bitmaps[0].closed,1);assert.equal(f.canvases.at(-1).draws,1);
 assert.equal(f.run('nativeStats.renderer'),'jpeg-canvas');assert.equal(f.run('nativeStats.presentedFrames'),1);assert.equal(f.images[1].options.headers['X-CarDash-Frame'],'1');
 f.run('end()');await settle();assert.equal(f.images[1].options.signal.aborted,true);
});

test('image input rejects oversized headers before reading and stale decoded bitmaps never paint',async()=>{
 const bad=fixture({canvasMode:'images'});await settle();bad.imageReply(0,{length:4194305});await settle();assert.equal(bad.run('nativeStats.videoErrors'),1);assert.equal(bad.bitmaps.length,0);bad.run('end()');
 const f=fixture({canvasMode:'images'});await settle();let resolve;f.deferBitmap(new Promise(r=>{resolve=r;}));f.imageReply(0);await settle();
 const old=f.canvases.at(-1);f.run('end()');const b={width:1280,height:720,closed:0,close(){this.closed++;}};resolve(b);await settle();assert.equal(b.closed,1);assert.equal(old.draws,0);
});

test('failed native H264 decoder closes its WebGL surface before image fallback',async()=>{
 const f=fixture({canvasMode:'webcodecs'});await settle();const old=f.canvases.at(-1);f.renderers[0].options.onError(new Error('Unsupported AVC configuration'));await settle();
 await f.run('poll()');await settle();assert.equal(f.images.length,1);assert.notEqual(f.canvases.at(-1),old);assert.equal(f.run('nativeStats.renderer'),'jpeg-canvas');f.run('end()');
});

for(const body of [false,true])test(`a stalled resize ${body?'JSON body':'request'} releases controls and resumes polling`,async()=>{
 const f=fixture({active:false,audioOutput:'phone'});await settle();await f.elements.get('#start').onclick();await settle();
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:773,height:601});
 f.run(`let deadlines=[],timedSignal;setTimeout=(fn,ms)=>{if(ms>=8000)deadlines.push(fn);return 1;};clearTimeout=()=>{};
 const oldFetch=fetch;fetch=(url,options)=>{if(url==='/api/resize'){timedSignal=options.signal;return ${body?'Promise.resolve({ok:true,json:()=>new Promise(()=>{})})':'new Promise(()=>{})'};}return oldFetch(url,options);};`);
 const pending=f.run('reconcileLayout()');await settle();
 assert.equal(f.run('changingLayout'),true);assert(f.run('deadlines.length')>0,'No bounded resize deadline');
 f.run('deadlines.shift()()');await pending;await settle();
 assert.equal(f.run('changingLayout'),false);assert.equal(f.run('timedSignal.aborted'),true);
 assert.equal(f.run('layoutSession'),null);assert.match(f.elements.get('#status').textContent,/timed out/i);
 assert.equal(f.elements.get('#stop').disabled,false);await f.run('poll()');assert.equal(f.run('polling'),false);f.run('end()');
});

test('a stalled status body cannot permanently block subsequent polling',async()=>{
 const f=fixture({audioOutput:'phone'});await settle();
 f.run(`let deadlines=[],heldStatus=true,statusSignal;setTimeout=(fn,ms)=>{if(ms>=8000)deadlines.push(fn);return 1;};clearTimeout=()=>{};
 const oldFetch=fetch;fetch=(url,options)=>{if(url==='/api/status'&&heldStatus){heldStatus=false;statusSignal=options.signal;return Promise.resolve({ok:true,json:()=>new Promise(()=>{})});}return oldFetch(url,options);};`);
 const pending=f.run('poll()');await settle();assert(f.run('deadlines.length')>0,'No bounded status deadline');
 f.run('deadlines.shift()()');await pending;assert.equal(f.run('polling'),false);assert.equal(f.run('statusSignal.aborted'),true);
 await f.run('poll()');assert.equal(f.run('inputSession'),'first');assert.doesNotMatch(f.elements.get('#status').textContent,/connection unavailable/i);f.run('end()');
});

test('an idle native image response waits for another frame without disconnecting',async()=>{
 const f=fixture({canvasMode:'images',audioOutput:'phone'});await settle();
 f.images[0].resolve({ok:true,status:204,body:null});await settle();await settle();
 assert.equal(f.run('nativeStats.videoErrors'),0);assert.equal(f.images.length,2);
 f.imageReply(1);await settle();await settle();assert.equal(f.run('nativeStats.presentedFrames'),1);f.run('end()');
});

test('a stalled image request is aborted and reports its timeout',async()=>{
 const f=fixture({active:false,canvasMode:'images',audioOutput:'phone'});await settle();
 f.run('let imageDeadline;const originalTimer=setTimeout;setTimeout=(fn,ms)=>{if(ms===6000)imageDeadline=fn;return originalTimer(fn,ms);};');
 await f.elements.get('#start').onclick();await settle();
 assert.equal(f.images.length,1);f.run('imageDeadline()');await settle();
 assert.equal(f.images[0].options.signal.aborted,true);assert.equal(f.run('closed'),true);assert.equal(f.run('nativeStats.videoErrors'),1);
 assert.match(f.run('nativeStats.lastVideoError'),/timed out/);f.run('end()');
});


test('hosted page sends nothing before Connect and labels experimental mode',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',active:false,audioOutput:'phone'});await settle();
 assert.equal(f.fetchCalls.length,0);assert.equal(f.elements.get('#start').disabled,true);
 assert.match(f.elements.get('#buildLabel').textContent,/Experimental HTTPS/);
 f.elements.get('#endpoint').value='http://169.254.38.140:8890/';await f.elements.get('#connect').onclick();await settle();
 assert.deepEqual(f.connectionCalls,['http://169.254.38.140:8890/']);assert(f.adapterCalls.includes('/api/status'));
 assert.equal(f.elements.get('#start').disabled,false);assert.equal(f.elements.get('#connect').textContent,'Reconnect');
 assert(!f.requests.some(r=>r.url==='/api/start'),'Connecting must not start a native session');f.run('end()');
});

test('hosted unsupported codec API never attempts bootstrap, JPEG or MSE',async()=>{
 const f=fixture({hosted:true,canvasMode:'image',audioOutput:'phone'});await settle();
 await f.elements.get('#connect').onclick();await settle();
 assert.equal(f.connectionCalls.length,0);assert.equal(f.fetchCalls.length,0);assert.equal(f.images.length,0);assert.equal(f.media.length,0);
 assert.match(f.elements.get('#status').textContent,/does not support secure H.264 canvas/);f.run('end()');
});

test('hosted decoder failure is bounded until explicit Reconnect with no image fallback',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'phone'});await f.elements.get('#connect').onclick();await settle();
 assert.equal(f.renderers.length,1);assert(f.adapterCalls.includes('/video'));
 f.renderers[0].options.onError(new Error('Unsupported native AVC profile'));await settle();
 await f.run('poll()');await f.run('poll()');await settle();
 assert.equal(f.renderers.length,1);assert.equal(f.images.length,0);assert.equal(f.media.length,0);
 assert.match(f.elements.get('#status').textContent,/Unsupported native AVC profile.*Reconnect/);
 await f.elements.get('#connect').onclick();await settle();assert.equal(f.renderers.length,2);f.run('end()');
});

test('hosted metrics separate decoded callbacks from canvas draw calls',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'phone'});await f.elements.get('#connect').onclick();await settle();
 f.renderers[0].stats={decodedFrames:12,presentedFrames:3};
 f.renderers[0].options.onFrame({decodedFrames:10,presentedFrames:3,timestamp:1000000,renderer:'webgl'});
 f.run('lastMetrics=-Infinity');const metrics=f.run('browserMetrics()');
 assert.equal(metrics.decodedFrames,12);assert.equal(metrics.presentedFrames,3);assert.equal(metrics.canvasDrawCalls,3);
 assert.equal(f.run('nativeStats.decodedFrames'),10);f.run('end()');
});

test('hosted touch release on pagehide uses the authenticated request adapter',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'phone'});await f.elements.get('#connect').onclick();await settle();
 f.elements.get('#canvas').onpointerdown({pointerId:1,clientX:100,clientY:100});await settle();
 f.events.get('pagehide')();await settle();
 const release=f.fetchCalls.filter(r=>r.url==='/api/touch').at(-1);
 assert.equal(release.options.keepalive,true);assert.equal(JSON.parse(release.options.body).down,false);
 assert.equal(f.adapterCalls.filter(p=>p==='/api/touch').length,2);f.run('end()');
});


test('showing and hiding controls never resizes or replaces a healthy native session',async()=>{
 const f=fixture({active:false,audioOutput:'browser',canvasMode:'webcodecs'});await settle();await f.elements.get('#start').onclick();await settle();
 const session=f.run('inputSession'),connections=f.run('nativeStats.videoConnections'),stops=f.audioCalls.stop;
 f.run('let scheduledCount=0;setTimeout=(fn,ms)=>{if(ms===1200)scheduledCount++;return 1;}');
 for(let i=0;i<20;i++){f.run('fullscreen(true)');f.run('fullscreen(false)');}
 assert.equal(f.run('scheduledCount'),0);assert.equal(f.run('inputSession'),session);assert.equal(f.run('nativeStats.videoConnections'),connections);assert.equal(f.audioCalls.stop,stops);
 assert.equal(f.requests.filter(r=>r.url==='/api/resize').length,0);f.run('end()');
});

test('first native frame hides controls once without changing audio or the native session',async()=>{
 const f=fixture({canvasMode:'webcodecs',audioOutput:'browser'});await settle();const stopCount=f.audioCalls.stop;
 f.renderers[0].options.onFrame({decodedFrames:1,presentedFrames:1,timestamp:1000,renderer:'webgl'});
 assert(f.classSet.has('full'));assert.equal(f.audioCalls.stop,stopCount);assert.equal(f.requests.filter(r=>r.url==='/api/resize').length,0);
 f.run('fullscreen(false)');f.renderers[0].options.onFrame({decodedFrames:2,presentedFrames:2,timestamp:2000,renderer:'webgl'});
 assert(!f.classSet.has('full'),'User-opened controls must remain open');f.run('end()');
});

test('motion queue stays bounded and pointer-up follows the in-flight down immediately',async()=>{
 const f=fixture({audioOutput:'phone'});await settle();let finish;
 f.deferNextTouch(new Promise(resolve=>{finish=resolve;}));f.run("send(.1,.1,true,'down')");await settle();
 for(let i=0;i<300;i++)f.run(`send(${i/300},.5,true,'move')`);
 assert(f.run('nativeStats.inputQueued')<=2);assert.equal(f.touches.length,1);
 f.run("send(.9,.6,false,'up')");finish({ok:true,json:async()=>({sequence:1})});await settle();await settle();
 assert.equal(f.touches.length,2);assert.equal(f.touches[1].down,false);assert.equal(f.touches[1].x,.9);
 assert(f.run('nativeStats.inputCoalesced')>=299);assert.equal(f.run('nativeStats.inputQueued'),0);f.run('end()');
});

test('a transient touch failure sends one release while video and audio stay connected',async()=>{
 const f=fixture({audioOutput:'browser',canvasMode:'webcodecs'});await settle();const stops=f.audioCalls.stop,connections=f.run('nativeStats.videoConnections');
 f.deferNextTouch(Promise.resolve({ok:false,json:async()=>({error:'Touch send failed'})}));f.run("send(.4,.5,true,'down')");await settle();await settle();
 assert.equal(f.touches.length,2);assert.equal(f.touches[1].down,false);assert.equal(f.audioCalls.stop,stops);assert.equal(f.run('nativeStats.videoConnections'),connections);assert.equal(f.run('closed'),false);
 assert.equal(f.run('nativeStats.inputErrors'),1);f.run('end()');
});

test('a pending status request cannot delay independent browser heartbeats',async()=>{
 const f=fixture({audioOutput:'phone'});await settle();f.run(`let finishHeldStatus;const original=fetch;fetch=(url,options)=>url==='/api/status'?new Promise(resolve=>{finishHeldStatus=()=>resolve(original(url,options));}):original(url,options);`);
 const before=f.requests.filter(r=>r.url==='/api/heartbeat').length,pending=f.run('poll()');await settle();
 await f.run('heartbeat()');await settle();assert.equal(f.requests.filter(r=>r.url==='/api/heartbeat').length,before+1);
 f.run('finishHeldStatus()');await pending;f.run('end()');
});

function recoveryClock(f){
 f.run(`let clockNow=100,scheduled=[];performance.now=()=>clockNow;
 setTimeout=(fn,ms)=>{const item={fn,ms,cancelled:false};scheduled.push(item);return item;};
 clearTimeout=item=>{if(item&&typeof item==='object')item.cancelled=true;};`);
 return {pending:()=>f.run('scheduled.filter(item=>!item.cancelled&&item===streamRecovery.timer)'),
  fire(index=0,now=null){const item=this.pending()[index];assert(item,'Missing recovery timer');if(now!==null)f.run('clockNow='+now);item.cancelled=true;item.fn();return item;}};
}

test('hosted stream EOF reconnects only video and preserves native session, audio and open controls',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'browser'});await f.elements.get('#connect').onclick();await settle();
 const clock=recoveryClock(f),stops=f.audioCalls.stop,commands=f.requests.filter(r=>['/api/start','/api/stop','/api/resize'].includes(r.url)).length;
 f.renderers[0].options.onFrame({decodedFrames:1,presentedFrames:1,timestamp:1000000,renderer:'webgl'});f.run('fullscreen(false)');
 f.streams[0].finish();await settle();assert.equal(clock.pending()[0].ms,500);assert.equal(f.run('inputSession'),'first');assert.equal(f.audioCalls.stop,stops);
 await f.run('poll()');await f.run('poll()');await settle();assert.equal(f.renderers.length,1,'Polling bypassed the retry deadline');
 clock.fire(0,600);await settle();assert.equal(f.renderers.length,2);assert.equal(f.streams[1].session,'first');assert.equal(f.audioCalls.stop,stops);
 f.renderers[1].options.onFrame({decodedFrames:1,presentedFrames:1,timestamp:2000000,renderer:'webgl'});
 assert(!f.classSet.has('full'),'Video-only recovery closed user-opened controls');assert.equal(f.run('nativeStats.videoRetries'),1);
 assert.equal(f.requests.filter(r=>['/api/start','/api/stop','/api/resize'].includes(r.url)).length,commands);f.run('end()');
});

test('video replacement waits for a delayed down and its release before accepting a new gesture',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'browser'});await f.elements.get('#connect').onclick();await settle();
 const clock=recoveryClock(f),stops=f.audioCalls.stop;let finishDown,finishUp;
 f.deferNextTouch(new Promise(resolve=>{finishDown=resolve;}));f.run("send(.1,.2,true,'down');send(.3,.4,false,'up')");await settle();
 f.streams[0].finish();await settle();clock.fire(0,600);await settle();
 assert.equal(f.renderers.length,2);assert.equal(f.run("send(.8,.8,true,'down')"),false);assert.equal(f.touches.length,1);
 f.deferNextTouch(new Promise(resolve=>{finishUp=resolve;}));finishDown({ok:true,json:async()=>({sequence:1})});await settle();await settle();
 assert.equal(f.touches.length,2);assert.equal(f.touches[1].down,false);assert.equal(f.touches[1].session,'first');
 assert.equal(f.run("send(.8,.8,true,'down')"),false,'Input raced the pending cleanup release');
 finishUp({ok:true,json:async()=>({sequence:2})});await settle();await settle();
 assert.equal(f.run("send(.8,.8,true,'down')"),true);await settle();assert.equal(f.touches.length,3);assert.equal(f.audioCalls.stop,stops);f.run('end()');
});

test('a cancelled recovery timer cannot clear or fire a replacement timer for the same generation',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'browser'});await f.elements.get('#connect').onclick();await settle();const clock=recoveryClock(f);
 f.streams[0].finish();await settle();const old=clock.pending()[0];f.run('end()');await f.run('poll()');await settle();
 f.streams[1].finish();await settle();const fresh=clock.pending()[0],connections=f.renderers.length;
 old.fn();await settle();assert.equal(f.renderers.length,connections);assert.equal(f.run('streamRecovery.timer'),fresh);
 clock.fire(0,600);await settle();assert.equal(f.renderers.length,connections+1);f.run('end()');
});

test('network retries use 0.5/1/2 seconds and count actual delayed execution toward the three-per-minute cap',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'browser'});await f.elements.get('#connect').onclick();await settle();const clock=recoveryClock(f),stops=f.audioCalls.stop;
 for(const [index,delay,at] of [[0,500,90100],[1,1000,91100],[2,2000,93100]]){
  f.streams[index].finish();await settle();assert.equal(clock.pending()[0].ms,delay);clock.fire(0,at);await settle();
 }
 f.streams[3].finish();await settle();assert.equal(clock.pending().length,0);assert.equal(f.renderers.length,4);
 assert.equal(f.run('nativeStats.streamRecoveries'),3);assert.equal(f.run('nativeStats.videoRetries'),3);assert.equal(f.run('inputSession'),'first');assert.equal(f.audioCalls.stop,stops);
 assert.match(f.elements.get('#status').textContent,/recovery limit.*Reconnect/i);await f.run('poll()');await settle();assert.equal(f.renderers.length,4);f.run('end()');
});

test('sustained timeline lag reconnects only the display with a ten-second catchup cooldown',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'browser'});await f.elements.get('#connect').onclick();await settle();const clock=recoveryClock(f),stops=f.audioCalls.stop;
 f.service={videoTimelineTicks:102*90000};f.renderers[0].options.onFrame({decodedFrames:12,presentedFrames:10,timestamp:100000000,renderer:'webgl'});
 await f.run('poll()');await settle();assert.equal(clock.pending().length,0);assert.equal(f.run('nativeStats.streamLagMs'),2000);
 await f.run('poll()');await settle();assert.equal(clock.pending()[0].ms,0);clock.fire(0,100);await settle();
 f.service={videoTimelineTicks:106*90000};f.renderers[1].options.onFrame({decodedFrames:2,presentedFrames:2,timestamp:102000000,renderer:'webgl'});
 await f.run('poll()');await settle();assert.equal(clock.pending()[0].ms,10000);assert.equal(f.run('nativeStats.videoRetries'),0);
 clock.fire(0,10100);await settle();assert.equal(f.run('nativeStats.streamRecoveries'),2);assert.equal(f.audioCalls.stop,stops);assert.equal(f.run('inputSession'),'first');
 assert.equal(f.requests.filter(r=>['/api/start','/api/stop','/api/resize'].includes(r.url)).length,0);f.run('end()');
});

test('intentional stop and late old-stream EOF never schedule display recovery',async()=>{
 const f=fixture({hosted:true,canvasMode:'webcodecs',audioOutput:'phone'});await f.elements.get('#connect').onclick();await settle();const clock=recoveryClock(f);
 const old=f.streams[0];await f.elements.get('#stop').onclick();old.finish();await settle();
 assert.equal(clock.pending().length,0);assert.equal(f.run('nativeStats.streamRecoveries'),0);assert.equal(f.run('nativeStats.videoErrors'),0);
});

test('passive viewers adopt viewport ownership only through the explicit Fit display action',async()=>{
 const f=fixture({audioOutput:'phone'});await settle();assert.equal(f.run('layoutSession'),null);
 f.elements.get('video').getBoundingClientRect=()=>({left:0,top:0,width:773,height:601});
 f.run('fullscreen(true);fullscreen(false)');f.events.get('resize')();await f.run('reconcileLayout()');await settle();
 assert.equal(f.run('layoutSession'),null);assert.equal(f.requests.filter(r=>r.url==='/api/resize').length,0);
 await f.elements.get('#fitViewport').onclick();await settle();assert.equal(f.requests.filter(r=>r.url==='/api/resize').length,1);assert.equal(f.run('layoutSession'),'resized');f.run('end()');
});
