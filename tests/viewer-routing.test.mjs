import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import vm from 'node:vm';

const option=new URL('../option1/',import.meta.url);
const manifest=JSON.parse(await readFile(new URL('viewer-version.json',option),'utf8'));
const previous=JSON.parse(await readFile(new URL('viewer4-version.json',option),'utf8'));
const loader=await readFile(new URL(manifest.loader,option),'utf8');
const html=await readFile(new URL('index.html',option),'utf8');
const digest=(data,encoding='hex')=>createHash('sha256').update(data).digest(encoding);
function load(query){
 const scripts=[],release={hidden:true},status={textContent:''};
 const document={querySelector:name=>name==='#releaseInfo'?release:name==='#status'?status:null,
                 createElement:name=>{assert.equal(name,'script');return {};},body:{appendChild:value=>scripts.push(value)}};
 vm.runInNewContext(loader,{window:{location:{href:'https://cfluid101.github.io/cardash-beta/option1/'+query}},document,URL});
 assert.equal(scripts.length,1);
 return {script:scripts[0],release,status};
}

test('only explicit ui=5 selects Viewer 5 and shows beta release links',()=>{
 const current=load('?v=https3&ui=5');
 assert.equal(current.script.src,'./'+manifest.routes['5'].client);
 assert.equal(current.script.async,false);
 assert.equal(current.release.hidden,false);
});

test('Viewer 4, default and previous query URLs retain the original client',()=>{
 for(const query of ['', '?v=https3', '?v=https3&ui=4', '?v=https3&ui=3', '?v=https3&ui=2', '?v=https2', '?ui=05', '?ui=999']){
  const prior=load(query);
  assert.equal(prior.script.src,'./assets/https3/client.8c4c1cd03b048e61.js',query);
  assert.equal(prior.release.hidden,true,query);
 }
});

test('loading failure leaves a visible recovery message',()=>{
 const current=load('?v=https3&ui=5');
 current.script.onerror();
 assert.equal(current.status.textContent,'Viewer files could not load. Refresh this page.');
});

test('all referenced and previous Viewer 4 scripts match their immutable digests',async()=>{
 for(const [path,expected] of Object.entries({...previous.script_sha256,...manifest.script_sha256})){
  const actual=digest(await readFile(new URL(path,option)));
  assert.equal(actual,expected,path);
  assert(path.includes('.'+actual.slice(0,16)+'.js'),path);
 }
 for(const [,src] of html.matchAll(/<script src="\.\/([^"]+)"/g)){
  assert(manifest.script_sha256[src],src);
 }
});

test('the style CSP permits exactly the unchanged layout plus release-link color',()=>{
 const style=html.match(/<style>([\s\S]*?)<\/style>/)[1];
 const actual=digest(style,'base64');
 assert.equal(actual,manifest.inline_style_sha256_base64);
 assert(html.includes("style-src 'sha256-"+actual+"'"));
 assert(!html.includes("'unsafe-inline'"));
});

test('Viewer 5 client changes only the displayed label',async()=>{
 const [current,prior]=await Promise.all([manifest.routes['5'].client,manifest.routes['4'].client].map(path=>readFile(new URL(path,option),'utf8')));
 assert.equal(current.replace('CarDash V3 · Viewer 5','CarDash V3 · Viewer 4'),prior);
 assert.notEqual(current,prior);
});

test('release note links are separate from the direct phone connection',()=>{
 const note=html.match(/<p id="releaseInfo" hidden>([\s\S]*?)<\/p>/)[1];
 assert(note.includes('https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.9'));
 assert(note.includes('com.cfluid.cardash.v3_3.0.0~beta.9_iphoneos-arm64.deb'));
 assert(note.includes('Existing Beta 7/8 packages'));
 assert(note.includes('export a diagnostic report'));
});
