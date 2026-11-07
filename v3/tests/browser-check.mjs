// Owned, invisible browser. Tests actual native CarPlay frames over the SSH trial.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const WebSocket=createRequire(new URL('../../receiver/package.json',import.meta.url))('ws');
const trial=resolve(process.argv[2]);const trialStart=Date.now();const hold=process.env.CDV3_FULL_TRIAL==='1';
const dir=await mkdtemp(trial+'/chrome-profile-'),delay=ms=>new Promise(r=>setTimeout(r,ms));
const chrome=spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--headless=new','--disable-background-timer-throttling','--disable-renderer-backgrounding','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',`--user-data-dir=${dir}`,'--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--autoplay-policy=no-user-gesture-required','--mute-audio','about:blank'],{stdio:['ignore','ignore','pipe']});
let chromeLog='',ws,sequence=0;const pending=new Map(),errors=[],report={source:'native iPhone CarPlay, no generated video',passed:false};chrome.stderr.on('data',b=>chromeLog=(chromeLog+b.toString()).slice(-8000));
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timeout=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout '+method));},10000);pending.set(id,{resolve,reject,timeout});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression,timeout=15000){const start=Date.now();while(Date.now()-start<timeout){const result=await evaluate(expression);if(result)return result;await delay(100);}throw new Error('Browser timeout '+expression);}
async function screenshot(name){const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(trial+'/'+name,Buffer.from(r.data,'base64'));}
try{
 let port;for(let i=0;i<80;i++){try{port=Number((await readFile(dir+'/DevToolsActivePort','utf8')).split('\n')[0]);break;}catch{await delay(100);}}assert(port,'Chrome did not start');
 const target=await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent('http://127.0.0.1:8890/')}`,{method:'PUT'})).json();
 ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.once('open',r);ws.once('error',j);});
 ws.on('message',raw=>{const m=JSON.parse(raw);if(m.id){const p=pending.get(m.id);if(p){clearTimeout(p.timeout);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params);});
 await send('Runtime.enable');await send('Page.enable');await send('Page.bringToFront');await send('Emulation.setDeviceMetricsOverride',{width:1280,height:760,deviceScaleFactor:1,mobile:false});
 await until('document.querySelector("#start")');
 await evaluate('fetch("/api/start",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}).then(r=>r.json())');
 await until('window.nativeStats?.decodedFrames>0',25000);
 report.before=await evaluate('(()=>{const v=document.querySelector("video");return {...nativeStats,width:v.videoWidth,height:v.videoHeight,quality:v.getVideoPlaybackQuality().totalVideoFrames};})()');
 await screenshot('browser-before.png');
 const point=await evaluate('(()=>{const v=document.querySelector("video"),r=v.getBoundingClientRect(),s=Math.min(r.width/1280,r.height/720);return {x:r.left+(r.width-1280*s)/2+.052*1280*s,y:r.top+(r.height-720*s)/2+.92*720*s};})()');
 await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await delay(120);await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
 await until('nativeStats.inputSent>=2');await delay(2500);await screenshot('browser-after-touch.png');
 // Static CarPlay screens legitimately stop emitting video. Select Waze for the motion sample.
 const waze=await evaluate('(()=>{const r=document.querySelector("video").getBoundingClientRect(),s=Math.min(r.width/1280,r.height/720);return {x:r.left+(r.width-1280*s)/2+.052*1280*s,y:r.top+(r.height-720*s)/2+.347*720*s};})()');
 await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...waze});await delay(120);await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...waze});await until('nativeStats.inputSent>=4');
 await send('Emulation.setDeviceMetricsOverride',{width:1600,height:900,deviceScaleFactor:1,mobile:false});await delay(18000);
 report.after=await evaluate('(()=>{const v=document.querySelector("video"),q=v.getVideoPlaybackQuality();return {...nativeStats,width:v.videoWidth,height:v.videoHeight,total:q.totalVideoFrames,dropped:q.droppedVideoFrames,lag:v.buffered.length?v.buffered.end(v.buffered.length-1)-v.currentTime:null,status:document.querySelector("#status").textContent};})()');
 assert.deepEqual([report.after.width,report.after.height],[1280,720]);assert(report.after.decodedFrames>report.before.decodedFrames+50);assert(report.after.mediaTime>report.before.mediaTime+4);assert(report.after.inputSent>=2);assert.equal(errors.length,0);assert(Number.isFinite(report.after.lag)&&report.after.lag>=0&&report.after.lag<1.5);assert(report.after.trims>=1);
 await screenshot('browser-native-carplay.png');
 if(hold){for(;;){const state=await evaluate('fetch("/api/status").then(r=>r.json())');if(!state.active){report.fullTrialSeconds=(Date.now()-trialStart)/1000;report.finalState=state;assert(report.fullTrialSeconds>=285&&report.fullTrialSeconds<325);assert.equal(state.session,null);assert.equal(state.error,"");break;}assert(Date.now()-trialStart<325000);await delay(1000);}}
 report.passed=true;
}catch(e){report.error=e.stack;try{report.browser=await evaluate('(()=>{const v=document.querySelector("video");return {stats:window.nativeStats,status:document.querySelector("#status")?.textContent,error:v?.error?.message,currentTime:v.currentTime,paused:v.paused,ready:v.readyState,ranges:Array.from({length:v.buffered.length},(_,i)=>[v.buffered.start(i),v.buffered.end(i)]),queuedBytes:bytes,queued:queue.length,updating:buffer?.updating};})()');}catch{}process.exitCode=1;}
finally{
 await writeFile(trial+'/browser-check.json',JSON.stringify(report,null,2));await writeFile(trial+'/chrome-check.log',chromeLog);ws?.close();for(const p of pending.values())clearTimeout(p.timeout);chrome.kill('SIGTERM');await new Promise(r=>{if(chrome.exitCode!==null)r();else{chrome.once('exit',r);setTimeout(()=>{chrome.kill('SIGKILL');r();},5000).unref();}});await rm(dir,{recursive:true,force:true});console.log(JSON.stringify(report));
}
