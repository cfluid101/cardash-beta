// SPDX-License-Identifier: GPL-3.0-only
export function streamSalt(value){
 if(typeof value!=='bigint'&&!(typeof value==='number'&&Number.isSafeInteger(value)))throw new Error('stream ID integer');
 const n=BigInt(value);if(n<-(1n<<63n)||n>=(1n<<64n))throw new Error('stream ID range');
 return 'DataStream-Salt'+BigInt.asUintN(64,n).toString();
}
