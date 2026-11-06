// SPDX-License-Identifier: GPL-3.0-only
import {randomUUID} from 'node:crypto';
const need=(x,m)=>{if(!x)throw new Error(m);};
export function selectGeometry(width,height){
  need(Number.isFinite(width)&&Number.isFinite(height)&&width>=100&&height>=100&&width<=8192&&height<=8192,'invalid viewport');
  const ratio=Math.max(4/3,width/height);need(ratio<=5,'unsupported aspect ratio');
  const w=Math.floor(Math.sqrt(614400*ratio)/2)*2,h=Math.floor(w/ratio/2)*2;return {width:w,height:h};
}
export class InputLease{
  constructor(send){this.send=send;this.generation=null;this.slots=new Map();this.sequence=0;this.isReady=false;}
  release(){if(this.slots.size){this.send(Buffer.from('000000000000010000000000','hex'));this.slots.clear();}}
  activate(geometry){need(Number.isInteger(geometry.width)&&Number.isInteger(geometry.height)&&geometry.width>=geometry.height&&geometry.height>0&&geometry.width<=4096,'invalid geometry');
    this.release();this.geometry={...geometry};this.generation=randomUUID();this.sequence=0;this.isReady=false;return this.generation;}
  ready(generation){need(generation===this.generation&&generation,'stale geometry');this.isReady=true;}
  accept({generation,sequence,contacts}){
    need(generation&&generation===this.generation&&this.isReady,'stale or unready display');
    need(Number.isSafeInteger(sequence)&&sequence>this.sequence,'stale input sequence');
    need(Array.isArray(contacts)&&contacts.length<=2,'too many contacts');const ids=new Set();
    for(const c of contacts){need(Number.isSafeInteger(c.id)&&c.id>=0&&!ids.has(c.id),'invalid pointer id');ids.add(c.id);
      need(typeof c.down==='boolean'&&[c.x,c.y].every(x=>Number.isFinite(x)&&x>=0&&x<=1),'invalid touch coordinates');}
    const next=new Map([...this.slots].filter(([id])=>contacts.some(c=>c.id===id&&c.down)));
    for(const c of contacts.filter(c=>c.down))if(!next.has(c.id))next.set(c.id,[0,1].find(slot=>![...next.values()].includes(slot)));
    const report=Buffer.from('000000000000010000000000','hex');
    for(const c of contacts.filter(c=>c.down)){const offset=next.get(c.id)*6;report[offset+1]=1;report.writeUInt16LE(Math.round(c.x*this.geometry.width),offset+2);report.writeUInt16LE(Math.round(c.y*this.geometry.height),offset+4);}
    this.send(report);this.slots=next;this.sequence=sequence;return {sequence,generation};
  }
  close(){this.release();this.generation=null;this.isReady=false;}
}
