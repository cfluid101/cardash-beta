import test from 'node:test';import assert from 'node:assert/strict';import {RtspParser} from '../lib/protocol.mjs';
test('event channel accepts fragmented RTSP replies to input commands',()=>{const p=new RtspParser();assert.equal(p.push(Buffer.from('RTSP/1.0 200 OK\r\nCSeq: 3\r\nContent-Length: 0\r\n')).length,0);const [r]=p.push(Buffer.from('\r\n'));assert.equal(r.method,'RESPONSE');assert.equal(r.path,'200');});
import {ScreenReceiver} from '../lib/protocol.mjs';
test('zero-length screen keepalive preserves packet framing',()=>{const p=new ScreenReceiver(Buffer.alloc(32),{});const h=Buffer.alloc(128);h[4]=2;assert.doesNotThrow(()=>p.push(h));});
