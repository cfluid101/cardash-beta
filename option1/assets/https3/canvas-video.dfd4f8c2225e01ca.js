// SPDX-License-Identifier: GPL-3.0-only
// Native CarPlay AVC frames only. This parser accepts the bounded, single-track
// fragmented MP4 emitted by backend/media.py; it is not a general MP4 player.
(function(global){
 'use strict';
 const MAX_BYTES=4*1024*1024,MAX_QUEUE=8,WAIT_MS=2000;
 const need=(value,message)=>{if(!value)throw new Error(message);};
 const u32=(data,at)=>{need(at>=0&&at+4<=data.length,'Truncated MP4 field');return new DataView(data.buffer,data.byteOffset+at,4).getUint32(0);};
 const u16=(data,at)=>{need(at>=0&&at+2<=data.length,'Truncated MP4 field');return new DataView(data.buffer,data.byteOffset+at,2).getUint16(0);};
 const kind=(data,at)=>String.fromCharCode(...data.subarray(at,at+4));
 function boxes(data){
  const result=[];let at=0;
  while(at<data.length){
   need(result.length<128&&at+8<=data.length,'Invalid MP4 child boxes');
   const size=u32(data,at);need(size>=8&&size<=MAX_BYTES&&size<=data.length-at,'Invalid MP4 box size');
   result.push({type:kind(data,at+4),data:data.subarray(at+8,at+size),size});at+=size;
  }
  return result;
 }
 function one(items,type){const found=items.filter(v=>v.type===type);need(found.length===1,'Expected one MP4 '+type);return found[0];}
 function full(data,version,flags){need(data.length>=4&&data[0]===version&&u32(data,0)%16777216===flags,'Unsupported MP4 full box');}
 function avcDescription(data,codec){
  need(data.length>=9&&data.length<=65536&&data[0]===1&&(data[4]&3)===3,'Invalid AVC configuration');
  const actual='avc1.'+Array.from(data.subarray(1,4),x=>x.toString(16).padStart(2,'0')).join('');
  need(actual.toLowerCase()===codec.toLowerCase(),'AVC codec does not match native status');
  let at=6;
  for(const type of [7,8]){
   need(at<=data.length,'Truncated AVC parameter sets');
   const count=type===7?data[5]&31:data[at++];need(count>0&&count<=31,'Missing AVC parameter sets');
   for(let i=0;i<count;i++){
    const length=u16(data,at);at+=2;need(length>0&&at+length<=data.length&&(data[at]&31)===type,'Invalid AVC parameter set');at+=length;
   }
  }
  // High-profile avcC extensions are passed unchanged to the platform decoder.
  return data.slice();
 }
 function initDescription(data,codec,width,height){
  const children=boxes(data),track=one(children,'trak'),trackBoxes=boxes(track.data);
  const tkhd=one(trackBoxes,'tkhd').data;full(tkhd,0,7);need(u32(tkhd,12)===1,'Unsupported MP4 track');
  const mdia=boxes(one(trackBoxes,'mdia').data),mdhd=one(mdia,'mdhd').data;full(mdhd,0,0);need(u32(mdhd,12)===90000,'Unsupported video timescale');
  const handler=one(mdia,'hdlr').data;need(handler.length>=12&&kind(handler,8)==='vide','Expected video track');
  const minf=boxes(one(mdia,'minf').data),stbl=boxes(one(minf,'stbl').data),stsd=one(stbl,'stsd').data;
  full(stsd,0,0);need(u32(stsd,4)===1,'Expected one video sample entry');
  const entries=boxes(stsd.subarray(8));need(entries.length===1&&entries[0].type==='avc1','Unsupported video sample entry');
  const sample=entries[0].data;need(sample.length>=78,'Truncated AVC sample entry');
  need(u16(sample,24)===width&&u16(sample,26)===height,'Native video dimensions do not match display');
  return avcDescription(one(boxes(sample.subarray(78)),'avcC').data,codec);
 }
 function fragmentDescription(data,moofSize){
  const top=boxes(data),mfhd=one(top,'mfhd').data;full(mfhd,0,0);need(mfhd.length===8,'Invalid MP4 fragment sequence');
  const track=boxes(one(top,'traf').data),tfhd=one(track,'tfhd').data;full(tfhd,0,0x020000);need(tfhd.length===8&&u32(tfhd,4)===1,'Unsupported fragment track');
  const tfdt=one(track,'tfdt').data;full(tfdt,1,0);need(tfdt.length===12,'Invalid decode timestamp');
  const ticks=(BigInt(u32(tfdt,4))<<32n)+BigInt(u32(tfdt,8));
  const trun=one(track,'trun').data;full(trun,0,0x000f01);need(trun.length===28&&u32(trun,4)===1,'Expected one video sample');
  need(u32(trun,8)===moofSize+8,'Invalid video sample offset');
  const duration=u32(trun,12),size=u32(trun,16),flags=u32(trun,20),offset=u32(trun,24);
  need(duration>0&&duration<=54000000&&size>4&&size<=MAX_BYTES-8,'Invalid video sample size or duration');
  need(flags===0x02000000||flags===0x01010000,'Unsupported video sample flags');
  const timestamp=(ticks+BigInt(offset))*1000000n/90000n;
  need(timestamp<=BigInt(Number.MAX_SAFE_INTEGER),'Video timestamp exceeds safe range');
  return {size,key:flags===0x02000000,timestamp:Number(timestamp),duration:Math.max(1,Math.round(duration*1000000/90000))};
 }
 function isIdr(data){
  let at=0,key=false;
  while(at<data.length){
   const length=u32(data,at);at+=4;need(length>0&&length<=data.length-at,'Invalid AVC NAL length');
   const type=data[at]&31;need(type>=1&&type<=23,'Invalid AVC NAL type');if(type===5)key=true;at+=length;
  }
  return key;
 }
 function renderer(canvas,width,height){
  canvas.width=width;canvas.height=height;if(canvas.style)canvas.style.objectFit='contain';
  const attributes={alpha:false,antialias:false,depth:false,stencil:false,preserveDrawingBuffer:false};
  const gl=canvas.getContext('webgl',attributes);
  if(!gl){
   const ctx=canvas.getContext('2d',{alpha:false});need(ctx,'No canvas rendering context is available');
   return {name:'canvas2d',draw(frame){ctx.drawImage(frame,0,0,width,height);},close(){}};
  }
  const resources=[];
  function shader(type,source){const s=gl.createShader(type);need(s,'Cannot create canvas shader');resources.push(['deleteShader',s]);gl.shaderSource(s,source);gl.compileShader(s);need(gl.getShaderParameter(s,gl.COMPILE_STATUS),'Canvas shader compilation failed');return s;}
  function cleanup(){for(const [method,value] of resources.splice(0))gl[method](value);}
  try{
   const vs=shader(gl.VERTEX_SHADER,'attribute vec2 p;attribute vec2 t;varying vec2 uv;void main(){gl_Position=vec4(p,0.,1.);uv=t;}');
   const fs=shader(gl.FRAGMENT_SHADER,'precision mediump float;varying vec2 uv;uniform sampler2D image;void main(){gl_FragColor=texture2D(image,uv);}');
   const program=gl.createProgram();need(program,'Cannot create canvas program');resources.push(['deleteProgram',program]);gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);need(gl.getProgramParameter(program,gl.LINK_STATUS),'Canvas shader link failed');gl.useProgram(program);
   for(const [name,data] of [['p',[-1,-1,1,-1,-1,1,1,1]],['t',[0,1,1,1,0,0,1,0]]]){
    const b=gl.createBuffer();need(b,'Cannot create canvas buffer');resources.push(['deleteBuffer',b]);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);const location=gl.getAttribLocation(program,name);need(location>=0,'Canvas shader attribute unavailable');gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,2,gl.FLOAT,false,0,0);
   }
   const texture=gl.createTexture();need(texture,'Cannot create canvas texture');resources.push(['deleteTexture',texture]);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);
   for(const key of [gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER])gl.texParameteri(gl.TEXTURE_2D,key,gl.LINEAR);
   for(const key of [gl.TEXTURE_WRAP_S,gl.TEXTURE_WRAP_T])gl.texParameteri(gl.TEXTURE_2D,key,gl.CLAMP_TO_EDGE);
   gl.uniform1i(gl.getUniformLocation(program,'image'),0);gl.viewport(0,0,width,height);gl.clearColor(0,0,0,1);
   return {name:'webgl',draw(frame){need(!gl.isContextLost(),'Canvas graphics context was lost');gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,frame);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);},close:cleanup};
  }catch(error){cleanup();throw error;}
 }
 function available(){return global.isSecureContext===true&&typeof global.VideoDecoder==='function'&&typeof global.EncodedVideoChunk==='function';}
 function create({canvas,codec,width,height,onFrame=()=>{},onError=()=>{}}){
  need(available(),'WebCodecs requires a secure browser context with VideoDecoder support');
  need(canvas&&typeof canvas.getContext==='function','A canvas is required');
  need(Number.isInteger(width)&&Number.isInteger(height)&&width>=2&&height>=2&&width<=4096&&height<=4096&&width*height<=4194304,'Invalid native display dimensions');
  need(typeof codec==='string'&&/^avc1\.[0-9a-f]{6}$/i.test(codec),'Invalid AVC codec');
  const paint=renderer(canvas,width,height);
  let buffer=new Uint8Array(0),pendingSample=null,seenFtyp=false,seenMoov=false,config=null,decoder=null,closed=false,failed=false;
  let awaitingKey=true,pendingFrame=null,renderTimer=null,lastPaint=-Infinity;
  let pushTail=Promise.resolve(),queuedInputBytes=0,queuedInputs=0,sampleBytes=0;
  const waits=new Set();
  const count={receivedFrames:0,submittedFrames:0,decodedFrames:0,presentedFrames:0,droppedFrames:0,droppedEncodedFrames:0,closedFrames:0,resets:0,error:'',lastTimestamp:null};
  function closeFrame(frame){try{frame.close();}finally{count.closedFrames++;}}
  function close(){
   if(closed)return;closed=true;
   for(const cancel of [...waits])cancel();
   if(renderTimer!==null){clearTimeout(renderTimer);renderTimer=null;}
   if(pendingFrame){closeFrame(pendingFrame);pendingFrame=null;}
   queuedInputBytes=0;queuedInputs=0;sampleBytes=0;buffer=new Uint8Array(0);pendingSample=null;
   const old=decoder;decoder=null;if(old&&old.state!=='closed')old.close();
   canvas.removeEventListener?.('webglcontextlost',contextLost);paint.close();
  }
  function fail(error){if(closed||failed)return;failed=true;count.error=error?.message||String(error);close();onError(error instanceof Error?error:new Error(count.error));}
  function contextLost(event){event.preventDefault?.();fail(new Error('Canvas graphics context was lost; reconnect.'));}
  canvas.addEventListener?.('webglcontextlost',contextLost);
  // Configuration and capacity waits must unblock at close, even if a browser
  // decoder never settles its own promise or emits another event.
  function waitFor(operation,message,code){
   if(closed)return Promise.reject(new Error('Native canvas closed'));
   return new Promise((resolve,reject)=>{
    let settled=false,timer=null;
    const finish=(error,value)=>{if(settled)return;settled=true;if(timer!==null)clearTimeout(timer);waits.delete(cancel);error?reject(error):resolve(value);};
    const cancel=()=>finish(new Error('Native canvas closed'));
    waits.add(cancel);timer=setTimeout(()=>finish(Object.assign(new Error(message),{code})),WAIT_MS);
    Promise.resolve(operation).then(value=>finish(null,value),error=>finish(error));
   });
  }
  async function capacity(instance){
   if(instance.decodeQueueSize<MAX_QUEUE)return;
   need(typeof instance.addEventListener==='function','Native decoder cannot report available capacity');
   let ready;
   const available=new Promise(resolve=>{ready=()=>{if(instance.decodeQueueSize<MAX_QUEUE)resolve();};instance.addEventListener('dequeue',ready);ready();});
   try{await waitFor(available,'Native decoder stalled for 2 seconds; reconnecting display.','DECODER_STALLED');}
   finally{instance.removeEventListener('dequeue',ready);}
  }
  function render(){
   renderTimer=null;const frame=pendingFrame;pendingFrame=null;if(!frame)return;
   try{
    if(closed)return;
    if(frame.timestamp<=lastPaint){count.droppedFrames++;return;}
    paint.draw(frame);lastPaint=frame.timestamp;count.presentedFrames++;count.lastTimestamp=frame.timestamp;
    onFrame({presentedFrames:count.presentedFrames,decodedFrames:count.decodedFrames,timestamp:frame.timestamp,width,height,renderer:paint.name});
   }catch(error){fail(error);}finally{closeFrame(frame);}
  }
  function newDecoder(){
   const old=decoder;decoder=null;if(old&&old.state!=='closed')old.close();
   let instance;
   instance=new global.VideoDecoder({
    output(frame){
     if(closed||decoder!==instance){closeFrame(frame);return;}
     try{
      need(frame.displayWidth===width&&frame.displayHeight===height,'Decoded native dimensions changed; reconnect.');
      count.decodedFrames++;
      if(pendingFrame){count.droppedFrames++;closeFrame(pendingFrame);}
      pendingFrame=frame;
      if(renderTimer===null)renderTimer=setTimeout(render,0);
     }catch(error){closeFrame(frame);fail(error);}
    },
    error(error){if(!closed&&decoder===instance)fail(error);}
   });
   decoder=instance;decoder.configure(config);
  }
  async function submit(sample){
   if(closed)return;
   if(awaitingKey&&!sample.key){count.droppedEncodedFrames++;return;}
   const instance=decoder;await capacity(instance);
   if(closed||decoder!==instance)return;
   decoder.decode(new global.EncodedVideoChunk({type:sample.key?'key':'delta',timestamp:sample.timestamp,duration:sample.duration,data:sample.data}));
   awaitingKey=false;count.submittedFrames++;
  }
  async function accept(sample,data){
   need(data.length===sample.size,'Video sample size does not match MP4');
   need(isIdr(data)===sample.key,'AVC keyframe flags do not match sample');count.receivedFrames++;
   sampleBytes=data.length;
   try{await submit({...sample,data});}finally{sampleBytes=0;}
  }
  async function configure(description){
   config={codec,codedWidth:width,codedHeight:height,description,hardwareAcceleration:'prefer-hardware',optimizeForLatency:true};
   const result=await waitFor(Promise.resolve().then(()=>global.VideoDecoder.isConfigSupported(config)),'Native decoder configuration timed out; switching renderer.');
   if(closed)return;
   need(result?.supported,'Native AVC configuration is not supported by this browser');newDecoder();awaitingKey=true;
  }
  async function consume(type,data,size){
   if(type==='ftyp'){need(!seenFtyp&&!seenMoov&&!pendingSample&&data.length>=8,'Unexpected MP4 file header');seenFtyp=true;return;}
   if(type==='moov'){need(seenFtyp&&!seenMoov&&!pendingSample,'Unexpected video initialization');const description=initDescription(data,codec,width,height);seenMoov=true;await configure(description);return;}
   need(seenMoov,'Video fragment arrived before initialization');
   if(type==='moof'){need(!pendingSample,'Missing video sample data');pendingSample=fragmentDescription(data,size);return;}
   if(type==='mdat'){need(pendingSample,'Unexpected video sample data');const sample=pendingSample;pendingSample=null;await accept(sample,data);return;}
   throw new Error('Unsupported MP4 box: '+type);
  }
  function push(data){
   if(closed)return Promise.resolve();
   try{
    need(data instanceof Uint8Array,'Video input must be bytes');
    if(data.length===0)return Promise.resolve();
    need(queuedInputs<128,'Too many unawaited native video inputs');
    need(data.length<=MAX_BYTES&&buffer.length+data.length+queuedInputBytes+sampleBytes<=MAX_BYTES,'Video parser buffer exceeded 4 MiB');
    const input=data.slice();queuedInputBytes+=input.length;queuedInputs++;
    // Serialize callers as well as fragmented MP4 parsing. Awaiting push applies
    // backpressure all the way to the network reader without discarding the IDR
    // and its dependent frames when one read contains a coalesced burst.
    const operation=pushTail.then(async()=>{
     if(closed)return;
     queuedInputBytes-=input.length;queuedInputs--;
     const joined=new Uint8Array(buffer.length+input.length);joined.set(buffer);joined.set(input,buffer.length);buffer=joined;
     while(!closed&&buffer.length>=8){
      const size=u32(buffer,0);need(size>=8&&size<=MAX_BYTES,'Invalid MP4 box size');
      if(buffer.length<size)break;
      const current=buffer;buffer=current.subarray(size);await consume(kind(current,4),current.subarray(8,size),size);
     }
     if(!closed&&buffer.length)buffer=buffer.slice();
    }).catch(error=>{if(!closed)fail(error);});
    pushTail=operation;return operation;
   }catch(error){fail(error);return Promise.resolve();}
  }
  return {push,close,get stats(){return {...count,renderer:paint.name,width,height,configured:Boolean(decoder&&decoder.state==='configured'),closed,parserBytes:buffer.length,pendingFrames:queuedInputs+(sampleBytes?1:0),pendingBytes:queuedInputBytes+sampleBytes,decodeQueueSize:decoder?.decodeQueueSize||0,waitingForKeyframe:awaitingKey};}};
 }
 global.CarDashCanvas={available,create};
})(window);
