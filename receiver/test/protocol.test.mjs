import test from 'node:test';
import assert from 'node:assert/strict';
import * as crypto from 'node:crypto';
const p = await import('../lib/protocol.mjs').catch(() => assert.fail('Receiver protocol implementation is missing'));
const {InputLease, selectGeometry} = await import('../lib/input.mjs');
const key = Buffer.alloc(32, 0x42);
function sealed(data, header, counter=0n) {
  const nonce = Buffer.alloc(12); nonce.writeBigUInt64LE(counter,4);
  const c = crypto.createCipheriv('chacha20-poly1305',key,nonce,{authTagLength:16});
  c.setAAD(header); return Buffer.concat([c.update(data),c.final(),c.getAuthTag()]);
}
test('RTSP retains fragmented bodies and separates pipelined requests', () => {
  const parser = new p.RtspParser();
  assert.deepEqual(parser.push(Buffer.from('POST /info RTSP/1.0\r\nCSeq: 7\r\nContent-Length: 3\r\n\r\na')),[]);
  const r=parser.push(Buffer.from('bcOPTIONS * RTSP/1.0\r\nCSeq: 8\r\n\r\n'));
  assert.equal(r.length,2); assert.equal(r[0].body.toString(),'abc');assert.equal(r[1].method,'OPTIONS');
  assert.match(p.rtspResponse(r[0],200,Buffer.from('ok')).toString(),/^RTSP\/1.0 200 OK\r\nCSeq: 7\r\nContent-Length: 2\r\n\r\nok$/);
  parser.end();
});
test('RTSP rejects ambiguous length, oversize headers/bodies, malformed lines and truncation',()=>{
  for(const wire of ['POST / RTSP/1.0\r\nContent-Length: -1\r\n\r\n','POST / RTSP/1.0\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n','POST / RTSP/1.0\r\nContent-Length: 1048577\r\n\r\n','POST / RTSP/1.0\r\nTransfer-Encoding: chunked\r\n\r\n','bad\r\n\r\n','a'.repeat(16385)]) assert.throws(()=>new p.RtspParser().push(Buffer.from(wire)));
  const a=new p.RtspParser();a.push(Buffer.from('GET'));assert.throws(()=>a.end(),/truncat/i);
});
test('control AEAD decrypts fragmented independent frames and rejects replay',()=>{
  const h=Buffer.from([3,0]), wire=Buffer.concat([h,sealed(Buffer.from('abc'),h)]);
  const c=new p.ControlCipher(key,Buffer.alloc(32,9));assert.equal(c.decode(wire.subarray(0,7)).length,0);
  assert.equal(c.decode(wire.subarray(7)).toString(),'abc');assert.throws(()=>c.decode(wire),/auth/i);
  assert.throws(()=>c.decode(Buffer.alloc(0)),/closed/i);
});
test('control encoding chunks without losing bytes and catches partial EOF',()=>{
  const a=new p.ControlCipher(Buffer.alloc(32,9),key),b=new p.ControlCipher(key,Buffer.alloc(32,9));
  const payload=Buffer.alloc(33000,0x73);assert.deepEqual(b.decode(a.encode(payload)),payload);
  const c=new p.ControlCipher(key,key);c.decode(Buffer.from([20,0]));assert.throws(()=>c.end(),/truncat/i);
});
test('screen parser authenticates the entire header before emitting a frame',()=>{
  const frames=[],configs=[],s=new p.ScreenReceiver(key,{onConfig:x=>configs.push(x),onFrame:x=>frames.push(x)});
  const config=Buffer.from('0142c01fffe100046742c01f01000268ce','hex');
  const ch=Buffer.alloc(128);ch.writeUInt32LE(config.length);ch[4]=1;
  s.push(Buffer.concat([ch,config]));assert.deepEqual(configs,[config]);
  const avcc=Buffer.from('000000026588','hex'),h=Buffer.alloc(128);h.writeUInt32LE(avcc.length+16);h.writeBigUInt64LE(2n<<32n,8);
  const wire=Buffer.concat([h,sealed(avcc,h)]);s.push(wire.subarray(0,130));assert.equal(frames.length,0);s.push(wire.subarray(130));
  assert.equal(frames.length,1);assert.equal(frames[0].timestampUs,2000000);assert.deepEqual(frames[0].data,avcc);
  const bad=Buffer.from(wire);bad[20]^=1;assert.throws(()=>s.push(bad));assert.equal(frames.length,1);
});
test('screen parser rejects oversize, unknown opcodes, frames before config and partial EOF',()=>{
  for(const mode of ['large','opcode','frame']){
    const h=Buffer.alloc(128);h.writeUInt32LE(mode==='large'?8388609:16);h[4]=mode==='opcode'?9:0;
    assert.throws(()=>new p.ScreenReceiver(key,{}).push(Buffer.concat([h,Buffer.alloc(16)])));
  }
  const s=new p.ScreenReceiver(key,{});s.push(Buffer.alloc(20));assert.throws(()=>s.end(),/truncat/i);
});
test('synthetic MFiSAP response verifies independently without an Apple identity',()=>{
  const controller=crypto.generateKeyPairSync('x25519'),signer=crypto.generateKeyPairSync('ec',{namedCurve:'prime256v1'});
  const cp=controller.publicKey.export({format:'der',type:'spki'}).subarray(-32);
  const cert=Buffer.from('SYNTHETIC-IDENTITY-NOT-APPLE');
  const response=p.mfiSap(Buffer.concat([Buffer.from([1]),cp]),{certificate:cert,signTranscript:data=>crypto.sign('sha256',data,{key:signer.privateKey,dsaEncoding:'ieee-p1363'})});
  const accessory=crypto.createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b656e032100','hex'),response.subarray(0,32)]),type:'spki',format:'der'});
  const shared=crypto.diffieHellman({privateKey:controller.privateKey,publicKey:accessory});
  const derive=tag=>crypto.createHash('sha1').update(tag).update(shared).digest().subarray(0,16);
  const n=response.readUInt32BE(32);assert.deepEqual(response.subarray(36,36+n),cert);assert.equal(response.readUInt32BE(36+n),64);
  const d=crypto.createDecipheriv('aes-128-ctr',derive('AES-KEY'),derive('AES-IV'));
  const sig=Buffer.concat([d.update(response.subarray(40+n)),d.final()]);
  assert(crypto.verify('sha256',Buffer.concat([response.subarray(0,32),cp]),{key:signer.publicKey,dsaEncoding:'ieee-p1363'},sig));
  assert.throws(()=>p.mfiSap(Buffer.alloc(33),{}));assert.throws(()=>p.mfiSap(Buffer.concat([Buffer.from([1]),Buffer.alloc(32)]),{}));
});
test('geometry fits landscape viewports and rejects degenerate input',()=>{
  for(const [w,h] of [[1280,600],[1600,900],[1206,652],[900,1000]]){
    const g=selectGeometry(w,h);assert(g.width>=g.height);assert.equal(g.width%2,0);assert.equal(g.height%2,0);assert(g.width*g.height<=614400);
    if(w>=h) assert(Math.abs(g.width/g.height-w/h)<.015);
  }
  for(const pair of [[0,600],[NaN,500],[Infinity,500],[1,50000]]) assert.throws(()=>selectGeometry(...pair));
});
test('portrait browser geometry still requests a landscape scene',()=>{
  const g=selectGeometry(900,1000);assert(g.width>g.height,'a square scene does not satisfy landscape-only');
});
test('input is released on replacement and stale/out-of-order input cannot reach the peer',()=>{
  const reports=[];const lease=new InputLease(x=>reports.push(x));const a=lease.activate({width:1000,height:500});lease.ready(a);
  lease.accept({generation:a,sequence:1,contacts:[{id:17,x:.25,y:.5,down:true}]});
  assert.equal(reports[0].toString('hex'),'0001fa00fa00010000000000');
  assert.throws(()=>lease.accept({generation:a,sequence:1,contacts:[]}));assert.equal(reports.length,1);
  const b=lease.activate({width:1200,height:600});assert.equal(reports[1].toString('hex'),'000000000000010000000000');
  assert.throws(()=>lease.accept({generation:a,sequence:2,contacts:[]}));assert.throws(()=>lease.accept({generation:b,sequence:1,contacts:[]}));
  lease.ready(b);assert.throws(()=>lease.accept({generation:b,sequence:1,contacts:[{id:1,x:2,y:0,down:true}]}));
  lease.accept({generation:b,sequence:1,contacts:[{id:1,x:1,y:1,down:true}]});assert.equal(reports.at(-1).readUInt16LE(2),1200);
  lease.close();assert.throws(()=>lease.accept({generation:b,sequence:2,contacts:[]}));
});
