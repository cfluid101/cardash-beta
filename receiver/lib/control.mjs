// SPDX-License-Identifier: GPL-3.0-only
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import {randomBytes,timingSafeEqual} from 'node:crypto';
export function localControl(transport,dir,log){
 const token=randomBytes(32).toString('hex');fs.writeFileSync(path.join(dir,'control-token.txt'),token,{mode:0o600});
 const server=http.createServer((req,res)=>{
  if(req.method==='GET'&&['/','/client.js'].includes(req.url)){res.setHeader('Content-Type',req.url==='/'?'text/html':'text/javascript');res.end(fs.readFileSync(fileURLToPath(new URL(req.url==='/'?'../web/index.html':'../web/client.js',import.meta.url))));return;}
  const supplied=req.headers['x-cardash-research-token'];if(typeof supplied!=='string'||supplied.length!==token.length||!timingSafeEqual(Buffer.from(supplied),Buffer.from(token))){res.writeHead(403).end();return;}
  if(req.method==='GET'&&req.url==='/status'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({nativeFrames:transport.frames,videoConnected:!!transport.videoSocket,eventConnected:!!transport.eventSocket,bytes:transport.bytes,codec:transport.codec??null}));return;}
  if(req.method==='GET'&&req.url==='/video'){res.setHeader('Content-Type','video/mp4');res.setHeader('Cache-Control','no-store');try{transport.subscribe(res);}catch{res.writeHead(409).end();}return;}
  if(req.method!=='POST'||req.url!=='/touch'){res.writeHead(404).end();return;}
  let body='';req.on('data',b=>{body+=b;if(body.length>2048)req.destroy();});req.on('end',()=>{try{const {x,y,down}=JSON.parse(body);if(typeof down!=='boolean'||transport.frames<1)throw new Error('input unavailable');const sequence=transport.touch(x,y,down);res.end(JSON.stringify({sequence}));}catch(e){log('input_rejected',{error:e.message});res.writeHead(400).end(JSON.stringify({error:e.message}));}});
 });server.listen(46205,'127.0.0.1');return server;
}
