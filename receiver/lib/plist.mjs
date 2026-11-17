// SPDX-License-Identifier: GPL-3.0-only
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const script=fileURLToPath(new URL('./plist.py',import.meta.url));
function run(mode,data){const r=spawnSync('python3',[script,mode],{input:data,maxBuffer:2*1024*1024,timeout:2000});if(r.status!==0)throw new Error('binary plist '+mode+' failed');return r.stdout;}
export const encodePlist=o=>run('encode',JSON.stringify(o,(_,v)=>typeof v==='bigint'?{$integer:v.toString()}:v));
export const decodePlist=b=>JSON.parse(run('decode',b),(_,v)=>v&&Object.keys(v).length===1&&v.$integer?BigInt(v.$integer):v);
export const plistBytes=b=>({$bytes:b.toString('base64')});
