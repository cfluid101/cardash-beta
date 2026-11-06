import test from 'node:test';import assert from 'node:assert/strict';
import {streamSalt} from '../lib/stream-key.mjs';
test('Apple signed plist representation becomes unsigned decimal stream key salt',()=>{assert.equal(streamSalt(-1n),'DataStream-Salt18446744073709551615');assert.equal(streamSalt(123),'DataStream-Salt123');assert.throws(()=>streamSalt(2**60));assert.throws(()=>streamSalt(1n<<65n));});
