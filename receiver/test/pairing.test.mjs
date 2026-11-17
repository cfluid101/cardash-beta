import test from 'node:test';
import assert from 'node:assert/strict';
import * as c from 'node:crypto';
import {Pairing,tlv,untlv,generateIdentity,hkdf,box,unbox,rawPublic,publicKey} from '../lib/pairing.mjs';
test('TLV reassembles long keys and rejects truncation',()=>{
 const value=c.randomBytes(384);assert.deepEqual(untlv(tlv([[3,value],[6,Buffer.from([2])]])).get(3),value);
 assert.throws(()=>untlv(Buffer.from([3,4,1])));
});
test('pair-verify authenticates the persisted controller and derives usable control keys',()=>{
 const identity=generateIdentity(),peer=c.generateKeyPairSync('ed25519'),eph=c.generateKeyPairSync('x25519'),id=Buffer.from('test-controller');
 const pairing=new Pairing(identity,new Map([[id.toString(),rawPublic(peer.publicKey)]]));
 const m2=untlv(pairing.verify(tlv([[6,Buffer.from([1])],[3,rawPublic(eph.publicKey)]])));
 assert.equal(m2.get(6)[0],2);
 const shared=c.diffieHellman({privateKey:eph.privateKey,publicKey:publicKey(m2.get(3),'x25519')});
 const key=hkdf(shared,'Pair-Verify-Encrypt-Salt','Pair-Verify-Encrypt-Info');
 const sub=untlv(unbox(key,'PV-Msg02',m2.get(5)));
 assert.equal(c.verify(null,Buffer.concat([m2.get(3),sub.get(1),rawPublic(eph.publicKey)]),identity.publicKey,sub.get(10)),true);
 const sig=c.sign(null,Buffer.concat([rawPublic(eph.publicKey),id,m2.get(3)]),peer.privateKey);
 const response=untlv(pairing.verify(tlv([[6,Buffer.from([3])],[5,box(key,'PV-Msg03',tlv([[1,id],[10,sig]]))]])));
 assert.equal(response.get(6)[0],4);assert.equal(response.has(7),false);assert.equal(pairing.verified,true);
 assert.deepEqual(pairing.readKey,hkdf(shared,'Control-Salt','Control-Write-Encryption-Key'));
});
test('unauthenticated verify and out-of-order setup fail closed',()=>{
 const pairing=new Pairing(generateIdentity(),new Map());
 assert.equal(untlv(pairing.verify(tlv([[6,Buffer.from([3])],[5,Buffer.alloc(30)]]))).get(7)[0],2);
 assert.equal(pairing.verified,false);
 assert.equal(untlv(pairing.setup(tlv([[6,Buffer.from([5])],[5,Buffer.alloc(30)]]))).get(7)[0],2);
});
