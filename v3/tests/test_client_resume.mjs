// SPDX-License-Identifier: GPL-3.0-only
// Viewer 3: restart a session the phone ended on its own; never one the user stopped.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../web/client.js',import.meta.url),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture({failStart=''}={}){
 const elements=new Map(),requests=[];let now=1000;
 let service={active:true,identityReady:true,session:'first',sessionSeconds:1,error:'',codec:null,videoConnected:false,audioOutput:'phone',videoContinuousDecode:true};
 const element=()=>({style:{},textContent:'',title:'',disabled:false,value:'',setAttribute(k,v){this[k]=v;},focus(){}});
 const video={...element(),pause(){},load(){},removeAttribute(){},play(){return Promise.resolve();},getBoundingClientRect(){return {left:0,top:0,width:773,height:601};}};
 elements.set('video',video);for(const id of ['status','start','stop','sound','audioOutput','full','exitFull','fitViewport'])elements.set('#'+id,element());
 async function fetch(url,options={}){
  if(url==='/api/status')return {ok:true,json:async()=>({...service})};
  const value=options.body?JSON.parse(options.body):{};requests.push({url,value});
  if(url==='/api/start'){
   if(failStart)return {ok:false,status:400,json:async()=>({error:failStart})};
   service={...service,active:true,session:'restarted-'+requests.filter(r=>r.url==='/api/start').length,lastStop:service.lastStop,requestedViewport:value.viewport};
  }
  if(url==='/api/stop')service={...service,active:false,session:null,lastStop:{session:value.session,reason:'user_stop',secondsAgo:0}};
  return {ok:true,json:async()=>({...service})};
 }
 const globals={document:{hidden:false,querySelector:s=>elements.get(s),body:{classList:{add(){},remove(){}}},addEventListener(){}},
  fetch,AbortController,DOMException,URL:{createObjectURL(){return 'blob:0';},revokeObjectURL(){}},performance:{now:()=>now},
  setTimeout:()=>0,clearTimeout(){},setInterval:()=>0,console,
  CarDashAudio:{stats:{enabled:false,muted:false,contextState:'suspended',connectionState:'idle',error:''},enable(){return Promise.resolve(false);},stop(){},connect(){return Promise.resolve(false);},muteToggle(){}}};
 globals.window=globals;globals.addEventListener=()=>{};
 const context=vm.createContext(globals);vm.runInContext(code,context);
 return {elements,requests,run:s=>vm.runInContext(s,context),advance(ms){now+=ms;},
  set service(v){service={...service,...v};},get service(){return service;},
  starts(){return requests.filter(r=>r.url==='/api/start');},status(){return elements.get('#status').textContent;},
  end(reason,session=service.session,secondsAgo=3){service={...service,active:false,session:null,lastStop:{session,reason,secondsAgo}};}};
}
async function shown(){const f=fixture(...arguments);await settle();await f.run('poll()');await settle();assert.equal(f.run('inputSession'),'first');return f;}

test('a session ended by lost contact restarts itself with the same layout',async()=>{
 const f=await shown();f.run('layoutViewport={width:773,height:601}');
 f.end('browser_timeout');await f.run('poll()');await settle();
 assert.equal(f.starts().length,1);assert.deepEqual(f.starts()[0].value.viewport,{width:773,height:601});
 await f.run('poll()');await settle();
 assert.equal(f.run('inputSession'),'restarted-1');assert.equal(f.run('nativeStats.autoResumes'),1);
 assert.equal(f.starts().length,1,'A resumed session must not be started twice');
});

test('native disconnects also resume; every other ending waits for the user',async()=>{
 for(const reason of ['native_control_disconnected','native_event_disconnected','native_video_disconnected','native_helper_ended','native_lease_failed','audio_lease_failed']){
  const f=await shown();f.end(reason);await f.run('poll()');await settle();assert.equal(f.starts().length,1,reason);
 }
 for(const reason of ['user_stop','viewport_changed','service_stop','native_start_failed','something_new']){
  const f=await shown();f.end(reason);await f.run('poll()');await settle();
  assert.equal(f.starts().length,0,reason);assert.match(f.status(),/Press Start/);
 }
});

test('pressing Stop is final even if the phone later reports that session',async()=>{
 const f=await shown();await f.elements.get('#stop').onclick();await settle();
 f.service={lastStop:{session:'first',reason:'browser_timeout',secondsAgo:1}};
 await f.run('poll()');await settle();assert.equal(f.starts().length,0);
});

test('another page\'s session, an old ending and older phones are left alone',async()=>{
 let f=await shown();f.end('browser_timeout','someone-else');await f.run('poll()');await settle();assert.equal(f.starts().length,0);
 f=await shown();f.end('browser_timeout','first',301);await f.run('poll()');await settle();assert.equal(f.starts().length,0);
 // Beta 5 and earlier report no lastStop at all.
 f=await shown();f.service={active:false,session:null};await f.run('poll()');await settle();assert.equal(f.starts().length,0);
 f=await shown();f.service={active:false,session:null,lastStop:'browser_timeout'};await f.run('poll()');await settle();assert.equal(f.starts().length,0);
});

test('a hidden page or an unprepared phone does not restart CarPlay',async()=>{
 let f=await shown();f.run('document.hidden=true');f.end('browser_timeout');await f.run('poll()');await settle();assert.equal(f.starts().length,0);
 // It resumes once the page is visible again.
 f.run('document.hidden=false');await f.run('poll()');await settle();assert.equal(f.starts().length,1);
 f=await shown();f.end('browser_timeout');f.service={identityReady:false};await f.run('poll()');await settle();assert.equal(f.starts().length,0);
});

test('automatic restarts are limited to two in five minutes',async()=>{
 const f=await shown();
 for(const expected of [1,2]){
  f.end('browser_timeout');await f.run('poll()');await settle();assert.equal(f.starts().length,expected);
  await f.run('poll()');await settle();f.advance(20000);
 }
 f.end('browser_timeout');await f.run('poll()');await settle();
 assert.equal(f.starts().length,2);assert.match(f.status(),/Press Start to reconnect/);
 // The explicit Start it asks for still works and the allowance returns later.
 await f.elements.get('#start').onclick();await settle();assert.equal(f.starts().length,3);
 f.advance(300001);await f.run('poll()');await settle();f.end('browser_timeout');await f.run('poll()');await settle();assert.equal(f.starts().length,4);
});

test('a failed automatic restart reports the phone\'s reason and is not repeated',async()=>{
 const f=await shown({failStart:'USB-free transport is unavailable: this iOS build is not supported yet'});
 f.end('browser_timeout');await f.run('poll()');await settle();
 assert.equal(f.starts().length,1);assert.match(f.status(),/not supported yet/);
 await f.run('poll()');await settle();assert.equal(f.starts().length,1);
});

test('an unsupported phone says so before Start is pressed',async()=>{
 const f=fixture();f.service={active:false,session:null,transport:{ready:false,error:'USB-free transport is unavailable: this iOS build (20H19) is not supported yet'}};
 await settle();await f.run('poll()');await settle();
 assert.match(f.status(),/20H19\) is not supported yet/);
 f.service={transport:{ready:true,error:''}};await f.run('poll()');await settle();assert.match(f.status(),/Ready\. Press Start/);
});
