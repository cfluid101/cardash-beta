// SPDX-License-Identifier: GPL-3.0-only
// Wire reference: DiPlay 615b32ce; see NOTICE.md. No accessory credentials included.
import * as crypto from 'node:crypto';
const HEADER_MAX=16384, BODY_MAX=1048576, SCREEN_MAX=8388608;
const need=(condition,message)=>{if(!condition)throw new Error(message);};
function nonce(counter){const n=Buffer.alloc(12);n.writeBigUInt64LE(counter,4);return n;}
export function seal(key,counter,data,aad){
  const c=crypto.createCipheriv('chacha20-poly1305',key,nonce(counter),{authTagLength:16});c.setAAD(aad);
  return Buffer.concat([c.update(data),c.final(),c.getAuthTag()]);
}
function open(key,counter,data,aad){
  need(data.length>=16,'authentication tag missing');
  try{const c=crypto.createDecipheriv('chacha20-poly1305',key,nonce(counter),{authTagLength:16});
    c.setAAD(aad);c.setAuthTag(data.subarray(-16));return Buffer.concat([c.update(data.subarray(0,-16)),c.final()]);
  }catch{throw new Error('authentication failed');}
}
class BoundedParser{
  constructor(limit){this.limit=limit;this.buffer=Buffer.alloc(0);this.closed=false;}
  feed(chunk,parse){
    need(!this.closed,'parser closed');
    try{need(Buffer.isBuffer(chunk)&&this.buffer.length+chunk.length<=this.limit,'receive buffer exceeded');
      this.buffer=Buffer.concat([this.buffer,chunk]);return parse();
    }catch(e){this.closed=true;this.buffer=Buffer.alloc(0);throw e;}
  }
  end(){need(!this.closed,'parser closed');this.closed=true;const remaining=this.buffer.length;this.buffer=Buffer.alloc(0);need(!remaining,'truncated message at EOF');}
}
export class RtspParser extends BoundedParser{
  constructor(){super(BODY_MAX+HEADER_MAX+4);}
  push(chunk){return this.feed(chunk,()=>{const messages=[];
    while(this.buffer.length){
      const end=this.buffer.indexOf('\r\n\r\n');
      if(end<0){need(this.buffer.length<=HEADER_MAX,'RTSP header exceeded');break;}
      need(end<=HEADER_MAX,'RTSP header exceeded');
      const raw=this.buffer.subarray(0,end);need([...raw].every(x=>x===9||x===10||x===13||(x>=32&&x<127)),'invalid header bytes');
      const lines=raw.toString('ascii').split('\r\n'),first=lines.shift(),response=/^(RTSP\/1\.0|HTTP\/1\.[01]) ([0-9]{3}) [ -~]*$/.exec(first);
      const match=response?[response[0],'RESPONSE',response[2],response[1]]:/^([A-Z_]+) (\S{1,2048}) (RTSP\/1\.0|HTTP\/1\.[01])$/.exec(first);
      need(match,'invalid request line');const headers=Object.create(null);
      for(const line of lines){const m=/^([A-Za-z0-9-]+):[ \t]*([^\r\n]*)$/.exec(line);need(m,'invalid header');
        const key=m[1].toLowerCase();need(!(key in headers),'duplicate header');headers[key]=m[2].trim();}
      need(!('transfer-encoding' in headers),'transfer encoding unsupported');
      const length=headers['content-length']??'0';need(/^(0|[1-9][0-9]*)$/.test(length),'invalid content length');
      const n=Number(length);need(Number.isSafeInteger(n)&&n<=BODY_MAX,'RTSP body exceeded');
      if(this.buffer.length<end+4+n)break;
      messages.push({method:match[1],path:match[2],protocol:match[3],headers,body:Buffer.from(this.buffer.subarray(end+4,end+4+n))});
      this.buffer=this.buffer.subarray(end+4+n);need(messages.length<=128,'too many pipelined requests');
    }return messages;
  });}
}
export function rtspResponse(request,status,body=Buffer.alloc(0)){
  need(Buffer.isBuffer(body)&&body.length<=BODY_MAX,'invalid response body');
  const protocol=request.protocol==='HTTP/1.1'?'HTTP/1.1':request.protocol==='HTTP/1.0'?'HTTP/1.0':'RTSP/1.0';
  const phrase={200:'OK',400:'Bad Request',404:'Not Found',501:'Not Implemented'}[status];need(phrase,'unsupported status');
  const seq=request.headers.cseq;need(seq===undefined||/^[0-9]{1,12}$/.test(seq),'invalid CSeq');
  return Buffer.concat([Buffer.from(`${protocol} ${status} ${phrase}\r\n${seq===undefined?'':`CSeq: ${seq}\r\n`}Content-Length: ${body.length}\r\n\r\n`),body]);
}
export class ControlCipher extends BoundedParser{
  constructor(readKey,writeKey){super(131072);need(readKey.length===32&&writeKey.length===32,'invalid control keys');this.readKey=Buffer.from(readKey);this.writeKey=Buffer.from(writeKey);this.readCounter=0n;this.writeCounter=0n;}
  encode(data){need(!this.closed,'cipher closed');need(Buffer.isBuffer(data)&&data.length<=BODY_MAX,'control payload exceeded');const out=[];
    for(let i=0;i<data.length||i===0;i+=16384){const part=data.subarray(i,i+16384),h=Buffer.alloc(2);h.writeUInt16LE(part.length);out.push(h,seal(this.writeKey,this.writeCounter++,part,h));}return Buffer.concat(out);
  }
  decode(chunk){return this.feed(chunk,()=>{const out=[];while(this.buffer.length>=2){const n=this.buffer.readUInt16LE();need(n<=16384,'control frame exceeded');if(this.buffer.length<2+n+16)break;
    out.push(open(this.readKey,this.readCounter,this.buffer.subarray(2,2+n+16),this.buffer.subarray(0,2)));this.readCounter++;this.buffer=this.buffer.subarray(2+n+16);
  }return Buffer.concat(out);});}
}
export class ScreenReceiver extends BoundedParser{
  constructor(key,callbacks){super(SCREEN_MAX+128);need(key.length===32,'invalid screen key');this.key=Buffer.from(key);this.callbacks=callbacks;this.counter=0n;this.configured=false;}
  push(chunk){return this.feed(chunk,()=>{while(this.buffer.length>=128){
    const h=this.buffer.subarray(0,128),n=h.readUInt32LE(),op=h[4];need(n<=SCREEN_MAX,'screen body exceeded');need(op===0||op===1||op===2,'unknown screen opcode '+op+' length '+n);
    if(this.buffer.length<128+n)break;const body=this.buffer.subarray(128,128+n);
    if(op===1){need(n<=65536,'codec config exceeded');let config=body;const avcc=body.indexOf('avcC');
      if(avcc>=4)config=body.subarray(avcc+4);need(config[0]===1&&config.length>=9,'unsupported codec configuration');
      this.callbacks.onConfig?.(Buffer.from(config));this.configured=true;
    }else if(op===0&&n>0){need(this.configured,'frame before codec configuration');const data=open(this.key,this.counter,body,h);this.counter++;
      const raw=h.readBigUInt64LE(8),us=Number((raw>>32n)*1000000n+((raw&0xffffffffn)*1000000n>>32n));
      this.callbacks.onFrame?.({data,timestampUs:us});
    }else{this.callbacks.onOther?.({opcode:op,bytes:n});}this.buffer=this.buffer.subarray(128+n);
  }});}
}
export function mfiSap(body,signer){
  need(Buffer.isBuffer(body)&&body.length===33&&body[0]===1,'invalid MFiSAP request');
  const peer=crypto.createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b656e032100','hex'),body.subarray(1)]),format:'der',type:'spki'});
  const pair=crypto.generateKeyPairSync('x25519'),pub=pair.publicKey.export({format:'der',type:'spki'}).subarray(-32);
  const shared=crypto.diffieHellman({privateKey:pair.privateKey,publicKey:peer});need(shared.some(x=>x!==0),'invalid shared key');
  const certificate=signer.certificate;need(Buffer.isBuffer(certificate)&&certificate.length>0&&certificate.length<=16384,'invalid accessory certificate');
  const signature=signer.signTranscript(Buffer.concat([pub,body.subarray(1)]));need(Buffer.isBuffer(signature)&&signature.length===64,'invalid P256 signature');
  const derive=tag=>crypto.createHash('sha1').update(tag).update(shared).digest().subarray(0,16);
  const c=crypto.createCipheriv('aes-128-ctr',derive('AES-KEY'),derive('AES-IV'));
  const encrypted=Buffer.concat([c.update(signature),c.final()]),n=Buffer.alloc(4),m=Buffer.alloc(4);n.writeUInt32BE(certificate.length);m.writeUInt32BE(encrypted.length);
  return Buffer.concat([pub,n,certificate,m,encrypted]);
}
