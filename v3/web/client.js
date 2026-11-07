// Native iPhone video and HID input. No simulated dashboard or frame fallback.
const video=document.querySelector('video'),status=document.querySelector('#status');
window.nativeStats={decodedFrames:0,inputSent:0,trims:0};
let inputSession=null;
let buffer,queue=[],bytes=0,closed=true,inputQueue=Promise.resolve(),pointer=null,abort,connecting=false;
async function api(action,body={}){const r=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await r.json();if(!r.ok)throw new Error(value.error||'Request failed');return value;}
function end(){closed=true;abort?.abort();queue=[];bytes=0;pointer=null;document.body.classList.remove('live');}
function fail(e){end();status.textContent=e.message;}
function append(){if(!buffer||buffer.updating||!queue.length||closed)return;const b=queue.shift();bytes-=b.byteLength;try{buffer.appendBuffer(b);}catch(e){fail(e);}}
function live(){if(video.buffered.length){const end=video.buffered.end(video.buffered.length-1);if(video.currentTime<video.buffered.start(0)||end-video.currentTime>1)video.currentTime=Math.max(video.buffered.start(0),end-.15);if(video.paused)video.play().catch(()=>{});}}
async function connect(codec){if(connecting||!closed)return;connecting=true;closed=false;abort=new AbortController();window.nativeStats={decodedFrames:0,inputSent:0,trims:0};
 try{const media=new MediaSource(),url=URL.createObjectURL(media);video.src=url;await new Promise(r=>media.addEventListener('sourceopen',r,{once:true}));URL.revokeObjectURL(url);
 buffer=media.addSourceBuffer(`video/mp4; codecs="${codec}"`);buffer.addEventListener('updateend',()=>{live();if(buffer.buffered.length&&video.currentTime-buffer.buffered.start(0)>8){nativeStats.trims++;buffer.remove(buffer.buffered.start(0),video.currentTime-3);return;}append();});buffer.addEventListener('error',()=>fail(new Error('Video decoder error; reconnect the preview.')));
 const response=await fetch('/video',{signal:abort.signal});if(!response.ok)throw new Error('Native video is not ready');const reader=response.body.getReader();document.body.classList.add('live');
 video.requestVideoFrameCallback(function frame(_,meta){nativeStats.decodedFrames=meta.presentedFrames;nativeStats.mediaTime=meta.mediaTime;if(!closed)video.requestVideoFrameCallback(frame);});
 connecting=false;
 for(;;){const {value,done}=await reader.read();if(done)throw new Error('Native session ended');bytes+=value.byteLength;if(bytes>4*1024*1024)throw new Error('Viewer fell behind; reconnect.');queue.push(value);append();}
 }catch(e){if(e.name!=='AbortError')fail(e);}finally{connecting=false;}}
function send(x,y,down){const session=inputSession;inputQueue=inputQueue.then(async()=>{await api('touch',{x,y,down,session});nativeStats.inputSent++;}).catch(fail);}
function coordinate(e){const r=video.getBoundingClientRect(),scale=Math.min(r.width/1280,r.height/720),w=1280*scale,h=720*scale,x=(e.clientX-r.left-(r.width-w)/2)/w,y=(e.clientY-r.top-(r.height-h)/2)/h;return x>=0&&x<=1&&y>=0&&y<=1?{x,y}:null;}
video.onpointerdown=e=>{if(pointer!==null||closed)return;const p=coordinate(e);if(!p)return;pointer={id:e.pointerId,...p};video.setPointerCapture(e.pointerId);send(p.x,p.y,true);};
video.onpointermove=e=>{if(pointer?.id!==e.pointerId)return;const p=coordinate(e);if(p){pointer={...pointer,...p};if(!window.lastMove||performance.now()-window.lastMove>40){window.lastMove=performance.now();send(p.x,p.y,true);}}};
function release(e){if(pointer?.id===e.pointerId){send(pointer.x,pointer.y,false);pointer=null;}}
video.onpointerup=release;video.onpointercancel=release;
window.addEventListener('pagehide',()=>{if(pointer)fetch('/api/touch',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({...pointer,down:false,session:inputSession})}).catch(()=>{});abort?.abort();});
document.querySelector('#start').onclick=async()=>{try{end();status.textContent='Starting native CarPlay…';await api('start');await poll();}catch(e){fail(e);}};
document.querySelector('#stop').onclick=async()=>{try{await api('stop',{session:inputSession});end();status.textContent='Stopped. Press Start for another trial.';}catch(e){fail(e);}};
document.querySelector('#full').onclick=()=>document.body.classList.add('full');document.querySelector('#exitFull').onclick=()=>document.body.classList.remove('full');
let polling=false;async function poll(){if(polling)return;polling=true;try{const s=await (await fetch('/api/status')).json();document.querySelector('#start').disabled=s.active||!s.identityReady;document.querySelector('#stop').disabled=!s.active;
 if(s.active){inputSession=s.session;await api('heartbeat',{session:s.session});status.textContent=s.error||`Native CarPlay · ${s.secondsRemaining}s left · video/touch preview`;if(s.codec&&s.videoConnected&&closed)connect(s.codec);}
 else {if(!closed)end();status.textContent=s.error||(s.identityReady?'Ready. Press Start for a five-minute trial.':'Prepare Native Preview in the phone app first.');}
 }catch(e){status.textContent='iPhone connection unavailable: '+e.message;}finally{polling=false;}}
setInterval(poll,2000);poll();
