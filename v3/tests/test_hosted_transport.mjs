import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../web/transport.js',import.meta.url),'utf8');
const token='a'.repeat(64);
function fixture({hosted=true,storedId=null}={}){
 const calls=[],stored=new Map(storedId?[['cardash.option1.clientId',storedId]]:[]),timers=new Map();let next=1;
 let responder=async(url)=>({ok:true,status:200,json:async()=>url.endsWith('/api/browser_session')?{version:1,token,expiresIn:1800}:{active:false}});
 const globals={URL,Headers,AbortController,DOMException,Uint8Array,crypto:{getRandomValues(a){a.fill(3);return a;}},
  location:hosted?{protocol:'https:',origin:'https://cfluid101.github.io',pathname:'/cardash-beta/option1/'}:{protocol:'http:',origin:'http://100.99.10.2:8890',pathname:'/'},
  sessionStorage:{getItem(k){return stored.get(k)||null;},setItem(k,v){stored.set(k,v);}},
  setTimeout(fn){const id=next++;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);},
  fetch(url,options){calls.push({url,options});return responder(url,options);}};
 globals.window=globals;vm.runInNewContext(code,globals);
 return {api:globals.CarDashTransport,calls,stored,timers,set responder(fn){responder=fn;}};
}
test('hosted mode waits for explicit connect; no token in diagnostics or storage',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);assert.equal(f.api.diagnostics.ready,false);
 await assert.rejects(()=>f.api.fetch('/api/status'),/Connect/);assert.equal(f.calls.length,0);
 await f.api.connect('http://100.99.10.2:8890');
 const first=f.calls[0];assert.equal(first.url,'http://100.99.10.2:8890/api/browser_session');
 assert.deepEqual(JSON.parse(first.options.body),{version:1,clientId:'03'.repeat(16)});
 assert.equal(first.options.credentials,'omit');assert.equal(first.options.targetAddressSpace,'local');
 assert.equal(first.options.headers.get('Authorization'),null);assert.equal(f.api.diagnostics.ready,true);
 assert(!JSON.stringify(f.api.diagnostics).includes(token));assert(!JSON.stringify([...f.stored]).includes(token));
 assert.equal(f.timers.size,0);
});
test('all remote request types attach bearer and retain session/abort/keepalive options',async()=>{
 const f=fixture({storedId:'b'.repeat(32)});await f.api.connect('http://192.168.1.50:8890/');
 const controller=new AbortController();
 for(const path of ['/api/status','/video','/audio','/image','/api/touch']){
  await f.api.fetch(path,{headers:{'X-CarDash-Session':'native-1'},signal:controller.signal,keepalive:true,credentials:'same-origin'});
  const {url,options}=f.calls.at(-1);assert.equal(url,'http://192.168.1.50:8890'+path);
  assert.equal(options.headers.get('Authorization'),'Bearer '+token);assert.equal(options.headers.get('X-CarDash-Session'),'native-1');
  assert.equal(options.credentials,'omit');assert.equal(options.signal,controller.signal);assert.equal(options.keepalive,true);assert.equal(options.redirect,'error');
 }
 assert.equal(JSON.parse(f.calls[0].options.body).clientId,'b'.repeat(32));
});
test('loopback uses its distinct permission space and local mode is unchanged',async()=>{
 const f=fixture();await f.api.connect('http://127.0.0.1:8890/');assert.equal(f.calls[0].options.targetAddressSpace,'loopback');
 const local=fixture({hosted:false}),options={method:'POST',body:'test'};await local.api.fetch('/api/status',options);
 assert.equal(local.calls[0].url,'/api/status');assert.equal(local.calls[0].options,options);assert.equal(local.api.diagnostics.mode,'local');assert(local.api.diagnostics.ready);
});
test('public endpoints, credentials, paths and redirects cannot receive a bearer',async()=>{
 const f=fixture();
 for(const url of ['https://example.com','http://example.com:8890','http://8.8.8.8:8890','http://user:pass@192.168.1.1:8890','http://192.168.1.1:8890/api','http://192.168.1.1:8890/?token=secret'])await assert.rejects(()=>f.api.connect(url),/local|address|endpoint/i);
 assert.equal(f.calls.length,0);
 await f.api.connect('http://10.1.2.3:8890/');
 for(const path of ['https://example.com/video','//example.com/video','/video?token=bad'])await assert.rejects(()=>f.api.fetch(path),/path/i);
 assert.equal(f.calls.length,1);
});
test('expired authorization clears the token and never replays a command',async()=>{
 const f=fixture();await f.api.connect('http://100.99.10.2:8890/');
 f.responder=async()=>({ok:false,status:401});
 await assert.rejects(()=>f.api.fetch('/api/start',{method:'POST'}),/expired|Connect/i);
 assert.equal(f.api.diagnostics.ready,false);assert.equal(f.calls.length,2);
 await assert.rejects(()=>f.api.fetch('/api/start',{method:'POST'}),/Connect/);assert.equal(f.calls.length,2);
});
test('bootstrap rejects invalid credentials and preserves actionable network errors',async()=>{
 const f=fixture();f.responder=async()=>({ok:true,status:200,json:async()=>({version:1,token:'bad',expiresIn:1800})});
 await assert.rejects(()=>f.api.connect('http://100.99.10.2:8890/'),/bootstrap|authorization/i);assert(!f.api.diagnostics.ready);
 f.responder=async()=>{throw new TypeError('Failed to fetch');};
 await assert.rejects(()=>f.api.connect('http://100.99.10.2:8890/'),/Local Network|local network/i);
 assert.match(f.api.diagnostics.lastError,/hotspot|address/i);assert.equal(f.timers.size,0);
});
test('stale bootstrap cannot replace a newer endpoint or credentials',async()=>{
 const f=fixture();let finish;
 f.responder=()=>new Promise(resolve=>{finish=resolve;});
 const old=f.api.connect('http://10.0.0.1:8890/');
 f.responder=async()=>({ok:true,status:200,json:async()=>({version:1,token,expiresIn:1800})});
 await f.api.connect('http://10.0.0.2:8890/');finish({ok:true,status:200,json:async()=>({version:1,token:'b'.repeat(64),expiresIn:1800})});
 await assert.rejects(()=>old,/cancel|ended|superseded/i);assert.equal(f.api.diagnostics.endpoint,'http://10.0.0.2:8890/');
 await f.api.fetch('/api/status');assert.equal(f.calls.at(-1).options.headers.get('Authorization'),'Bearer '+token);
});


test('bootstrap deadline includes a body that never finishes and remains retryable',async()=>{
 const f=fixture();f.responder=async()=>({ok:true,status:200,json:()=>new Promise(()=>{})});
 const pending=f.api.connect('http://100.99.10.2:8890/');await Promise.resolve();
 [...f.timers.values()][0]();await assert.rejects(()=>pending,/timed out/);assert.equal(f.api.diagnostics.ready,false);assert.equal(f.timers.size,0);
});
