// SPDX-License-Identifier: GPL-3.0-only
// Protocol port from DiPlay 615b32ce PairSetup/PairVerify/Srp6a. See NOTICE.md.
import * as c from 'node:crypto';
const need=(x,s)=>{if(!x)throw new Error(s);};
export const rawPublic=k=>k.export({format:'der',type:'spki'}).subarray(-32);
export function publicKey(b,type='ed25519'){need(b?.length===32,'public key length');return c.createPublicKey({key:Buffer.concat([Buffer.from(type==='x25519'?'302a300506032b656e032100':'302a300506032b6570032100','hex'),b]),format:'der',type:'spki'});}
export function generateIdentity(){return {...c.generateKeyPairSync('ed25519'),id:c.randomUUID()};}
export function tlv(items){return Buffer.concat(items.flatMap(([t,b])=>{need(Buffer.isBuffer(b)&&b.length<65536,'TLV value');const parts=[];for(let i=0;i<b.length||i===0;i+=255){const p=b.subarray(i,i+255);parts.push(Buffer.from([t,p.length]),p);}return parts;}));}
export function untlv(b){need(Buffer.isBuffer(b)&&b.length<=65536,'TLV size');const out=new Map();for(let i=0;i<b.length;){need(i+2<=b.length,'TLV header');const t=b[i++],n=b[i++];need(i+n<=b.length,'TLV truncated');out.set(t,Buffer.concat([out.get(t)??Buffer.alloc(0),b.subarray(i,i+n)]));i+=n;}return out;}
export const hkdf=(secret,salt,info)=>Buffer.from(c.hkdfSync('sha512',secret,Buffer.from(salt),Buffer.from(info),32));
function nonce(label){need(Buffer.byteLength(label)<=8,'nonce label');const n=Buffer.alloc(12);n.write(label,4);return n;}
export function box(key,label,data){const x=c.createCipheriv('chacha20-poly1305',key,nonce(label),{authTagLength:16});return Buffer.concat([x.update(data),x.final(),x.getAuthTag()]);}
export function unbox(key,label,data){need(data?.length>=16,'encrypted data');const x=c.createDecipheriv('chacha20-poly1305',key,nonce(label),{authTagLength:16});x.setAuthTag(data.subarray(-16));return Buffer.concat([x.update(data.subarray(0,-16)),x.final()]);}
const hash=(...b)=>c.createHash('sha512').update(Buffer.concat(b)).digest();
const integer=b=>BigInt('0x'+b.toString('hex'));
function bytes(n,pad=0){let h=n.toString(16);if(h.length%2)h='0'+h;return Buffer.from(h.padStart(pad*2,'0'),'hex');}
const N=integer(c.getDiffieHellman('modp15').getPrime()),G=5n;
function power(b,e){let r=1n;b%=N;while(e){if(e&1n)r=r*b%N;b=b*b%N;e>>=1n;}return r;}
const K=integer(hash(bytes(N),bytes(G,384)));
const equal=(a,b)=>a?.length===b?.length&&c.timingSafeEqual(a,b);
const state=n=>[6,Buffer.from([n])];
export class Pairing{
 constructor(identity,peers,save=()=>{}){this.identity=identity;this.peers=peers;this.save=save;this.verified=false;this.setupState=0;this.verifyState=0;}
 fail(s,e){this.lastError=e.message;return tlv([state(s),[7,Buffer.from([2])]]);}
 setup(body){let s=0;try{const t=untlv(body);s=t.get(6)?.[0]??0;
  if(s===1){need(!this.setupState,'setup already started');this.salt=c.randomBytes(16);const x=integer(hash(this.salt,hash(Buffer.from('Pair-Setup:3939'))));this.v=power(G,x);this.b=integer(c.randomBytes(32));this.B=(K*this.v+power(G,this.b))%N;this.setupState=2;return tlv([state(2),[3,bytes(this.B,384)],[2,this.salt]]);}
  if(s===3){need(this.setupState===2,'setup order');const ab=t.get(3),proof=t.get(4);need(ab?.length===384&&proof?.length===64,'SRP input');const A=integer(ab);need(A%N!==0n,'SRP zero');const u=integer(hash(ab,bytes(this.B,384)));need(u!==0n,'SRP u');const secret=power(A*power(this.v,u)%N,this.b);this.sessionKey=hash(bytes(secret));const hn=hash(bytes(N)),hg=hash(bytes(G));const xor=Buffer.from(hn.map((x,i)=>x^hg[i]));const expected=hash(xor,hash(Buffer.from('Pair-Setup')),this.salt,ab,bytes(this.B,384),this.sessionKey);need(equal(proof,expected),'SRP client proof rejected');this.setupState=4;return tlv([state(4),[4,hash(ab,proof,this.sessionKey)]]);}
  if(s===5){need(this.setupState===4,'setup order');const key=hkdf(this.sessionKey,'Pair-Setup-Encrypt-Salt','Pair-Setup-Encrypt-Info');const sub=untlv(unbox(key,'PS-Msg05',t.get(5)));const id=sub.get(1),pk=sub.get(3),signature=sub.get(10);need(id?.length>0&&id.length<=256&&signature?.length===64,'controller identity');const ck=hkdf(this.sessionKey,'Pair-Setup-Controller-Sign-Salt','Pair-Setup-Controller-Sign-Info');need(c.verify(null,Buffer.concat([ck,id,pk]),publicKey(pk),signature),'controller signature');const aid=Buffer.from(this.identity.id),apk=rawPublic(this.identity.publicKey),ak=hkdf(this.sessionKey,'Pair-Setup-Accessory-Sign-Salt','Pair-Setup-Accessory-Sign-Info');const sig=c.sign(null,Buffer.concat([ak,aid,apk]),this.identity.privateKey);this.peers.set(id.toString(),pk);this.save();this.setupState=6;return tlv([state(6),[5,box(key,'PS-Msg06',tlv([[1,aid],[3,apk],[10,sig]]))]]);}
  throw new Error('setup state');
 }catch(e){this.setupState=-1;return this.fail(s%2===1?s+1:s,e);}}
 verify(body){let s=0;try{const t=untlv(body);s=t.get(6)?.[0]??0;
  if(s===1){need(!this.verifyState,'verify already started');this.client=t.get(3);const peer=publicKey(this.client,'x25519'),ep=c.generateKeyPairSync('x25519');this.ep=rawPublic(ep.publicKey);this.shared=c.diffieHellman({privateKey:ep.privateKey,publicKey:peer});this.key=hkdf(this.shared,'Pair-Verify-Encrypt-Salt','Pair-Verify-Encrypt-Info');const id=Buffer.from(this.identity.id);const sig=c.sign(null,Buffer.concat([this.ep,id,this.client]),this.identity.privateKey);this.verifyState=2;return tlv([state(2),[3,this.ep],[5,box(this.key,'PV-Msg02',tlv([[1,id],[10,sig]]))]]);}
  if(s===3){need(this.verifyState===2,'verify order');const sub=untlv(unbox(this.key,'PV-Msg03',t.get(5))),id=sub.get(1),sig=sub.get(10);need(id?.length>0&&id.length<=256&&sig?.length===64,'verify identity');const pk=this.peers.get(id.toString());need(pk,'unknown controller');need(c.verify(null,Buffer.concat([this.client,id,this.ep]),publicKey(pk),sig),'verify signature');this.readKey=hkdf(this.shared,'Control-Salt','Control-Write-Encryption-Key');this.writeKey=hkdf(this.shared,'Control-Salt','Control-Read-Encryption-Key');this.verified=true;this.verifyState=4;return tlv([state(4)]);}
  throw new Error('verify state');
 }catch(e){this.verifyState=-1;return this.fail(s%2===1?s+1:s,e);}}
}
