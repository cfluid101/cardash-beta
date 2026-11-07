# SPDX-License-Identifier: GPL-3.0-only
"""Phone-resident native receiver. Loopback protocol + local-hotspot viewer."""
import argparse
import asyncio
import ctypes
import hashlib
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import plistlib
import signal
import stat
import socket
import struct
import sys
import time
import uuid
import crypto
from protocol import Pairing,ControlCipher,RtspParser,ScreenReceiver,mfi_sap,need
from media import Muxer,keyframe
from provision import CERT_SHA256

ROOT=Path(__file__).resolve().parent
VERSION='3.0.0-beta.1'
DISPLAY='b7e6c5a0-1111-4000-8000-000000000001'

def plist(data):return plistlib.dumps(data,fmt=plistlib.FMT_BINARY,sort_keys=False)
def response(request,status=200,body=b'',kind='application/octet-stream'):
    seq=request['headers'].get('cseq','0');need(seq.isdigit() and len(seq)<13,'CSeq')
    phrase={200:'OK',400:'Bad Request',403:'Forbidden',501:'Not Implemented'}[status]
    return (f"{request['protocol']} {status} {phrase}\r\nCSeq: {seq}\r\nContent-Length: {len(body)}\r\nContent-Type: {kind}\r\nServer: AirTunes/509.0\r\n\r\n").encode()+body

class Receiver:
    def __init__(self,args):
        self.args=args;self.state=Path(args.state);self.state.mkdir(parents=True,exist_ok=True,mode=0o750)
        if os.getuid()==0:os.chown(self.state,0,501);os.chmod(self.state,0o750)
        self.identity_path=self.state/'identity.json'
        if self.identity_path.exists():self.identity=json.loads(self.identity_path.read_text())
        else:self.identity={'id':str(uuid.uuid4()),'seed':os.urandom(32).hex(),'peers':{}};self.save_identity()
        self.token=os.urandom(32).hex();self.lock=asyncio.Lock();self.command_lock=asyncio.Lock()
        self.helper=None;self.active=False;self.started=0;self.last_heartbeat=0;self.had_viewer=False
        self.error='';self.native={};self.frames=0;self.codec=None;self.muxer=None;self.pending=None
        self.control=None;self.event=None;self.video=None;self.pair=None;self.screen_key=None;self.ec=None
        self.viewers={};self.connections=set();self.sequence=0;self.native_watch=None;self.provisioning=False
        self.capture=None;self.capture_bytes=0;self.last_pointer=None
        self.provision_task=None;self.provision_child=None
        self.generation=None
        self.log('service_started',version=VERSION)
    def log(self,event,**values):
        path=self.state/'diagnostic.ndjson'
        if path.exists() and path.stat().st_size>2*1024*1024:path.replace(self.state/'diagnostic.previous.ndjson')
        with path.open('a') as f:f.write(json.dumps({'time':time.time(),'event':event,**values},separators=(',',':'))+'\n')
    def save_identity(self):
        tmp=self.identity_path.with_suffix('.tmp');fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump(self.identity,f)
        tmp.replace(self.identity_path)
    def ready(self):
        return all((self.state/'accessory'/x).is_file() for x in ['identity.pk8','certificate.p7b'])
    def status(self):
        return dict(version=VERSION,active=self.active,session=self.generation,identityReady=self.ready(),preparing=self.provisioning,
                    nativeFrames=self.frames,codec=self.codec,videoConnected=bool(self.video),eventConnected=bool(self.event),
                    native=self.native,error=self.error,secondsRemaining=max(0,300-int(time.monotonic()-self.started)) if self.active else 0,
                    audioSupported=False,sourceWidth=1280,sourceHeight=720)
    async def prepare(self):
        if self.ready():return
        need(not self.provisioning,'Identity preparation is already running')
        self.provisioning=True;self.error='';self.log('identity_preparation_started')
        self.provision_task=asyncio.create_task(self.prepare_worker())
    async def prepare_worker(self):
        download=self.state/'identity-download.apk'
        try:
            downloader=str(Path(self.args.helper).with_name('cardash-v3-download'))
            self.provision_child=await asyncio.create_subprocess_exec(downloader,str(download),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            try:output,_=await asyncio.wait_for(self.provision_child.communicate(),45)
            except asyncio.TimeoutError:
                self.provision_child.kill();await self.provision_child.wait()
                raise ValueError('Identity download timed out. Check the phone internet connection and try Prepare again.')
            need(self.provision_child.returncode==0,'Identity download failed. Check the phone internet connection and try Prepare again. '+output.decode(errors='replace')[-500:])
            self.provision_child=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'provision.py'),str(self.state),str(download),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            try:output,_=await asyncio.wait_for(self.provision_child.communicate(),10)
            except asyncio.TimeoutError:
                self.provision_child.kill();await self.provision_child.wait();raise ValueError('Identity verification timed out; no session started')
            need(self.provision_child.returncode==0,'Identity verification failed: '+output.decode(errors='replace')[-500:])
            self.log('identity_prepared',certificate_sha256=CERT_SHA256)
        except Exception as e:self.error=str(e);self.log('identity_preparation_failed',error=str(e))
        finally:
            self.provisioning=False;self.provision_child=None
            if download.exists():download.unlink()
    async def import_identity(self):
        need(not self.active and not self.provisioning,'Stop the active trial or wait for preparation to finish')
        source='/var/mobile/Library/Caches/com.cfluid.cardash.v3/identity-import.apk'
        fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
        self.provisioning=True
        try:
            details=os.fstat(fd);need(stat.S_ISREG(details.st_mode) and details.st_uid==501 and 0<details.st_size<=32*1024*1024,'Invalid APK import file')
            self.provision_child=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'provision.py'),str(self.state),'--fd',str(fd),pass_fds=(fd,),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            try:output,_=await asyncio.wait_for(self.provision_child.communicate(),10)
            except asyncio.TimeoutError:
                self.provision_child.kill();await self.provision_child.wait();raise ValueError('Identity verification timed out; no session started')
            need(self.provision_child.returncode==0,'Identity verification failed: '+output.decode(errors='replace')[-500:])
            self.error='';self.log('identity_imported',certificate_sha256=CERT_SHA256)
        except Exception as e:
            self.error=str(e);self.log('identity_import_failed',error=str(e));raise
        finally:
            os.close(fd);self.provisioning=False;self.provision_child=None
            if os.path.exists(source):os.unlink(source)
        return self.status()
    async def start(self):
        async with self.lock:
            if self.active:return self.status()
            need(not self.provisioning,'Wait for identity preparation to finish')
            need(self.ready(),'Open CarDash V3 on the phone and tap Prepare Native Preview first')
            self.der=(self.state/'accessory/identity.pk8').read_bytes();self.cert=(self.state/'accessory/certificate.p7b').read_bytes()
            need(hashlib.sha256(self.cert).hexdigest()==CERT_SHA256 and crypto.certificate_matches(self.der,self.cert),'Accessory identity invalid')
            self.frames=0;self.codec=None;self.muxer=None;self.pending=None;self.native={};self.error='';self.capture_bytes=0
            self.generation=os.urandom(16).hex()
            if self.args.capture:
                folder=Path(self.args.capture);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
                self.capture=(folder/'native.mp4').open('wb')
            public=crypto.public(bytes.fromhex(self.identity['seed'])).hex()
            self.helper=await asyncio.create_subprocess_exec(self.args.helper,'62000',public,'300',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
            self.active=True;self.started=time.monotonic();self.last_heartbeat=self.started;self.had_viewer=False
            self.native_watch=asyncio.create_task(self.watch_helper(self.helper,self.generation))
            self.log('native_start',pid=self.helper.pid);return self.status()
    async def watch_helper(self,child,generation):
        try:
            while True:
                line=await child.stdout.readline()
                if not line:break
                try:
                    value=json.loads(line)
                    if self.generation in (generation,None):
                        if value.get('event')=='session_observation':self.native={k:value[k] for k in ['present','authenticated','activated']}
                        elif value.get('event')=='cleanup' and value.get('session_present') is False:self.native={'present':False,'authenticated':False,'activated':False}
                    self.log('native_helper',detail=value)
                except (ValueError,KeyError):self.log('native_helper_output',text=line.decode(errors='replace')[:2000])
            code=await child.wait()
            if self.helper is child:
                if code:self.error=f'Native helper exited ({code}); export diagnostics'
                await self.stop('native_helper_ended')
        except asyncio.CancelledError:pass
    async def stop(self,reason='user_stop'):
        async with self.lock:
            child=self.helper;self.helper=None;self.active=False;self.generation=None
            if child and child.returncode is None:
                child.terminate()
                try:await asyncio.wait_for(child.wait(),4)
                except asyncio.TimeoutError:child.kill();await child.wait()
            for writer in [self.control,self.event,self.video]:
                if writer:writer.close()
            for queue in list(self.viewers):
                try:queue.put_nowait(None)
                except asyncio.QueueFull:pass
            self.control=self.event=self.video=None;self.pair=None;self.screen_key=None;self.ec=None;self.pending=None;self.last_pointer=None
            if self.capture:self.capture.close();self.capture=None
            self.log('native_stop',reason=reason,frames=self.frames)
    async def command(self,value,generation=None):
        expected=self.generation if generation is None else generation
        async with self.command_lock:
            need(self.active and expected==self.generation,'Stale native session')
            need(self.active and self.event and self.ec,'Native input is unavailable')
            body=plist(value);self.sequence+=1
            wire=(f'POST /command RTSP/1.0\r\nCSeq: {self.sequence}\r\nContent-Type: application/x-apple-binary-plist\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body
            self.event.write(self.ec.encode(wire));await asyncio.wait_for(self.event.drain(),2)
            if value['type']=='hidSendReport':self.log('native_touch',sequence=self.sequence)
            return self.sequence
    async def touch(self,value):
        need(self.active and value.get('session')==self.generation,'Stale native session')
        x,y,down=value.get('x'),value.get('y'),value.get('down')
        need(type(x) in (float,int) and type(y) in (float,int) and all(math.isfinite(v) and 0<=v<=1 for v in (x,y)) and type(down) is bool,'Touch coordinates invalid')
        need(self.frames>0,'Native video has not started')
        report=bytearray(12);report[6]=1;report[1]=int(down);struct.pack_into('<HH',report,2,round(x*1280),round(y*720))
        seq=await self.command({'type':'hidSendReport','uuid':'2a2a2a2a','hidReport':bytes(report)},value['session'])
        if value['session']==self.generation:self.last_pointer={'x':x,'y':y,'down':False,'session':value['session']} if down else None
        return {'sequence':seq}
    async def modes(self,generation):
        await asyncio.sleep(.5)
        if generation!=self.generation:return
        try:
            await self.command({'type':'changeModes','params':{'resources':[{'resourceID':1,'transferType':2}]}},generation)
            await self.command({'type':'showUI','params':{'url':'carplay:'}},generation)
        except Exception as e:self.log('show_ui_error',error=str(e))
    async def control_client(self,reader,writer):
        if not self.active or self.control:writer.close();return
        self.control=writer;pair=Pairing(self.identity,self.save_identity);parser=RtspParser();cipher=None;generation=self.generation
        try:
            while True:
                data=await asyncio.wait_for(reader.read(65536),30)
                if not data or generation!=self.generation:break
                for request in parser.push(cipher.decode(data) if cipher else data):
                    if generation!=self.generation:break
                    path=request['path'];method=request['method'];body=b'';kind='application/octet-stream';status=200
                    self.log('native_request',path=path,method=method,encrypted=bool(cipher))
                    if path in ('/pair-setup','/pair-verify'):
                        body=pair.setup(request['body']) if path=='/pair-setup' else pair.verify(request['body']);kind='application/pairing+tlv8'
                        if pair.error:self.log('pairing_error',error=pair.error)
                    elif not pair.verified:status=403
                    elif path=='/auth-setup':body=mfi_sap(request['body'],self.der,self.cert)
                    elif path=='/info':body=plistlib.loads((ROOT/'receiver-info.plist').read_bytes());body=plist(body);kind='application/x-apple-binary-plist'
                    elif method=='SETUP':
                        value=plistlib.loads(request['body']);reply={}
                        if 'streams' in value:
                            streams=[]
                            for s in value['streams']:
                                self.log('stream_offer',type=s.get('type'))
                                if s.get('type')==110:
                                    ident=int(s['streamConnectionID'])&0xffffffffffffffff
                                    self.screen_key=crypto.hkdf(pair.shared,'DataStream-Salt'+str(ident),'DataStream-Output-Encryption-Key')
                                    streams.append({'type':110,'dataPort':62002})
                            reply={'streams':streams}
                        else:
                            if value.get('timingPort'):
                                _,timing=await asyncio.open_connection('::1',62004);timing.write(struct.pack('>H',value['timingPort']));await timing.drain();timing.close()
                            reply={'timingPort':62003,'eventPort':62001,'enabledFeatures':['viewAreas']}
                        body=plist(reply);kind='application/x-apple-binary-plist'
                    elif method in ('RECORD','SET_PARAMETER','TEARDOWN','OPTIONS') or path in ('/feedback','/command'):
                        if method=='RECORD':asyncio.create_task(self.modes(generation))
                    else:status=501
                    wire=response(request,status,body,kind);writer.write(cipher.encode(wire) if cipher else wire);await writer.drain()
                    if not cipher and pair.verified and generation==self.generation:
                        cipher=ControlCipher(pair.read_key,pair.write_key);self.pair=pair;self.log('control_authenticated')
        except Exception as e:self.error=str(e);self.log('control_error',error=str(e))
        finally:
            writer.close()
            if self.control is writer:
                self.control=None
                if self.active:asyncio.create_task(self.stop('native_control_disconnected'))
    async def event_client(self,reader,writer):
        if not self.pair or not self.pair.verified or self.event:writer.close();return
        self.event=writer;shared=self.pair.shared;ec=ControlCipher(crypto.hkdf(shared,'Events-Salt','Events-Read-Encryption-Key'),crypto.hkdf(shared,'Events-Salt','Events-Write-Encryption-Key'));self.ec=ec;parser=RtspParser();generation=self.generation;self.log('event_connected')
        try:
            while True:
                data=await reader.read(65536)
                if not data or generation!=self.generation:break
                for request in parser.push(ec.decode(data)):
                    if request['method']!='RESPONSE':
                        async with self.command_lock:
                            if generation!=self.generation:break
                            writer.write(ec.encode(response(request)));await writer.drain()
        except Exception as e:self.log('event_error',error=str(e));self.error=str(e)
        finally:
            writer.close()
            if self.event is writer:self.event=None
            if self.active and generation==self.generation:asyncio.create_task(self.stop('native_event_disconnected'))
    def configure(self,config):
        if self.muxer and self.muxer.config==config:return
        self.muxer=Muxer(config,1280,720);self.codec=self.muxer.codec;self.initial=self.muxer.initialization();self.pending=None
        self.log('native_video_config',codec=self.codec)
        if self.capture:self.capture.write(self.initial)
        for q in list(self.viewers):
            try:q.put_nowait(None)
            except asyncio.QueueFull:pass
    def frame(self,data,timestamp):
        key=keyframe(data)
        if self.pending:
            old,ts,oldkey=self.pending;fragment=self.muxer.fragment(old,ts,timestamp)
            if fragment:
                if self.capture and self.capture_bytes+len(fragment)<=32*1024*1024:self.capture.write(fragment);self.capture_bytes+=len(fragment)
                for q,state in list(self.viewers.items()):
                    if state['closed']:continue
                    if not state['ready']:
                        if not oldkey:continue
                        fragment_out=self.initial+fragment;state['ready']=True
                    else:fragment_out=fragment
                    if state['bytes']+len(fragment_out)>2*1024*1024 or q.full():state['closed']=True;continue
                    state['bytes']+=len(fragment_out);q.put_nowait(fragment_out)
        self.pending=(data,timestamp,key);self.frames+=1
        if self.frames<4 or self.frames%300==0:self.log('native_frame',frames=self.frames)
    async def video_client(self,reader,writer):
        if not self.screen_key or self.video:writer.close();return
        self.video=writer;parser=ScreenReceiver(self.screen_key,self.configure,self.frame);generation=self.generation;self.log('video_connected')
        try:
            while True:
                data=await reader.read(65536)
                if not data or generation!=self.generation:break
                parser.push(data)
        except Exception as e:self.error=str(e);self.log('video_error',error=str(e))
        finally:
            writer.close()
            if self.video is writer:self.video=None
            self.log('video_closed',frames=self.frames)
            if self.active and generation==self.generation:asyncio.create_task(self.stop('native_video_disconnected'))
    async def ticker(self):
        while True:
            await asyncio.sleep(2)
            if not self.active:continue
            elapsed=time.monotonic()-self.last_heartbeat
            if elapsed>(12 if self.had_viewer else 45):await self.stop('browser_timeout');continue
            if self.viewers and self.event:
                try:await self.command({'type':'forceKeyFrame','params':{'uuid':DISPLAY}})
                except Exception as e:self.log('keyframe_error',error=str(e))
    async def action(self,value,local=False):
        action=value.get('action')
        if action=='status':return self.status()
        if action=='start':return await self.start()
        if action in ('stop','heartbeat') and not local:need(self.active and value.get('session')==self.generation,'Stale native session')
        if action=='stop':await self.stop();return self.status()
        if action=='heartbeat':self.last_heartbeat=time.monotonic();self.had_viewer=True;return self.status()
        if action=='touch':return await self.touch(value)
        if action=='prepare' and local:await self.prepare();return self.status()
        if action=='import' and local:return await self.import_identity()
        if action=='report' and local:
            text=''
            for name in ['installation.log','service-bootstrap.log','diagnostic.previous.ndjson','diagnostic.ndjson']:
                p=self.state/name
                if p.exists():
                    with p.open('rb') as f:
                        offset=max(0,p.stat().st_size-2*1024*1024);f.seek(offset);content=f.read(2*1024*1024).decode(errors='replace')
                    if offset and name.endswith('.ndjson'):content=content.partition('\n')[2]
                    text+=content if name.endswith('.ndjson') else json.dumps({'event':'supporting_log','file':name,'text':content})+'\n'
            if len(text)>4*1024*1024:text=text[-4*1024*1024:].partition('\n')[2]
            return {'report':text,'status':self.status()}
        raise ValueError('Unknown action')
    async def ipc(self,reader,writer):
        try:
            sock=writer.get_extra_info('socket');uid=ctypes.c_uint();gid=ctypes.c_uint();libc=ctypes.CDLL(None)
            need(libc.getpeereid(sock.fileno(),ctypes.byref(uid),ctypes.byref(gid))==0 and uid.value in (0,501),'Local peer denied')
            data=await asyncio.wait_for(reader.readline(),5);need(len(data)<=4096,'IPC size');value=json.loads(data)
            result=await self.action(value,local=True);writer.write(json.dumps({'ok':True,**result}).encode()+b'\n');await writer.drain()
        except Exception as e:
            self.log('local_request_rejected',error=str(e))
            writer.write(json.dumps({'ok':False,'error':str(e)}).encode()+b'\n')
            try:await writer.drain()
            except (OSError,ConnectionError):pass
        finally:writer.close()
    async def http(self,reader,writer):
        if len(self.connections)>=16:writer.close();return
        self.connections.add(writer)
        try:
            peer=writer.get_extra_info('peername');need(peer and ipaddress.ip_address(peer[0]).is_private,'Local network only')
            raw=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),5);need(len(raw)<=16384,'Header limit')
            lines=raw.decode('ascii').split('\r\n');method,path,_=lines.pop(0).split(' ');headers={}
            for line in lines:
                if not line:continue
                k,v=line.split(':',1);k=k.lower();need(k not in headers,'Duplicate header');headers[k]=v.strip()
            host=headers.get('host','');local_ip=writer.get_extra_info('sockname')[0]
            allowed={local_ip+':'+str(self.args.port)}
            if ipaddress.ip_address(peer[0]).is_loopback:allowed|={'localhost:'+str(self.args.port),'127.0.0.1:'+str(self.args.port)}
            need(host in allowed,'Host header rejected')
            need(headers.get('origin','http://'+host)=='http://'+host,'Cross-origin request rejected')
            need(headers.get('sec-fetch-site','same-origin') in ('same-origin','none'),'Cross-site request rejected')
            need('transfer-encoding' not in headers,'Transfer encoding rejected')
            length=int(headers.get('content-length','0'));need(0<=length<=4096,'Request limit')
            body=await asyncio.wait_for(reader.readexactly(length),5) if length else b''
            cookie=dict(v.strip().split('=',1) for v in headers.get('cookie','').split(';') if '=' in v)
            authenticated=hmac.compare_digest(cookie.get('cdv3',''),self.token)
            if method=='GET' and path in ('/','/client.js'):
                name='index.html' if path=='/' else 'client.js';data=(ROOT.parent/'web'/name).read_bytes()
                await self.reply(writer,200,data,'text/html' if path=='/' else 'text/javascript',{'Set-Cookie':f'cdv3={self.token}; HttpOnly; SameSite=Strict; Path=/'})
            elif not authenticated:await self.reply(writer,403,b'Open the CarDash page first','text/plain')
            elif method=='GET' and path=='/api/status':await self.reply(writer,200,json.dumps(self.status()).encode())
            elif method=='GET' and path=='/video':await self.viewer(writer)
            elif method=='POST' and path.startswith('/api/'):
                value=json.loads(body or b'{}');value['action']=path[5:];result=await self.action(value);await self.reply(writer,200,json.dumps(result).encode())
            else:await self.reply(writer,404,b'Not found','text/plain')
        except Exception as e:
            self.log('browser_request_rejected',error=str(e))
            try:await self.reply(writer,400,json.dumps({'error':str(e)}).encode())
            except (ConnectionError,OSError):pass
        finally:self.connections.discard(writer);writer.close()
    async def reply(self,writer,status,data,kind='application/json',extra=None):
        values={'Content-Type':kind,'Content-Length':str(len(data)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Connection':'close',**(extra or {})}
        header=f'HTTP/1.1 {status} '+('OK' if status==200 else 'Error')+'\r\n'+''.join(k+': '+v+'\r\n' for k,v in values.items())+'\r\n'
        writer.write(header.encode()+data);await asyncio.wait_for(writer.drain(),5)
    async def viewer(self,writer):
        need(self.active and self.video and self.muxer,'Native video is not ready');need(len(self.viewers)<2,'Two viewers are already connected')
        q=asyncio.Queue(maxsize=90);state={'ready':False,'bytes':0,'closed':False,'session':self.generation};self.viewers[q]=state;self.had_viewer=True;self.last_heartbeat=time.monotonic()
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n');await writer.drain()
        try:
            await self.command({'type':'forceKeyFrame','params':{'uuid':DISPLAY}})
            while self.active and not state['closed']:
                try:fragment=await asyncio.wait_for(q.get(),4)
                except asyncio.TimeoutError:
                    if writer.is_closing():break
                    continue
                if fragment is None:break
                state['bytes']-=len(fragment);writer.write(fragment);await asyncio.wait_for(writer.drain(),3)
        finally:
            self.viewers.pop(q,None)
            if self.last_pointer and state['session']==self.generation:
                try:await self.touch(self.last_pointer)
                except Exception:pass
    async def run(self):
        servers=[];ipcpath=self.state/'control.sock'
        # Process-wide lock in main makes an existing socket stale only for this service.
        if ipcpath.exists():ipcpath.unlink()
        try:
            for port,handler in [(62000,self.control_client),(62001,self.event_client),(62002,self.video_client)]:
                servers.append(await asyncio.start_server(handler,'::1',port,limit=65536))
            servers.append(await asyncio.start_server(self.http,'0.0.0.0',self.args.port,limit=16384))
            servers.append(await asyncio.start_unix_server(self.ipc,str(ipcpath),limit=8192));os.chmod(ipcpath,0o660)
            if os.getuid()==0:os.chown(ipcpath,0,501)
            self.log('listening',port=self.args.port)
            ticker=asyncio.create_task(self.ticker());stop=asyncio.Event();loop=asyncio.get_running_loop()
            for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
            await stop.wait();ticker.cancel()
        finally:
            if self.provision_child and self.provision_child.returncode is None:
                self.provision_child.kill();await self.provision_child.wait()
            await self.stop('service_stop')
            for server in servers:server.close();await server.wait_closed()
            for writer in self.connections:writer.close()
            if ipcpath.exists():ipcpath.unlink()

def main():
    import fcntl
    parser=argparse.ArgumentParser();parser.add_argument('--state',default='/var/jb/var/lib/cardash-v3');parser.add_argument('--helper',default='/var/jb/usr/libexec/cardash-v3-session');parser.add_argument('--port',type=int,default=8890);parser.add_argument('--capture');args=parser.parse_args()
    os.umask(0o077);Path(args.state).mkdir(parents=True,exist_ok=True,mode=0o750)
    with (Path(args.state)/'service.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from memory_budget import configure
        budget=configure()
        async def serve():
            receiver=Receiver(args);receiver.log('memory_budget',**budget)
            await receiver.run()
        asyncio.run(serve())
if __name__=='__main__':main()
