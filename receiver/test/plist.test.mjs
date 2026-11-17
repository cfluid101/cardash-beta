import test from 'node:test';import assert from 'node:assert/strict';
import {encodePlist,decodePlist,plistBytes} from '../lib/plist.mjs';
import {receiverInfo} from '../lib/info.mjs';
test('binary plist preserves unsigned stream IDs and binary HID descriptors',()=>{const v={streamConnectionID:18446744073709551615n,data:plistBytes(Buffer.from([0,255]))};assert.deepEqual(decodePlist(encodePlist(v)),v);const i=receiverInfo();assert.deepEqual(decodePlist(encodePlist(i)),i);assert.equal(i.displays[0].widthPixels,1280);assert(i.features>2**32);});
