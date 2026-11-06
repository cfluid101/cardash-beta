// Native, authenticated video only. No synthetic fallback.
const token=location.hash.slice(1),headers={'X-CarDash-Research-Token':token};
const video=document.querySelector('video'),status=document.querySelector('#status');
window.nativeStats={decodedFrames:0,inputSent:0,trims:0};
let buffer,queue=[],bytes=0,closed=false,inputQueue=Promise.resolve(),pointer=null;
const abort=new AbortController();
function fail(e){closed=true;abort.abort();status.textContent=e.message;}
function append(){if(!buffer||buffer.updating||!queue.length||closed)return;const b=queue.shift();bytes-=b.byteLength;try{buffer.appendBuffer(b);}catch(e){fail(e);}}
function live(){if(video.buffered.length){const end=video.buffered.end(video.buffered.length-1);if(video.currentTime<video.buffered.start(0)||end-video.currentTime>1)video.currentTime=Math.max(video.buffered.start(0),end-.15);if(video.paused)video.play().catch(()=>{});}}
(async()=>{try{
 const state=await fetch('/status',{headers}).then(r=>r.json());if(!state.codec)throw new Error('Native video is not ready');
 const media=new MediaSource();video.src=URL.createObjectURL(media);await new Promise(r=>media.addEventListener('sourceopen',r,{once:true}));
 buffer=media.addSourceBuffer(`video/mp4; codecs="${state.codec}"`);buffer.addEventListener('updateend',()=>{live();if(buffer.buffered.length&&video.currentTime-buffer.buffered.start(0)>8){window.nativeStats.trims++;buffer.remove(buffer.buffered.start(0),video.currentTime-3);return;}append();});
 const response=await fetch('/video',{headers,signal:abort.signal});if(!response.ok)throw new Error('Native video unavailable');const reader=response.body.getReader();
 video.requestVideoFrameCallback(function frame(_,meta){window.nativeStats.decodedFrames=meta.presentedFrames;window.nativeStats.mediaTime=meta.mediaTime;status.textContent=`Live · ${meta.presentedFrames} decoded frames`;if(!closed)video.requestVideoFrameCallback(frame);});
 for(;;){const {value,done}=await reader.read();if(done)throw new Error('Native session ended');bytes+=value.byteLength;if(bytes>4*1024*1024)throw new Error('Viewer fell behind');queue.push(value);append();}
 }catch(e){fail(e);}})();
function send(x,y,down){inputQueue=inputQueue.then(async()=>{const r=await fetch('/touch',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({x,y,down})});if(!r.ok)throw new Error('Native input rejected');window.nativeStats.inputSent++;}).catch(fail);}
function coordinate(e){const r=video.getBoundingClientRect(),scale=Math.min(r.width/1280,r.height/720),w=1280*scale,h=720*scale,x=(e.clientX-r.left-(r.width-w)/2)/w,y=(e.clientY-r.top-(r.height-h)/2)/h;return x>=0&&x<=1&&y>=0&&y<=1?{x,y}:null;}
video.onpointerdown=e=>{if(pointer!==null||closed)return;const p=coordinate(e);if(!p)return;pointer={id:e.pointerId,...p};video.setPointerCapture(e.pointerId);send(p.x,p.y,true);};
video.onpointermove=e=>{if(pointer?.id!==e.pointerId)return;const p=coordinate(e);if(p){pointer={...pointer,...p};if(!window.lastMove||performance.now()-window.lastMove>40){window.lastMove=performance.now();send(p.x,p.y,true);}}};
function release(e){if(pointer?.id===e.pointerId){send(pointer.x,pointer.y,false);pointer=null;}}
video.onpointerup=release;video.onpointercancel=release;window.addEventListener('pagehide',()=>{if(pointer)fetch('/touch',{method:'POST',keepalive:true,headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({...pointer,down:false})}).catch(()=>{});abort.abort();});
