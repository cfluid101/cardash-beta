// Native iPhone video and HID input. No simulated dashboard or frame fallback.
const video=document.querySelector('video'),status=document.querySelector('#status');
window.nativeStats={decodedFrames:0,inputSent:0,trims:0,videoConnections:0,videoErrors:0,lastVideoError:'',lastVideoErrorTime:null,lastVideoErrorDetails:null};
let inputSession=null,videoConnection=null,commandEpoch=0,audioEpoch=0,carplayActive=false;
let baseStatus='Connecting to iPhone…',audioError='';
// Keep these aliases for the diagnostic browser harness; each connection owns
// the actual buffers so delayed callbacks cannot modify a replacement stream.
let buffer,queue=[],bytes=0,closed=true,inputQueue=Promise.resolve(),pointer=null,abort,connecting=false;
async function api(action,body={}){const r=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await r.json();if(!r.ok)throw new Error(value.error||'Request failed');return value;}
function current(owner){return owner&&videoConnection===owner&&inputSession===owner.session&&!owner.abort.signal.aborted;}
function end(){
 const old=videoConnection;videoConnection=null;inputSession=null;audioEpoch++;audioError='';
 CarDashAudio.stop();closed=true;connecting=false;old?.abort.abort();
 if(old?.reader)old.reader.cancel().catch(()=>{});
 if(old?.url)URL.revokeObjectURL(old.url);
 buffer=null;queue=[];bytes=0;pointer=null;inputQueue=Promise.resolve();
 video.pause();video.removeAttribute('src');video.load();document.body.classList.remove('live');
}
function renderStatus(){
 const a=CarDashAudio.stats,button=document.querySelector('#sound');
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
 status.textContent=baseStatus+detail;
}
function enableSound(){
 audioError='';const epoch=audioEpoch;
 try{return CarDashAudio.enable().catch(e=>{if(epoch===audioEpoch){audioError=e.message;renderStatus();}return false;});}
 catch(e){if(epoch===audioEpoch){audioError=e.message;renderStatus();}return Promise.resolve(false);}
}
function connectSound(session){
 const epoch=audioEpoch,prior=CarDashAudio.stats.error;if(prior)audioError=prior;
 return CarDashAudio.connect(session).then(ready=>{
  if(session!==inputSession||epoch!==audioEpoch)return false;
  if(ready)audioError='';else if(CarDashAudio.stats.error)audioError=CarDashAudio.stats.error;
  renderStatus();return ready;
 }).catch(e=>{if(session===inputSession&&epoch===audioEpoch){audioError=e.message;renderStatus();}return false;});
}
function fail(e,owner=null){if(owner&&!current(owner))return;end();baseStatus=e.message;renderStatus();}
function failVideo(e,owner,stage){
 if(!current(owner))return;
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
async function connect(codec,session=inputSession){
 if(connecting||!closed||!session||session!==inputSession)return;
 const owner={session,abort:new AbortController(),queue:[],bytes:0,buffer:null,reader:null,url:null,phase:'sourceopen'};
 videoConnection=owner;connecting=true;closed=false;abort=owner.abort;queue=owner.queue;bytes=0;buffer=null;
 Object.assign(nativeStats,{decodedFrames:0,inputSent:0,trims:0});nativeStats.videoConnections++;
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
    if(owner.buffer.buffered.length&&video.currentTime-owner.buffer.buffered.start(0)>8){nativeStats.trims++;owner.buffer.remove(owner.buffer.buffered.start(0),video.currentTime-3);return;}
    append(owner);
   }catch(e){failVideo(e,owner,'updateend');}
  });
  owner.buffer.addEventListener('error',()=>failVideo(new Error('Video decoder error; reconnect the preview.'),owner,'source-buffer-error'));
  owner.phase='video-request';
  const response=await fetch('/video',{signal:owner.abort.signal,headers:{'X-CarDash-Session':session}});
  if(!current(owner))return;if(!response.ok||!response.body)throw new Error('Native video is not ready ('+response.status+')');
  owner.phase='video-stream';owner.reader=response.body.getReader();document.body.classList.add('live');
  video.requestVideoFrameCallback(function frame(_,meta){if(!current(owner))return;nativeStats.decodedFrames=meta.presentedFrames;nativeStats.mediaTime=meta.mediaTime;video.requestVideoFrameCallback(frame);});
  connecting=false;
  for(;;){
   const {value,done}=await owner.reader.read();if(!current(owner))break;if(done)throw new Error('Native session ended');
   owner.bytes+=value.byteLength;if(owner.bytes>4*1024*1024)throw new Error('Viewer fell behind; reconnect.');
   bytes=owner.bytes;owner.queue.push(value);append(owner);
  }
 }catch(e){if(e.name!=='AbortError')failVideo(e,owner);}
 finally{if(owner.url)URL.revokeObjectURL(owner.url);if(current(owner))connecting=false;}
}
function send(x,y,down){
 const session=inputSession,owner=videoConnection;
 inputQueue=inputQueue.then(async()=>{
  if(!current(owner)||session!==inputSession)return;
  await api('touch',{x,y,down,session});if(current(owner))nativeStats.inputSent++;
 }).catch(e=>{if(current(owner))fail(e,owner);});
}
function coordinate(e){const r=video.getBoundingClientRect(),scale=Math.min(r.width/1280,r.height/720),w=1280*scale,h=720*scale,x=(e.clientX-r.left-(r.width-w)/2)/w,y=(e.clientY-r.top-(r.height-h)/2)/h;return x>=0&&x<=1&&y>=0&&y<=1?{x,y}:null;}
video.onpointerdown=e=>{if(pointer!==null||closed)return;const p=coordinate(e);if(!p)return;enableSound();pointer={id:e.pointerId,...p};video.setPointerCapture(e.pointerId);send(p.x,p.y,true);};
video.onpointermove=e=>{if(pointer?.id!==e.pointerId)return;const p=coordinate(e);if(p){pointer={...pointer,...p};if(!window.lastMove||performance.now()-window.lastMove>40){window.lastMove=performance.now();send(p.x,p.y,true);}}};
function release(e){if(pointer?.id===e.pointerId){send(pointer.x,pointer.y,false);pointer=null;}}
video.onpointerup=release;video.onpointercancel=release;
window.addEventListener('pagehide',()=>{commandEpoch++;if(pointer)fetch('/api/touch',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({...pointer,down:false,session:inputSession})}).catch(()=>{});end();});
document.querySelector('#start').onclick=async()=>{
 const epoch=++commandEpoch;end();carplayActive=false;enableSound();baseStatus='Starting native CarPlay…';renderStatus();
 try{await api('start');if(epoch===commandEpoch)await poll();}catch(e){if(epoch===commandEpoch)fail(e);}
};
document.querySelector('#stop').onclick=async()=>{
 const session=inputSession,epoch=++commandEpoch;
 try{await api('stop',{session});if(epoch!==commandEpoch)return;end();carplayActive=false;baseStatus='Stopped. Press Start to reconnect.';renderStatus();}
 catch(e){if(epoch===commandEpoch)fail(e);}
};
document.querySelector('#full').onclick=()=>document.body.classList.add('full');document.querySelector('#exitFull').onclick=()=>document.body.classList.remove('full');
document.querySelector('#sound').onclick=async()=>{
 const a=CarDashAudio.stats;
 const retry=Boolean(audioError||(carplayActive?a.error:''))||(carplayActive&&(a.connectionState==='disconnected'||a.connectionState==='idle'));
 if(retry){audioEpoch++;CarDashAudio.stop();const allowed=await enableSound();if(allowed&&inputSession){const pending=connectSound(inputSession);renderStatus();await pending;}}
 else if(a.contextState!=='running'||!a.enabled){const allowed=await enableSound();if(allowed&&inputSession)await connectSound(inputSession);}
 else CarDashAudio.muteToggle();
 renderStatus();
};
let polling=false;
async function poll(){
 if(polling)return;polling=true;const epoch=commandEpoch;
 try{
  const response=await fetch('/api/status');if(!response.ok)throw new Error('Status request failed ('+response.status+')');
  const s=await response.json();if(epoch!==commandEpoch)return;
  document.querySelector('#start').disabled=s.active||!s.identityReady;document.querySelector('#stop').disabled=!s.active;
  if(s.active){
   if(typeof s.session!=='string'||!s.session)throw new Error('Native session identity is missing');
   if(inputSession!==s.session){end();inputSession=s.session;audioError='';}
   carplayActive=true;const session=s.session;
   await api('heartbeat',{session});if(epoch!==commandEpoch||session!==inputSession)return;
   baseStatus=s.error||`Native CarPlay · ${Math.floor(s.sessionSeconds/60)}m ${s.sessionSeconds%60}s · connected`;
   if(s.codec&&s.videoConnected&&closed)connect(s.codec,session);
   connectSound(session);
  }else{
   if(!closed||inputSession!==null)end();carplayActive=false;
   baseStatus=s.error||(s.identityReady?'Ready. Press Start to connect.':'Tap Prepare CarPlay in the phone app first.');
  }
  renderStatus();
 }catch(e){if(epoch===commandEpoch){baseStatus='iPhone connection unavailable: '+e.message;renderStatus();}}
 finally{polling=false;}
}
setInterval(poll,2000);poll();
