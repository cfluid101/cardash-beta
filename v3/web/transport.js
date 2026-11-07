// Direct browser-to-iPhone transport. Hosted assets never relay device traffic.
(function(global){
 'use strict';
 const location=global.location,hosted=location?.protocol==='https:'&&location.origin==='https://cfluid101.github.io'&&location.pathname.startsWith('/cardash-beta/option1/');
 const DEFAULT='http://100.99.10.2:8890/',NETWORK_ERROR='Cannot reach the iPhone. Check its hotspot and address, then allow Local Network Access for this site. This browser may not support HTTPS-to-local HTTP connections.';
 let endpoint=hosted?DEFAULT:location?.origin+'/',addressSpace='local',token='',ready=!hosted,lastError='',epoch=0,bootstrap=null,clientId=null;
 function localEndpoint(text){
  let url;try{url=new URL(text);}catch(_){throw new Error('Enter a local HTTP endpoint, for example '+DEFAULT);}
  if(url.protocol!=='http:'||url.username||url.password||url.pathname!=='/'||url.search||url.hash)throw new Error('Use a local HTTP address without credentials, path, query or fragment.');
  const host=url.hostname;
  if(host==='localhost'||host==='[::1]')return {url:url.origin+'/',space:'loopback'};
  if(!/^\d+\.\d+\.\d+\.\d+$/.test(host))throw new Error('The iPhone endpoint must use a local IPv4 address.');
  const p=host.split('.').map(Number);
  const loopback=p[0]===127,local=p[0]===10||(p[0]===172&&p[1]>=16&&p[1]<=31)||(p[0]===192&&p[1]===168)||(p[0]===169&&p[1]===254)||(p[0]===100&&p[1]>=64&&p[1]<=127);
  if(!loopback&&!local)throw new Error('The iPhone endpoint must be on the local network.');
  return {url:url.origin+'/',space:loopback?'loopback':'local'};
 }
 function identifier(){
  if(clientId)return clientId;
  try{const saved=global.sessionStorage?.getItem('cardash.option1.clientId');if(/^[0-9a-f]{32}$/.test(saved||''))clientId=saved;}catch(_){}
  if(!clientId){const bytes=new Uint8Array(16);global.crypto.getRandomValues(bytes);clientId=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');try{global.sessionStorage?.setItem('cardash.option1.clientId',clientId);}catch(_){}}
  return clientId;
 }
 function options(base,authorization){
  const headers=new Headers(base.headers||{});headers.delete('Authorization');if(authorization)headers.set('Authorization','Bearer '+authorization);
  return {...base,headers,mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',targetAddressSpace:addressSpace};
 }
 function disconnect(){epoch++;bootstrap?.abort();bootstrap=null;token='';ready=!hosted;lastError='';}
 async function connect(text=DEFAULT){
  if(!hosted)return true;
  disconnect();const generation=epoch;
  let controller,timer;
  try{
   const parsed=localEndpoint(text);endpoint=parsed.url;addressSpace=parsed.space;
   controller=new AbortController();bootstrap=controller;
   const timeout=new Promise((_,reject)=>{timer=global.setTimeout(()=>{controller.abort();reject(new Error('iPhone connection timed out. Check the hotspot/address and allow the Local Network Access prompt, then press Connect.'));},20000);});
   // The first request runs directly from the document's Connect click handler.
   const request=global.fetch(new URL('/api/browser_session',endpoint).href,options({method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({version:1,clientId:identifier()})},'')).then(async response=>({response,value:await response.json()}));
   const {response,value}=await Promise.race([request,timeout]);
   if(generation!==epoch||controller.signal.aborted)throw new Error('Connection attempt was superseded.');
   if(!response.ok)throw new Error(value.error||'iPhone authorization bootstrap failed ('+response.status+').');
   if(!value||typeof value!=='object'||value.version!==1||typeof value.token!=='string'||!/^([0-9a-f]{64})$/.test(value.token)||!Number.isInteger(value.expiresIn)||value.expiresIn<=0||value.expiresIn>86400)throw new Error('Invalid iPhone authorization bootstrap response.');
   token=value.token;ready=true;lastError='';return true;
  }catch(error){
   const message=error instanceof TypeError||error?.name==='TypeError'?NETWORK_ERROR:error.message||'iPhone connection failed.';
   if(generation===epoch){token='';ready=false;lastError=message;}
   throw new Error(message);
  }finally{if(timer!==undefined)global.clearTimeout(timer);if(bootstrap===controller)bootstrap=null;}
 }
 async function fetchDevice(path,base={}){
  if(!hosted)return global.fetch(path,base);
  if(!/^\/(?:api\/[a-z_]+|video|audio|image)$/.test(path))throw new Error('Invalid local request path.');
  if(!ready||!token)throw new Error('Press Connect to authorize this browser with the iPhone.');
  const generation=epoch;
  try{
   const response=await global.fetch(new URL(path,endpoint).href,options(base,token));
   if(response.status===401){
    if(generation===epoch){token='';ready=false;lastError='iPhone authorization expired. Press Connect to reconnect.';}
    throw new Error('iPhone authorization expired. Press Connect to reconnect.');
   }
   return response;
  }catch(error){
   if(error?.name==='AbortError')throw error;
   const message=error instanceof TypeError||error?.name==='TypeError'?NETWORK_ERROR:error.message||'Local request failed.';
   if(generation===epoch)lastError=message;throw new Error(message);
  }
 }
 global.CarDashTransport=Object.freeze({connect,disconnect,fetch:fetchDevice,get diagnostics(){return {mode:hosted?'hosted':'local',endpoint,ready,lastError};}});
})(window);
