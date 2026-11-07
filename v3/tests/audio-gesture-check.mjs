// Synthetic PCM/browser graph acceptance only. This does not use the phone,
// capture microphone audio, or establish that sound is audible in the Tesla.
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {readFile,mkdtemp,rm,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const WebSocket=createRequire(new URL('../../receiver/package.json',import.meta.url))('ws');
const source=await readFile(new URL('../web/audio.js',import.meta.url));
const out=process.argv[2]?resolve(process.argv[2]):null;
if(out)await mkdir(out,{recursive:true});
const delay=ms=>new Promise(r=>setTimeout(r,ms)),timers=new Set();
const server=createServer((req,res)=>{
 if(req.url==='/audio.js'){res.writeHead(200,{'Content-Type':'text/javascript'});res.end(source);return;}
 if(req.url==='/audio'){
  if(req.headers['x-cardash-session']!=='fixture-test'){res.writeHead(403);res.end();return;}
  res.writeHead(200,{'Content-Type':'application/octet-stream','Cache-Control':'no-store'});res.flushHeaders();
  let sequence=0;
  const timer=setInterval(()=>{
   const frames=960,packet=Buffer.alloc(4+12+frames*4);packet.writeUInt32BE(packet.length-4,0);packet.writeUInt32BE(48000,4);packet[8]=2;packet[9]=0;packet.writeUInt16BE(2,10);packet.writeUInt32BE(++sequence,12);
   for(let i=0;i<frames;i++){const value=Math.round(Math.sin((sequence*frames+i)*Math.PI*2*440/48000)*1024);packet.writeInt16LE(value,16+i*4);packet.writeInt16LE(value,18+i*4);}
   if(!res.write(packet)){res.end();clearInterval(timer);timers.delete(timer);}
  },20);timers.add(timer);res.on('close',()=>{clearInterval(timer);timers.delete(timer);});return;
 }
 res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><button id="sound" style="width:200px;height:80px">Enable synthetic audio</button><script src="/audio.js"></script><script>sound.onclick=async()=>{await CarDashAudio.enable();await CarDashAudio.connect("fixture-test")};</script>');
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;
const profile=await mkdtemp(join(tmpdir(),'cardash-audio-gesture-'));
// Enforce user activation rather than using the research viewer's bypass flag.
// Mute the OS output; analyserEnergy measures only the actual browser audio graph.
const chrome=spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--headless=new','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--autoplay-policy=document-user-activation-required','--mute-audio','about:blank'],{stdio:['ignore','ignore','pipe']});
let ws,sequence=0,logs='';const pending=new Map(),report={source:'synthetic PCM fixture; real Chrome Web Audio graph; OS output muted',passed:false};chrome.stderr.on('data',b=>logs=(logs+b).slice(-8000));
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout '+method));},10000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
try{
 let debugPort;for(let i=0;i<100;i++){try{debugPort=+(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await delay(100);}}assert(debugPort,'Chrome did not start');
 const page=await(await fetch(`http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent('http://127.0.0.1:'+port+'/')}`,{method:'PUT'})).json();ws=new WebSocket(page.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.once('open',r);ws.once('error',j);});
 ws.on('message',raw=>{const m=JSON.parse(raw),p=pending.get(m.id);if(!p)return;pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);});
 await send('Page.enable');await send('Runtime.enable');await send('Page.bringToFront');
 for(let i=0;i<100;i++){if(await evaluate('!!window.CarDashAudio'))break;await delay(50);}
 await evaluate('CarDashAudio.connect("fixture-test"); CarDashAudio.enable().catch(()=>{}); true');await delay(300);
 report.beforeGesture=await evaluate('CarDashAudio.stats');assert.equal(report.beforeGesture.contextState,'suspended');assert.equal(report.beforeGesture.connections,0);
 await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,x:80,y:40});await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:80,y:40});
 for(let i=0;i<60;i++){const value=await evaluate('CarDashAudio.stats');if(value.nonzeroSamples>40000&&value.analyserEnergy>.001){report.playing=value;break;}await delay(100);}
 assert(report.playing,'No rendered PCM after actual browser click');assert.equal(report.playing.contextState,'running');assert(report.playing.scheduledAhead<=.5);assert.equal(report.playing.error,'');
 await evaluate('CarDashAudio.stop()');await delay(100);report.stopped=await evaluate('CarDashAudio.stats');assert.equal(report.stopped.sources,0);assert.equal(report.stopped.lanes,0);assert.equal(report.stopped.connectionState,'idle');report.passed=true;
}catch(error){report.error=error.stack;process.exitCode=1;}
finally{
 ws?.close();for(const p of pending.values())clearTimeout(p.timer);chrome.kill('SIGTERM');await new Promise(r=>{if(chrome.exitCode!==null)r();else{chrome.once('exit',r);setTimeout(()=>{chrome.kill('SIGKILL');r();},5000).unref();}});
 for(const timer of timers)clearInterval(timer);server.closeAllConnections();await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true});
 if(out){await writeFile(join(out,'audio-gesture-check.json'),JSON.stringify(report,null,2)+'\n');await writeFile(join(out,'chrome.log'),logs);}
 console.log(JSON.stringify(report));
}
