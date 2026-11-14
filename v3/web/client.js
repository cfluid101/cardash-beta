// Native CarPlay display and HID input. Every renderer uses the native session stream.
const video=document.querySelector('video'),status=document.querySelector('#status');
let canvas=document.querySelector('#canvas');
const transport=window.CarDashTransport||{fetch:(...args)=>fetch(...args),diagnostics:{mode:'local',ready:true}};
const hosted=transport.diagnostics.mode==='hosted',fetchDevice=(...args)=>transport.fetch(...args);
let connectionBusy=false,blockedVideoSession=null,blockedVideoError='',inputError='';
window.nativeStats={decodedFrames:0,inputSent:0,inputQueued:0,inputCoalesced:0,inputErrors:0,inputRttMs:0,heartbeatErrors:0,heartbeatRttMs:0,statusRttMs:0,videoRetries:0,streamRecoveries:0,streamLagMs:0,trims:0,videoConnections:0,videoErrors:0,lastVideoError:'',lastVideoErrorTime:null,lastVideoErrorDetails:null};
let inputSession=null,videoConnection=null,commandEpoch=0,audioEpoch=0,carplayActive=false,identityReady=false;
let baseStatus='Connecting to iPhone…',audioError='';
let audioOutput='phone',changingOutput=false,changingLayout=false;
let layoutSession=null,layoutViewport=null,sourceWidth=1280,sourceHeight=720,layoutError='';
let forceImage=false,lastFrameAt=0,continuousDecodeSupported=false;
let streamRecovery={session:null,attempts:[],timer:null,pending:null,reason:''};
let controlsHiddenSession=null,inputCleanup=null;
function viewport(){const r=video.getBoundingClientRect();return {width:Math.round(r.width),height:Math.round(r.height)};}
function sameViewport(a,b){return a&&b&&Math.abs(a.width-b.width)<2&&Math.abs(a.height-b.height)<2;}
async function reconcileLayout(){
 if(changingOutput||changingLayout||!carplayActive||!inputSession||layoutSession!==inputSession)return;
 const target=viewport();if(target.width<100||target.height<100||sameViewport(target,layoutViewport))return;
 const session=inputSession,epoch=++commandEpoch;changingLayout=true;end();
 layoutError='';baseStatus='Resizing native CarPlay…';renderStatus();
 try{
  const result=await api('resize',{session,viewport:target});
  if(epoch!==commandEpoch)return;
  layoutSession=result.session;layoutViewport=target;
 }catch(e){if(epoch===commandEpoch){layoutSession=null;layoutError='Native resize failed: '+e.message;}}
 finally{changingLayout=false;if(epoch===commandEpoch)await poll();renderStatus();}
}
// Keep these aliases for the diagnostic browser harness; each connection owns
// the actual buffers so delayed callbacks cannot modify a replacement stream.
let buffer,queue=[],bytes=0,closed=true,inputQueue=Promise.resolve(),pointer=null,abort,connecting=false;
async function requestJSON(url,options={},timeout=8000){
 const controller=new AbortController();let timer;const requestedAt=performance.now();
 const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error('Request timed out; reconnecting to iPhone.'));},timeout);});
 try{return await Promise.race([(async()=>{const response=await fetchDevice(url,{...options,signal:controller.signal});const value=await response.json();if(!response.ok)throw new Error(value.error||'Request failed ('+response.status+')');return value;})(),deadline]);}
 finally{clearTimeout(timer);const key={'/api/status':'statusRttMs','/api/heartbeat':'heartbeatRttMs','/api/touch':'inputRttMs'}[url];if(key)nativeStats[key]=Math.min(60000,Math.max(0,Math.round(performance.now()-requestedAt)));}
}
function api(action,body={}){return requestJSON('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},action==='heartbeat'||action==='touch'?4000:20000);}

function current(owner){return owner&&videoConnection===owner&&inputSession===owner.session&&!owner.abort.signal.aborted;}
function closeDisplay(keepLastFrame=false){
 const old=videoConnection;releaseDetachedInput(old);videoConnection=null;closed=true;connecting=false;old?.abort.abort();
 if(old?.reader)old.reader.cancel().catch(()=>{});
 old?.renderer?.close();
 if(!keepLastFrame){if(canvas)canvas.hidden=true;if(video.style)video.style.visibility='';document.body.classList.remove('live');}
 if(old?.url)URL.revokeObjectURL(old.url);
 buffer=null;queue=[];bytes=0;pointer=null;inputQueue=Promise.resolve();nativeStats.inputQueued=0;if(old?.input)old.input.queue=[];
 video.pause();video.removeAttribute('src');video.load();
}
function end(){
 if(streamRecovery.timer!==null)clearTimeout(streamRecovery.timer);
 streamRecovery={session:null,attempts:[],timer:null,pending:null,reason:''};
 closeDisplay();inputSession=null;audioEpoch++;audioError='';CarDashAudio.stop();
}
function recoverDisplay(error,owner,codec,reason='network'){
 if(!current(owner))return;
 const session=owner.session,now=performance.now();
 if(streamRecovery.session!==session)streamRecovery={session,attempts:[],timer:null,pending:null,reason:''};
 const recovery=streamRecovery;
 recovery.attempts=recovery.attempts.filter(at=>now-at.time<60000);
 closeDisplay(true);recovery.reason=reason;
 const previous=recovery.attempts.at(-1),networkAttempts=recovery.attempts.filter(at=>at.reason==='network').length;
 const cooldown=recovery.attempts.length>=3?Math.max(1,recovery.attempts[0].time+60000-now):0;
 const delay=Math.max(cooldown,reason==='lag'?Math.max(0,previous?previous.time+10000-now:0):[500,1000,2000][Math.min(2,networkAttempts)]);
 baseStatus=reason==='lag'?'Catching up the native display…':'Reconnecting the native display…';renderStatus();
 const ticket={};recovery.pending=ticket;
 recovery.timer=setTimeout(function retry(){
  // A cancelled callback may already be queued when a new session starts.
  if(streamRecovery!==recovery||recovery.pending!==ticket)return;
  recovery.timer=null;recovery.pending=null;
  if(!carplayActive||inputSession!==session||!closed||!transport.diagnostics.ready)return;
  const actual=performance.now();recovery.attempts=recovery.attempts.filter(at=>actual-at.time<60000);
  if(recovery.attempts.length>=3){
   recovery.pending=ticket;recovery.timer=setTimeout(retry,Math.max(1,recovery.attempts[0].time+60000-actual));return;
  }
  // Count actual reconnects, not scheduled timestamps: backgrounded browser
  // timers can run much later than requested.
  recovery.attempts.push({time:actual,reason});nativeStats.streamRecoveries++;
  if(reason==='network')nativeStats.videoRetries++;
  nativeStats.lastStreamRecoveryReason=reason;
  connect(codec,session);
 },delay);
}
function renderStatus(){
 const a=CarDashAudio.stats,button=document.querySelector('#sound');
 button.hidden=audioOutput!=='browser';
 document.querySelector('#audioOutput').disabled=connectionBusy||changingOutput||changingLayout||!transport.diagnostics.ready;
 document.querySelector('#start').disabled=connectionBusy||changingOutput||changingLayout||carplayActive||!identityReady||!transport.diagnostics.ready;
 document.querySelector('#stop').disabled=connectionBusy||changingOutput||changingLayout||!carplayActive||!transport.diagnostics.ready;
 if(hosted){const state=transport.diagnostics,button=document.querySelector('#connect');if(button){button.disabled=connectionBusy||changingOutput||changingLayout;button.textContent=connectionBusy?'Connecting…':state.ready?'Reconnect':'Connect';}const detail=document.querySelector('#connectionStatus');if(detail)detail.textContent=connectionBusy?'Allow Local Network Access if the browser asks.':state.lastError||(state.ready?'Direct iPhone connection: '+state.endpoint:'Connect to the iPhone on your hotspot.');}
 const rendering=carplayActive&&nativeStats.renderer?' · '+(nativeStats.renderer==='jpeg-canvas'?'Native image stream':nativeStats.renderer.startsWith('webcodecs')?'H.264 canvas':'Video player'):'';
 const displayStatus=(inputError?inputError+' · ':'')+(layoutError?layoutError+' · '+baseStatus:baseStatus)+rendering;
 const fit=document.querySelector('#fitViewport');if(fit)fit.disabled=changingOutput||changingLayout||!carplayActive||!inputSession;
 if(audioOutput!=='browser'){status.textContent=displayStatus+' · Audio: device output';return;}
 const error=audioError||(carplayActive?a.error:'');
 const retry=Boolean(error)||(carplayActive&&a.enabled&&a.contextState==='running'&&a.connectionState==='disconnected');
 button.textContent=retry?'Retry sound':a.contextState!=='running'||!a.enabled?'Enable sound':a.muted?'Unmute':'Mute';
 button.title=error|| (a.muted?'Sound is muted':'Control browser sound');
 button.setAttribute('aria-pressed',String(a.muted));
 let detail='';
 if(error)detail=' · Sound: '+error+(a.muted?' (muted)':'');
 else if(carplayActive&&(!a.enabled||a.contextState!=='running'))detail=' · Tap Enable sound';
 else if(carplayActive&&a.connectionState==='connecting')detail=' · Sound connecting…';
 else if(carplayActive&&a.muted)detail=' · Sound muted';
 status.textContent=displayStatus+detail;
}
function enableSound(){
 if(audioOutput!=='browser')return Promise.resolve(false);
 audioError='';const epoch=audioEpoch;
 try{return CarDashAudio.enable().catch(e=>{if(epoch===audioEpoch){audioError=e.message;renderStatus();}return false;});}
 catch(e){if(epoch===audioEpoch){audioError=e.message;renderStatus();}return Promise.resolve(false);}
}
function connectSound(session){
 if(audioOutput!=='browser')return Promise.resolve(false);
 const epoch=audioEpoch,prior=CarDashAudio.stats.error;if(prior)audioError=prior;
 return CarDashAudio.connect(session).then(ready=>{
  if(session!==inputSession||epoch!==audioEpoch)return false;
  if(ready)audioError='';else if(CarDashAudio.stats.error)audioError=CarDashAudio.stats.error;
  renderStatus();return ready;
 }).catch(e=>{if(session===inputSession&&epoch===audioEpoch){audioError=e.message;renderStatus();}return false;});
}
function fail(e,owner=null){if(owner&&!current(owner))return;end();baseStatus=e.message;fullscreen(false);renderStatus();}
function frameDisplayed(owner){if(!current(owner)||controlsHiddenSession===owner.session)return;controlsHiddenSession=owner.session;fullscreen(true);}
function failVideo(e,owner,stage){
 if(!current(owner))return;
 if(hosted){blockedVideoSession=owner.session;blockedVideoError=(e.message||String(e))+' Press Reconnect to retry.';}
 const ranges=[];try{for(let i=0;i<owner.buffer?.buffered.length;i++)ranges.push([owner.buffer.buffered.start(i),owner.buffer.buffered.end(i)]);}catch(_){}
 nativeStats.videoErrors++;nativeStats.lastVideoError=e.message||String(e);nativeStats.lastVideoErrorTime=new Date().toISOString();
 nativeStats.lastVideoErrorDetails={stage:stage||owner.phase,session:owner.session,currentTime:video.currentTime,queuedBytes:owner.bytes,bufferUpdating:Boolean(owner.buffer?.updating),buffered:ranges,mediaError:video.error?.code||null,decodedFrames:nativeStats.decodedFrames};
 fail(e,owner);
}
function append(owner){
 if(!current(owner)||!owner.buffer||owner.buffer.updating||!owner.queue.length)return;
 const data=owner.queue.shift();owner.bytes-=data.byteLength;bytes=owner.bytes;
 try{owner.buffer.appendBuffer(data);}catch(e){failVideo(e,owner,'append');}
}
function live(owner){
 if(!current(owner))return;
 if(video.buffered.length){const last=video.buffered.end(video.buffered.length-1);if(video.currentTime<video.buffered.start(0)||last-video.currentTime>1)video.currentTime=Math.max(video.buffered.start(0),last-.15);if(video.paused)video.play().catch(()=>{});}
}
function trimVideo(owner){
 const ranges=owner.buffer.buffered;if(!ranges.length)return false;
 const start=ranges.start(0),end=ranges.end(ranges.length-1);
 if(video.currentTime-start>8){
  // MSE removal extends to the next random access point. Never cut into the
  // current decode chain: retain a confirmed IDR at least three seconds back.
  const before=Math.min(video.currentTime-3,end),safe=owner.keyframes.filter(t=>t/90000>start+1/90000&&t/90000<before);
  if(safe.length){const keep=safe[safe.length-1];nativeStats.trims++;owner.buffer.remove(start,(keep-1)/90000);return true;}
 }
 if(end-start>90)throw new Error('Native video has no safe random access point within 90 seconds; reconnecting.');
 return false;
}
async function connect(codec,session=inputSession){
 if(connecting||!closed||!session||session!==inputSession||streamRecovery.timer!==null)return;
 if(hosted&&(!canvas||typeof CarDashCanvas==='undefined'||!CarDashCanvas.available())){blockedVideoSession=session;blockedVideoError='This browser does not support secure H.264 canvas decoding. The hosted renderer cannot start.';fail(new Error(blockedVideoError));return;}
 if(canvas&&typeof CarDashCanvas!=='undefined'){
  if((hosted||!forceImage)&&CarDashCanvas.available())return connectCanvas(codec,session);
  if(typeof createImageBitmap==='function')return connectImages(session);
 }
 const owner={session,abort:new AbortController(),queue:[],bytes:0,buffer:null,reader:null,url:null,phase:'sourceopen',keyframes:[],timelineTicks:0};
 videoConnection=owner;connecting=true;closed=false;abort=owner.abort;queue=owner.queue;bytes=0;buffer=null;
 lastFrameAt=performance.now();Object.assign(nativeStats,{decodedFrames:0,presentedFrames:0,inputSent:0,trims:0,renderer:'mse'});nativeStats.videoConnections++;
 try{
  const media=new MediaSource();owner.url=URL.createObjectURL(media);
  const opened=new Promise((resolve,reject)=>{
   const clean=()=>{media.removeEventListener('sourceopen',onOpen);owner.abort.signal.removeEventListener('abort',onAbort);};
   const onOpen=()=>{clean();resolve();};const onAbort=()=>{clean();reject(new DOMException('Old video connection ended','AbortError'));};
   media.addEventListener('sourceopen',onOpen,{once:true});owner.abort.signal.addEventListener('abort',onAbort,{once:true});
  });
  video.src=owner.url;await opened;if(!current(owner))return;
  URL.revokeObjectURL(owner.url);owner.url=null;
  owner.phase='source-buffer';owner.buffer=media.addSourceBuffer(`video/mp4; codecs="${codec}"`);buffer=owner.buffer;
  owner.buffer.addEventListener('updateend',()=>{
   // A queued updateend may arrive after the reader starts another append.
   if(!current(owner)||owner.buffer.updating)return;
   try{live(owner);
    if(trimVideo(owner))return;
    append(owner);
   }catch(e){failVideo(e,owner,'updateend');}
  });
  owner.buffer.addEventListener('error',()=>failVideo(new Error('Video decoder error; reconnect the preview.'),owner,'source-buffer-error'));
  owner.phase='video-request';
  const response=await fetchDevice('/video',{signal:owner.abort.signal,headers:{'X-CarDash-Session':session}});
  if(!current(owner))return;if(!response.ok||!response.body)throw new Error('Native video is not ready ('+response.status+')');
  owner.phase='video-stream';owner.reader=response.body.getReader();document.body.classList.add('live');
  video.requestVideoFrameCallback(function frame(_,meta){if(!current(owner))return;frameDisplayed(owner);lastFrameAt=performance.now();nativeStats.decodedFrames=meta.presentedFrames;nativeStats.presentedFrames=meta.presentedFrames;nativeStats.mediaTime=meta.mediaTime;video.requestVideoFrameCallback(frame);});
  connecting=false;
  for(;;){
   const {value,done}=await owner.reader.read();if(!current(owner))break;if(done)throw new Error('Native session ended');
   owner.bytes+=value.byteLength;if(owner.bytes>4*1024*1024)throw new Error('Viewer fell behind; reconnect.');
   bytes=owner.bytes;owner.queue.push(value);append(owner);
  }
 }catch(e){if(e.name!=='AbortError')failVideo(e,owner);}
 finally{if(owner.url)URL.revokeObjectURL(owner.url);if(current(owner))connecting=false;}
}
function canvasOwner(session,renderer){
 if(canvas.cloneNode){const next=canvas.cloneNode(false);canvas.replaceWith(next);canvas=next;bindCanvas();}
 const owner={session,abort:new AbortController(),reader:null,renderer:null,phase:renderer};
 videoConnection=owner;connecting=true;closed=false;abort=owner.abort;
 lastFrameAt=performance.now();Object.assign(nativeStats,{decodedFrames:0,presentedFrames:0,inputSent:0,trims:0,renderer});nativeStats.videoConnections++;
 canvas.width=sourceWidth;canvas.height=sourceHeight;canvas.hidden=false;
 if(video.style)video.style.visibility='hidden';
 document.body.classList.add('live');return owner;
}
async function connectCanvas(codec,session){
 const owner=canvasOwner(session,'webcodecs-webgl');owner.codec=codec;let retryable=false;
 try{
  owner.renderer=CarDashCanvas.create({canvas,codec,width:sourceWidth,height:sourceHeight,
   onFrame:s=>{if(!current(owner))return;frameDisplayed(owner);lastFrameAt=performance.now();nativeStats.decodedFrames=s.decodedFrames;nativeStats.presentedFrames=s.presentedFrames;nativeStats.mediaTime=s.timestamp/1e6;nativeStats.renderer=s.renderer==='canvas2d'?'webcodecs-2d':'webcodecs-webgl';
    // A fresh output can catch up between polls. An old status reference must
    // not mask a continuously moving source that is still seconds behind.
    if(Number.isSafeInteger(owner.timelineTicks)&&Number.isFinite(owner.timelineRequestedAt)&&lastFrameAt-owner.timelineRequestedAt<=500&&owner.timelineTicks/90-s.timestamp/1000<=500)owner.nativeLagSince=null;
   },
   onError:e=>{if(!current(owner))return;if(hosted&&e.code==='DECODER_STALLED'){recoverDisplay(e,owner,codec,'network');return;}if(!hosted)forceImage=true;failVideo(new Error('H.264 canvas decoder: '+e.message),owner,'canvas-decoder');}});
  retryable=true;const response=await fetchDevice('/video',{signal:owner.abort.signal,headers:{'X-CarDash-Session':session,...(continuousDecodeSupported?{'X-CarDash-Renderer':'webcodecs'}:{})}});
  if(!current(owner))return;if(!response.ok||!response.body){retryable=response.status>=500;throw new Error('Native H.264 is not ready ('+response.status+')');}
  owner.reader=response.body.getReader();connecting=false;
  for(;;){retryable=true;const {value,done}=await owner.reader.read();if(!current(owner))break;if(done)throw new Error('Native H.264 stream ended');retryable=false;await owner.renderer.push(value);}
 }catch(e){if(e.name!=='AbortError'&&current(owner)){if(hosted&&retryable&&transport.diagnostics.ready)recoverDisplay(e,owner,codec);else{if(!hosted)forceImage=true;failVideo(e,owner,'canvas-stream');}}}
 finally{if(current(owner))connecting=false;}
}
async function connectImages(session){
 const owner=canvasOwner(session,'jpeg-canvas');let sequence=0;
 try{
  // canvasOwner replaces a prior WebGL surface before requesting 2D.
  if(canvas.getContext('2d')===null)throw new Error('Image canvas unavailable; reload this page.');
  const context=canvas.getContext('2d');connecting=false;
  for(;;){
   const deadline=setTimeout(()=>failVideo(new Error('Native image request timed out'),owner,'image-timeout'),6000);
   try{
    const response=await fetchDevice('/image',{signal:owner.abort.signal,headers:{'X-CarDash-Session':session,'X-CarDash-Frame':String(sequence)}});
    if(!current(owner))break;
    if(response.status===204)continue;
    if(!response.ok||!response.body)throw new Error('Native image stream unavailable ('+response.status+')');
    const next=Number(response.headers.get('X-CarDash-Frame'));if(!Number.isSafeInteger(next)||next<=sequence)throw new Error('Invalid native image sequence');
    if(response.headers.get('Content-Type')!=='image/jpeg')throw new Error('Invalid native image type');
    const length=Number(response.headers.get('Content-Length'));if(!Number.isSafeInteger(length)||length<=0||length>4*1024*1024)throw new Error('Invalid native image size');
    owner.reader=response.body.getReader();const chunks=[];let count=0;
    for(;;){const {value,done}=await owner.reader.read();if(!current(owner))break;if(done)break;count+=value.byteLength;if(count>length)throw new Error('Native image exceeded declared size');chunks.push(value);}
    if(!current(owner))break;if(count!==length)throw new Error('Truncated native image');owner.reader=null;
    const frame=await createImageBitmap(new Blob(chunks,{type:'image/jpeg'}));
    try{if(!current(owner))break;if(frame.width!==sourceWidth||frame.height!==sourceHeight)throw new Error('Native image geometry changed');context.drawImage(frame,0,0,canvas.width,canvas.height);}
    finally{frame.close();}
    sequence=next;frameDisplayed(owner);lastFrameAt=performance.now();nativeStats.decodedFrames++;nativeStats.presentedFrames++;nativeStats.mediaTime=Number(response.headers.get('X-CarDash-Time')||0)/1e6;
   }finally{clearTimeout(deadline);}
  }
 }catch(e){if(e.name!=='AbortError')failVideo(e,owner,'native-image-stream');}
 finally{if(current(owner))connecting=false;}
}
const MAX_INPUT_PENDING=4;
function releaseDetachedInput(owner){
 const state=owner?.input;
 if(!state||state.detached||(!state.busy&&!state.contact&&!state.queue.length))return;
 state.detached=true;state.queue=[];state.contact=false;
 const event=state.lastSent;if(!event)return;
 const cleanup={session:owner.session};inputCleanup=cleanup;
 cleanup.promise=(async()=>{
  // Video can close before an already-sent down reaches the native command
  // lock. Wait for that bounded request, then send its ordered release.
  try{await state.task;}catch(_){}
  if(inputSession!==cleanup.session||!carplayActive)return;
  try{await api('touch',{x:event.x,y:event.y,down:false,session:cleanup.session});}
  catch(error){if(inputSession===cleanup.session){nativeStats.inputErrors++;inputError='Touch release interrupted: '+error.message;renderStatus();}}
 })().finally(()=>{if(inputCleanup===cleanup)inputCleanup=null;});
}
function startInputPump(owner){owner.input.task=pumpInput(owner);inputQueue=owner.input.task;}
function inputDepth(owner){if(current(owner))nativeStats.inputQueued=owner.input.queue.length+(owner.input.busy?1:0);}
async function pumpInput(owner){
 const state=owner.input;if(state.busy)return;state.busy=true;inputDepth(owner);
 try{
  while(current(owner)&&state.queue.length){
   const event=state.queue.shift();state.lastSent=event;inputDepth(owner);
   try{await api('touch',{x:event.x,y:event.y,down:event.down,session:owner.session});if(current(owner)){nativeStats.inputSent++;inputError='';}}
   catch(error){
    if(!current(owner))break;
    nativeStats.inputErrors++;state.queue=[];state.contact=false;pointer=null;
    inputError='Touch input interrupted: '+error.message;renderStatus();
    // A timed-out request may already have reached the phone. One bounded,
    // generation-bound release clears that contact without ending the stream.
    try{await api('touch',{x:event.x,y:event.y,down:false,session:owner.session});if(current(owner))nativeStats.inputSent++;}catch(_){}
    break;
   }
  }
 }finally{state.busy=false;inputDepth(owner);if(current(owner)&&state.queue.length)startInputPump(owner);}
}
function send(x,y,down,kind=null){
 const owner=videoConnection;if(!current(owner)||inputCleanup?.session===owner.session)return false;
 const state=owner.input||(owner.input={queue:[],busy:false,contact:false});
 kind=kind||(down?(state.contact?'move':'down'):'up');
 if(kind==='down'){
  if(state.contact||state.queue.length>MAX_INPUT_PENDING-2)return false;
  state.contact=true;
 }else if(kind==='move'){
  if(!state.contact)return false;
  const last=state.queue[state.queue.length-1];
  if(last?.kind==='move'){Object.assign(last,{x,y});nativeStats.inputCoalesced++;inputDepth(owner);return true;}
  if(state.queue.length>=MAX_INPUT_PENDING-1){nativeStats.inputCoalesced++;return true;}
 }else{
  if(!state.contact)return false;state.contact=false;
  if(state.queue[state.queue.length-1]?.kind==='move'){state.queue.pop();nativeStats.inputCoalesced++;}
 }
 state.queue.push({x,y,down,kind});inputDepth(owner);if(!state.busy)startInputPump(owner);return true;
}
function displayRect(){
 const r=video.getBoundingClientRect();if(r.width<=0||r.height<=0)return null;
 const isCanvas=nativeStats.renderer&&nativeStats.renderer!=='mse';
 const w=(!isCanvas&&video.videoWidth)||sourceWidth,h=(!isCanvas&&video.videoHeight)||sourceHeight,scale=Math.min(r.width/w,r.height/h);
 return {left:r.left+(r.width-w*scale)/2,top:r.top+(r.height-h*scale)/2,width:w*scale,height:h*scale};
}
function positionControlsToggle(){
 const tab=document.querySelector('#exitFull'),r=displayRect();if(!tab||!r)return;
 // Follow the contained native sidebar, below its clock/signal area. Browser
 // resizing changes presentation only; it must never restart the native session.
 tab.style.left=Math.round(r.left)+'px';tab.style.top=Math.round(r.top+r.height*.18)+'px';
 tab.style.height=Math.round(Math.min(44,Math.max(28,r.height*.055)))+'px';
}
function coordinate(e){
 const r=displayRect();if(!r)return null;
 const x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
 return x>=0&&x<=1&&y>=0&&y<=1?{x,y}:null;
}
video.onpointerdown=e=>{if(pointer!==null||closed||changingLayout||changingOutput)return;const p=coordinate(e);if(!p)return;enableSound();if(!send(p.x,p.y,true,'down'))return;pointer={id:e.pointerId,...p};(e.currentTarget||video).setPointerCapture(e.pointerId);};
video.onpointermove=e=>{if(pointer?.id!==e.pointerId)return;const p=coordinate(e);if(p){pointer={...pointer,...p};if(!window.lastMove||performance.now()-window.lastMove>40){window.lastMove=performance.now();send(p.x,p.y,true,'move');}}};
function release(e){if(pointer?.id===e.pointerId){send(pointer.x,pointer.y,false,'up');pointer=null;}}
video.onpointerup=release;video.onpointercancel=release;video.onlostpointercapture=release;
function bindCanvas(){if(canvas){for(const event of ['onpointerdown','onpointermove','onpointerup','onpointercancel','onlostpointercapture'])canvas[event]=video[event];}}
bindCanvas();
document.addEventListener('visibilitychange',()=>{if(videoConnection)videoConnection.nativeLagSince=null;});
window.addEventListener('pagehide',()=>{commandEpoch++;if(pointer)fetchDevice('/api/touch',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({...pointer,down:false,session:inputSession})}).catch(()=>{});end();});
document.querySelector('#start').onclick=async()=>{
 if(connectionBusy||changingOutput||changingLayout||!transport.diagnostics.ready)return;
 const epoch=++commandEpoch;blockedVideoSession=null;blockedVideoError='';layoutError='';end();carplayActive=false;enableSound();baseStatus='Starting native CarPlay…';renderStatus();
 try{const target=viewport(),s=await api('start',{viewport:target});if(epoch===commandEpoch){layoutSession=s.session;layoutViewport=s.requestedViewport||target;await poll();}}catch(e){if(epoch===commandEpoch)fail(e);}
};
document.querySelector('#stop').onclick=async()=>{
 if(changingOutput||changingLayout)return;
 const session=inputSession,epoch=++commandEpoch;
 try{await api('stop',{session});if(epoch!==commandEpoch)return;layoutSession=null;layoutError='';end();carplayActive=false;baseStatus='Stopped. Press Start to reconnect.';fullscreen(false);renderStatus();}
 catch(e){if(epoch===commandEpoch)fail(e);}
};
function fullscreen(enabled){positionControlsToggle();document.body.classList[enabled?'add':'remove']('full');document.querySelector('#exitFull')?.setAttribute('aria-expanded',String(!enabled));}
document.querySelector('#full').onclick=()=>{fullscreen(true);document.querySelector('#exitFull').focus?.({preventScroll:true});};document.querySelector('#exitFull').onclick=()=>{fullscreen(false);document.querySelector('#full').focus?.({preventScroll:true});};
window.addEventListener('resize',positionControlsToggle);
const fitViewport=document.querySelector('#fitViewport');if(fitViewport)fitViewport.onclick=async()=>{if(changingLayout||changingOutput||!carplayActive||!inputSession)return;layoutSession=inputSession;layoutViewport=null;layoutError='';await reconcileLayout();};
document.querySelector('#audioOutput').onchange=async()=>{
 const selected=document.querySelector('#audioOutput').value;
 if(changingOutput||changingLayout||!['phone','browser'].includes(selected))return;
 const restart=carplayActive,session=inputSession,epoch=++commandEpoch;
 const restartViewport=layoutViewport||{width:sourceWidth,height:sourceHeight};
 changingOutput=true;audioOutput=selected;end();carplayActive=false;
 if(selected==='browser')enableSound();
 baseStatus=restart?'Switching audio; reconnecting CarPlay…':'Saving audio output…';renderStatus();
 try{
  if(restart){await api('stop',{session});if(epoch!==commandEpoch)return;}
  await api('audio_output',{mode:selected});if(epoch!==commandEpoch)return;
  if(restart){const target=restartViewport,s=await api('start',{viewport:target});if(epoch!==commandEpoch)return;layoutSession=s.session;layoutViewport=s.requestedViewport||target;}
 }catch(e){if(epoch===commandEpoch){baseStatus=e.message;renderStatus();}}
 finally{changingOutput=false;if(epoch===commandEpoch)await poll();renderStatus();}
};
document.querySelector('#sound').onclick=async()=>{
 if(audioOutput!=='browser')return;
 const a=CarDashAudio.stats;
 const retry=Boolean(audioError||(carplayActive?a.error:''))||(carplayActive&&(a.connectionState==='disconnected'||a.connectionState==='idle'));
 if(retry){audioEpoch++;CarDashAudio.stop();const allowed=await enableSound();if(allowed&&inputSession){const pending=connectSound(inputSession);renderStatus();await pending;}}
 else if(a.contextState!=='running'||!a.enabled){const allowed=await enableSound();if(allowed&&inputSession)await connectSound(inputSession);}
 else CarDashAudio.muteToggle();
 renderStatus();
};
let polling=false;
let lastMetrics=-Infinity;
function browserMetrics(){
 const now=performance.now();if(now-lastMetrics<15000)return undefined;lastMetrics=now;
 const rect=video.getBoundingClientRect(),quality=video.getVideoPlaybackQuality?.();
 const isMse=nativeStats.renderer==='mse',stats=videoConnection?.renderer?.stats||{};
 return {width:Math.round(rect.width),height:Math.round(rect.height),decodedFrames:isMse?nativeStats.decodedFrames:stats.decodedFrames??nativeStats.decodedFrames,presentedFrames:nativeStats.presentedFrames||0,canvasDrawCalls:isMse?0:nativeStats.presentedFrames||0,droppedFrames:isMse?quality?.droppedVideoFrames||0:stats.droppedFrames||0,currentTime:isMse?video.currentTime:nativeStats.mediaTime||0,paused:isMse?video.paused:closed,hidden:Boolean(document.hidden),readyState:isMse?video.readyState:nativeStats.presentedFrames?4:0,mediaError:isMse?video.error?.code||0:0,videoErrors:nativeStats.videoErrors,frameAgeMs:Math.max(0,now-lastFrameAt),decoderQueueSize:stats.decodeQueueSize||0,secureContext:!!window.isSecureContext,webCodecs:typeof VideoDecoder==='function',webGL:typeof WebGLRenderingContext==='function',webGPU:typeof navigator!=='undefined'&&!!navigator.gpu,renderer:nativeStats.renderer||'unavailable',browserInstance:transport.diagnostics.browserInstance||'',heartbeatRttMs:nativeStats.heartbeatRttMs,statusRttMs:nativeStats.statusRttMs,inputRttMs:nativeStats.inputRttMs,inputQueued:nativeStats.inputQueued,inputCoalesced:nativeStats.inputCoalesced,inputErrors:nativeStats.inputErrors,heartbeatErrors:nativeStats.heartbeatErrors,videoRetries:nativeStats.videoRetries,streamLagMs:nativeStats.streamLagMs,streamRecoveries:nativeStats.streamRecoveries};
}
let heartbeatRequest=null;
async function heartbeat(){
 if(heartbeatRequest||!carplayActive||!inputSession||changingLayout||changingOutput||!transport.diagnostics.ready)return;
 const request={session:inputSession};heartbeatRequest=request;
 try{await api('heartbeat',{session:request.session,browser:browserMetrics(),link:{heartbeatRttMs:nativeStats.heartbeatRttMs,streamLagMs:nativeStats.streamLagMs,hidden:Boolean(document.hidden),frameReady:!!(current(videoConnection)&&nativeStats.decodedFrames>0)}});}
 catch(error){if(inputSession===request.session&&carplayActive){nativeStats.heartbeatErrors++;}}
 finally{if(heartbeatRequest===request)heartbeatRequest=null;}
}
async function poll(){
 if(hosted&&!transport.diagnostics.ready){if(!closed)end();identityReady=false;carplayActive=false;renderStatus();return;}
 if(polling||connectionBusy||changingOutput||changingLayout)return;polling=true;const epoch=commandEpoch;
 try{
  const statusRequestedAt=performance.now(),s=await requestJSON('/api/status');if(epoch!==commandEpoch)return;identityReady=!!s.identityReady;continuousDecodeSupported=s.videoContinuousDecode===true;
  const output=s.audioOutput==='browser'?'browser':'phone';
  if(output!==audioOutput){audioOutput=output;audioEpoch++;audioError='';CarDashAudio.stop();}
  document.querySelector('#audioOutput').value=audioOutput;
  document.querySelector('#start').disabled=s.active||!s.identityReady;document.querySelector('#stop').disabled=!s.active;
  if(s.active){
   if(typeof s.session!=='string'||!s.session)throw new Error('Native session identity is missing');
   if(inputSession!==s.session){end();inputSession=s.session;audioError='';if(layoutSession!==s.session){layoutSession=null;layoutViewport=s.requestedViewport||null;}}
   sourceWidth=s.actualSource?.width||s.sourceWidth||1280;sourceHeight=s.actualSource?.height||s.sourceHeight||720;positionControlsToggle();
   carplayActive=true;const session=s.session;
   // Decoder output and canvas draw calls are distinct; neither proves that
   // a vehicle physically presented the pixels. Preserve both for diagnosis.
   const rendererStats=videoConnection?.renderer?.stats;
   if(rendererStats){nativeStats.decodedFrames=rendererStats.decodedFrames??nativeStats.decodedFrames;nativeStats.presentedFrames=rendererStats.presentedFrames??nativeStats.presentedFrames;nativeStats.canvasDrawCalls=nativeStats.presentedFrames;}
   const ticks=Number.isSafeInteger(s.videoTimelineTicks)&&s.videoTimelineTicks>=0?s.videoTimelineTicks:0;
   nativeStats.streamLagMs=Math.max(0,ticks/90-(nativeStats.mediaTime||0)*1000);
   // iOS may stop encoding an unchanged screen. Keep its last frame and touch
   // connection; age alone is not evidence that newer pixels were lost.
   const nativeAhead=nativeStats.streamLagMs>500;
   const awaitingNativeFrame=!nativeStats.presentedFrames||nativeAhead;
   const owner=videoConnection;
   if(hosted&&current(owner)&&owner.renderer&&!document.hidden){
    const now=performance.now();
    if(nativeAhead){if(owner.nativeLagSince==null)owner.nativeLagSince=now;}else owner.nativeLagSince=null;
    const behindFor=owner.nativeLagSince==null?0:now-owner.nativeLagSince;
    // A resumed native timestamp can jump across a long idle interval before
    // its frame reaches the browser. Start the grace period at that observation.
    if(s.nativeFrames>0&&now-lastFrameAt>6000&&(!nativeStats.presentedFrames||behindFor>=6000))recoverDisplay(new Error('No fresh display frames arrived.'),owner,s.codec,'network');
    else if(nativeStats.presentedFrames>0&&nativeStats.streamLagMs>1500&&behindFor>=2000)recoverDisplay(new Error('The display fell behind the native stream.'),owner,s.codec,'lag');
   }
   heartbeat();if(epoch!==commandEpoch||session!==inputSession)return;
   const phase=!s.native?.authenticated||!s.native?.activated?'starting native session':!s.nativeFrames?'waiting for native video':!nativeStats.decodedFrames?'receiving video; waiting for browser playback':awaitingNativeFrame&&performance.now()-lastFrameAt>5000?'waiting for browser frames':'playing';
   baseStatus=(blockedVideoSession===session?blockedVideoError:'')||(streamRecovery.timer!==null?(streamRecovery.reason==='lag'?'Catching up the native display…':'Reconnecting the native display…'):'')||s.error||`Native CarPlay · ${Math.floor(s.sessionSeconds/60)}m ${s.sessionSeconds%60}s · ${phase}`;
   if(s.codec&&s.videoConnected&&closed&&blockedVideoSession!==session)connect(s.codec,session);
   if(current(videoConnection)){
    videoConnection.keyframes=Array.isArray(s.videoKeyframes)?s.videoKeyframes.slice(-32).filter(t=>Number.isSafeInteger(t)&&t>=0):[];
    videoConnection.timelineTicks=Number.isSafeInteger(s.videoTimelineTicks)&&s.videoTimelineTicks>=0?s.videoTimelineTicks:0;
    videoConnection.timelineRequestedAt=statusRequestedAt;
   }
   connectSound(session);
  }else{
   if(!closed||inputSession!==null)end();carplayActive=false;
   baseStatus=s.error||(s.identityReady?'Ready. Press Start to connect.':'Tap Prepare CarPlay in the phone app first.');
  }
  renderStatus();
 }catch(e){if(epoch===commandEpoch){baseStatus='iPhone connection unavailable: '+e.message;renderStatus();}}
 finally{polling=false;}
}
if(hosted){
 const panel=document.querySelector('#connectionPanel'),input=document.querySelector('#endpoint'),button=document.querySelector('#connect');
 if(panel)panel.hidden=false;if(input)input.value=transport.diagnostics.endpoint;
 const label=document.querySelector('#buildLabel');if(label)label.textContent='CarDash V3 · HTTPS3 beta · Viewer 2';
 baseStatus='Connect to your iPhone to use the H.264 canvas renderer.';
 if(button)button.onclick=async()=>{
  if(connectionBusy||changingOutput||changingLayout)return;
  const epoch=++commandEpoch;end();carplayActive=false;identityReady=false;blockedVideoSession=null;blockedVideoError='';
  if(typeof CarDashCanvas==='undefined'||!CarDashCanvas.available()){baseStatus='This browser does not support secure H.264 canvas decoding. No local connection was attempted.';renderStatus();return;}
  connectionBusy=true;baseStatus='Connecting directly to your iPhone…';renderStatus();
  try{await transport.connect(input.value);if(epoch===commandEpoch){connectionBusy=false;await poll();}}
  catch(error){if(epoch===commandEpoch)baseStatus=error.message;}
  finally{connectionBusy=false;renderStatus();}
 };
 renderStatus();
}
// In hosted mode poll() is inert until the user's Connect gesture succeeds.
setInterval(heartbeat,2000);setInterval(poll,2000);poll();
