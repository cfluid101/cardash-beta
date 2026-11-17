// SPDX-License-Identifier: GPL-3.0-only
import net from 'node:net';
import {localControl} from './lib/control.mjs';
import {Transport} from './lib/transport.mjs';
import {decodePlist,encodePlist} from './lib/plist.mjs';
import {receiverInfo} from './lib/info.mjs';
import fs from 'node:fs';
import path from 'node:path';
import * as crypto from 'node:crypto';
import {Pairing,generateIdentity,rawPublic,untlv} from './lib/pairing.mjs';
import {RtspParser,ControlCipher,mfiSap} from './lib/protocol.mjs';
const dir=path.resolve(process.argv[2]);fs.mkdirSync(dir,{recursive:true,mode:0o700});
const log=(event,detail={})=>process.stdout.write(JSON.stringify({time:new Date().toISOString(),event,...detail})+'\n');
const keyfile=path.join(dir,'identity.json');let identity,peers;
if(fs.existsSync(keyfile)){const saved=JSON.parse(fs.readFileSync(keyfile));const privateKey=crypto.createPrivateKey(saved.privateKey);identity={id:saved.id,privateKey,publicKey:crypto.createPublicKey(privateKey)};peers=new Map((saved.peers??[]).map(([id,key])=>[id,Buffer.from(key,'hex')]));}
else{identity=generateIdentity();peers=new Map();}
function save(){const tmp=keyfile+'.tmp';fs.writeFileSync(tmp,JSON.stringify({id:identity.id,privateKey:identity.privateKey.export({type:'pkcs8',format:'pem'}),peers:[...peers].map(([id,key])=>[id,key.toString('hex')])}),{mode:0o600});fs.renameSync(tmp,keyfile);}
save();fs.writeFileSync(path.join(dir,'public-key.txt'),rawPublic(identity.publicKey).toString('hex'));
const accessoryDir=path.resolve(dir,'../receiver-accessory-identity');
const accessoryKey=crypto.createPrivateKey({key:fs.readFileSync(path.join(accessoryDir,'identity.pk8')),format:'der',type:'pkcs8'});
const accessoryCert=fs.readFileSync(path.join(accessoryDir,'certificate.p7b'));
const certificateKey=new crypto.X509Certificate(fs.readFileSync(path.join(accessoryDir,'certificate.pem'))).publicKey;
const challenge=crypto.randomBytes(64),proof=crypto.sign('sha256',challenge,{key:accessoryKey,dsaEncoding:'ieee-p1363'});
if(!crypto.verify('sha256',challenge,{key:certificateKey,dsaEncoding:'ieee-p1363'},proof))throw new Error('accessory certificate mismatch');
log('accessory_identity_loaded',{source:'DiPlay-v0.2.22-public-experimental-APK',certificateSha256:crypto.createHash('sha256').update(accessoryCert).digest('hex')});
const signer={certificate:accessoryCert,signTranscript:data=>crypto.sign('sha256',data,{key:accessoryKey,dsaEncoding:'ieee-p1363'})};
const transport=new Transport(path.resolve(process.argv[3]),log);const control=localControl(transport,path.resolve(process.argv[3]),log);
const sockets=new Set();let next=0;
function respond(req,status,body=Buffer.alloc(0),type='application/octet-stream'){
 const phrase={200:'OK',400:'Bad Request',403:'Forbidden',501:'Not Implemented'}[status];const seq=req.headers.cseq??'0';if(!/^\d{1,12}$/.test(seq))throw new Error('CSeq');
 return Buffer.concat([Buffer.from(`${req.protocol} ${status} ${phrase}\r\nCSeq: ${seq}\r\nContent-Length: ${body.length}\r\nContent-Type: ${type}\r\nServer: AirTunes/509.0\r\n\r\n`),body]);
}
const server=net.createServer(socket=>{
 if(sockets.size>=1){socket.destroy();return;}sockets.add(socket);socket.setNoDelay(true);socket.setTimeout(30000);const id=++next,pair=new Pairing(identity,peers,save),parser=new RtspParser();let cipher;
 log('control_connected',{id});socket.on('timeout',()=>socket.destroy());socket.on('error',e=>log('socket_error',{id,error:e.message}));socket.on('close',()=>{sockets.delete(socket);transport.endSession();log('control_closed',{id});});
 socket.on('data',chunk=>{try{for(const req of parser.push(cipher?cipher.decode(chunk):chunk)){
  log('request',{id,method:req.method,path:req.path,bytes:req.body.length,encrypted:!!cipher});let status=200,body=Buffer.alloc(0),type='application/octet-stream';
  if(req.path==='/pair-setup'||req.path==='/pair-verify'){
   const t=untlv(req.body);log('pairing_request',{id,path:req.path,state:t.get(6)?.[0],method:t.get(0)?.[0],fields:[...t].map(([tag,value])=>[tag,value.length])});
   body=req.path==='/pair-setup'?pair.setup(req.body):pair.verify(req.body);type='application/pairing+tlv8';const out=untlv(body);log('pairing_response',{id,state:out.get(6)?.[0],error:out.get(7)?.[0],detail:pair.lastError??null,setupComplete:pair.setupState===6,verified:pair.verified});
  }else if(!pair.verified)status=403;
  else if(req.path==='/auth-setup'){body=mfiSap(req.body,signer);log('accessory_auth_response',{id,bytes:body.length});}
  else if(req.method==='SETUP'){const dict=decodePlist(req.body);log('setup',{id,keys:Object.keys(dict)});body=encodePlist(transport.setup(dict));type='application/x-apple-binary-plist';}
  else if(req.path==='/info'){body=encodePlist(receiverInfo());type='application/x-apple-binary-plist';}
  else if(['RECORD','SET_PARAMETER','TEARDOWN','OPTIONS'].includes(req.method)||req.path==='/feedback'||req.path==='/command'){if(req.path==='/command'&&req.body.length){const command=decodePlist(req.body);log('native_control_command',{type:command.type,params:command.type==='modesChanged'?command.params:undefined});}
 if(req.method==='RECORD'){log('native_record',{id});setTimeout(()=>{try{transport.command({type:'changeModes',params:{resources:[{resourceID:1,transferType:2}]}});transport.command({type:'showUI',params:{url:'carplay:'}});}catch(e){log('show_ui_error',{error:e.message});}},500);}}
  else status=501;
  const wire=respond(req,status,body,type);socket.write(cipher?cipher.encode(wire):wire);
  if(!cipher&&pair.verified){cipher=new ControlCipher(pair.readKey,pair.writeKey);transport.authenticate(pair);log('control_authenticated',{id});}
 }}catch(e){log('handler_error',{id,error:e.message});socket.destroy();}});
});
server.listen(46200,'127.0.0.1',()=>log('listening',{port:46200,identityPublic:rawPublic(identity.publicKey).toString('hex')}));
function close(){control.close();transport.close();for(const s of sockets)s.destroy();server.close(()=>process.exit(0));setTimeout(()=>process.exit(0),1000).unref();}
process.on('SIGTERM',close);process.on('SIGINT',close);setTimeout(close,300000).unref();
