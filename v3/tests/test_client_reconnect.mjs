// SPDX-License-Identifier: GPL-3.0-only
// Viewer 4: a page the Tesla reloaded after shrinking the browser reconnects itself.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../web/client.js',import.meta.url),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture({stored,failConnect='',storage='normal',active=true}={}){
 const elements=new Map(),requests=[],connects=[];let disconnects=0,ready=false,now=1000;
 const saved=new Map();if(stored!==undefined)saved.set('cardash.option1.endpoint',stored);
 let service={active,identityReady:true,session:active?'running':null,sessionSeconds:400,error:'',codec:null,videoConnected:false,audioOutput:'phone',videoContinuousDecode:true};
 const element=()=>({style:{},textContent:'',title:'',disabled:false,value:'',hidden:true,setAttribute(k,v){this[k]=v;},focus(){}});
 const video={...element(),pause(){},load(){},removeAttribute(){},play(){return Promise.resolve();},getBoundingClientRect(){return {left:0,top:0,width:773,height:601};}};
 elements.set('video',video);for(const id of ['status','start','stop','sound','audioOutput','full','exitFull','fitViewport','connectionPanel','endpoint','connect','connectionStatus','buildLabel'])elements.set('#'+id,element());
 elements.set('#canvas',{hidden:true,cloneNode(){return this;},replaceWith(){},getContext(){return {};}});
 const transport={
  get diagnostics(){return {mode:'hosted',endpoint:connects.at(-1)||'http://100.99.10.2:8890/',ready,lastError:'',browserInstance:'0'.repeat(32)};},
  async connect(text){connects.push(text);if(failConnect)throw new Error(failConnect);ready=true;return true;},
  disconnect(){disconnects++;ready=false;},
  async fetch(url,options={}){
   if(url==='/api/status')return {ok:true,json:async()=>({...service})};
   const value=options.body?JSON.parse(options.body):{};requests.push({url,value});
   return {ok:true,json:async()=>({...service})};
  }};
 const localStorage=storage==='throws'?{getItem(){throw new Error('denied');},setItem(){throw new Error('denied');}}:{getItem:k=>saved.has(k)?saved.get(k):null,setItem(k,v){saved.set(k,String(v));}};
 const globals={document:{hidden:false,querySelector:s=>elements.get(s),body:{classList:{add(){},remove(){}}},addEventListener(){}},
  AbortController,DOMException,URL:{createObjectURL(){return 'blob:0';},revokeObjectURL(){}},performance:{now:()=>now},
  setTimeout:()=>0,clearTimeout(){},setInterval:()=>0,console,CarDashTransport:transport,
  CarDashCanvas:{available:()=>true,create(){return {push:async()=>{},close(){},stats:{}};}},
  CarDashAudio:{stats:{enabled:false,muted:false,contextState:'suspended',connectionState:'idle',error:''},enable(){return Promise.resolve(false);},stop(){},connect(){return Promise.resolve(false);},muteToggle(){}}};
 if(storage!=='missing')globals.localStorage=localStorage;
 globals.window=globals;globals.addEventListener=()=>{};
 const context=vm.createContext(globals);vm.runInContext(code,context);
 return {elements,requests,connects,saved,run:s=>vm.runInContext(s,context),get disconnects(){return disconnects;},
  status(){return elements.get('#status').textContent;},set service(v){service={...service,...v};}};
}

test('a reloaded page reconnects to the remembered phone and rejoins the running session without Start',async()=>{
 const f=fixture({stored:'http://100.99.10.2:8890/'});await settle();await settle();
 assert.deepEqual(f.connects,['http://100.99.10.2:8890/']);
 assert.equal(f.elements.get('#endpoint').value,'http://100.99.10.2:8890/');
 assert.equal(f.run('inputSession'),'running');assert.equal(f.run('carplayActive'),true);
 assert.equal(f.requests.filter(r=>r.url==='/api/start').length,0,'Rejoining must not start a second native session');
 assert.match(f.elements.get('#buildLabel').textContent,/Viewer 4/);
});

test('a browser that was never connected sends nothing until Connect, which is then remembered',async()=>{
 const f=fixture({});await settle();
 assert.deepEqual(f.connects,[]);assert.equal(f.elements.get('#endpoint').value,'http://100.99.10.2:8890/');
 f.elements.get('#endpoint').value='http://172.20.10.1:8890/';await f.elements.get('#connect').onclick();await settle();
 assert.deepEqual(f.connects,['http://172.20.10.1:8890/']);
 assert.equal(f.saved.get('cardash.option1.endpoint'),'http://172.20.10.1:8890/');
 assert.equal(f.run('inputSession'),'running');
});

test('a refused automatic reconnect is quiet and leaves Connect working',async()=>{
 const f=fixture({stored:'http://100.99.10.2:8890/',failConnect:'Cannot reach the iPhone.'});await settle();await settle();
 assert.equal(f.connects.length,1);assert.equal(f.disconnects,1);
 assert.match(f.status(),/Press Connect to reach your iPhone/);assert.doesNotMatch(f.status(),/Cannot reach/);
 assert.equal(f.elements.get('#connect').disabled,false);
 // The remembered address is kept for the next reload; a tap still reports the real error.
 assert.equal(f.saved.get('cardash.option1.endpoint'),'http://100.99.10.2:8890/');
 await f.elements.get('#connect').onclick();await settle();
 assert.equal(f.connects.length,2);assert.match(f.status(),/Cannot reach the iPhone/);
});

test('only a plain local address is ever reused',async()=>{
 for(const stored of ['https://example.com/','http://example.com/','http://100.99.10.2:8890/path','javascript:alert(1)','http://user:pw@10.0.0.1/','']){
  const f=fixture({stored});await settle();
  assert.deepEqual(f.connects,[],stored);assert.equal(f.elements.get('#endpoint').value,'http://100.99.10.2:8890/',stored);
 }
});

test('blocked or missing storage never breaks the page',async()=>{
 for(const storage of ['throws','missing']){
  const f=fixture({storage});await settle();
  assert.deepEqual(f.connects,[]);
  await f.elements.get('#connect').onclick();await settle();
  assert.equal(f.connects.length,1);assert.equal(f.run('inputSession'),'running',storage);
 }
});

test('reconnecting to a phone with no session waits at Ready instead of starting CarPlay',async()=>{
 const f=fixture({stored:'http://100.99.10.2:8890/',active:false});await settle();await settle();
 assert.equal(f.connects.length,1);assert.equal(f.requests.filter(r=>r.url==='/api/start').length,0);
 assert.match(f.status(),/Ready\. Press Start/);
});
