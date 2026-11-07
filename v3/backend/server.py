# SPDX-License-Identifier: GPL-3.0-only
"""Phone-resident native receiver. Loopback protocol + local-hotspot viewer."""
import sys

def startup_phase(phase):
    # Fixed phase names only: no verbose imports, paths, keys or session data.
    if __name__=='__main__':print('[CarDash V3 startup] '+phase,file=sys.stderr,flush=True)

startup_phase('python_entry')
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
import time
import uuid
import crypto
from protocol import Pairing,ControlCipher,RtspParser,ScreenReceiver,mfi_sap,need
from media import Muxer,keyframe
from provision import CERT_SHA256
from audio_transport import AudioChannel
from network import TeslaNetwork,allowed_peer
from transport import transport_status,startup_failure

startup_phase('imports_ready')

ROOT=Path(__file__).resolve().parent
VERSION='3.0.0-beta.3'
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
        self.error='';self.native_error='';self.native={};self.frames=0;self.codec=None;self.muxer=None;self.pending=None
        self.control=None;self.event=None;self.video=None;self.pair=None;self.screen_key=None;self.ec=None
        self.viewers={};self.connections=set();self.sequence=0;self.native_watch=None;self.provisioning=False
        self.capture=None;self.capture_bytes=0;self.last_pointer=None
        self.provision_task=None;self.provision_child=None
        self.generation=None
        self.audio_channels={};self.audio_history=[];self.audio_viewers={};self.audio_ducked=False;self.clock_offset=0
        self.pending_commands={}
        self.network=TeslaNetwork(args.port)
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
        return dict(version=VERSION,active=self.active,session=self.generation,identityReady=self.ready(),preparing=self.provisioning,network=self.network.status,transport=transport_status(self.state),
                    nativeFrames=self.frames,codec=self.codec,videoConnected=bool(self.video),eventConnected=bool(self.event),
                    native=self.native,error=self.error,sessionSeconds=int(time.monotonic()-self.started) if self.active else 0,sessionLimitSeconds=None,
                    audioSupported=True,microphoneSupported=False,audio=[c.status() for c in self.audio_channels.values()],audioHistory=self.audio_history[-16:],audioDucked=self.audio_ducked,sourceWidth=1280,sourceHeight=720)
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
            transport=transport_status(self.state);need(transport['ready'],transport.get('error','Transport unavailable'))
            self.der=(self.state/'accessory/identity.pk8').read_bytes();self.cert=(self.state/'accessory/certificate.p7b').read_bytes()
            need(hashlib.sha256(self.cert).hexdigest()==CERT_SHA256 and crypto.certificate_matches(self.der,self.cert),'Accessory identity invalid')
            self.frames=0;self.codec=None;self.muxer=None;self.pending=None;self.native={};self.error='';self.native_error='';self.capture_bytes=0
            self.audio_history=[];self.audio_ducked=False;self.clock_offset=0
            self.pending_commands.clear()
            self.generation=os.urandom(16).hex()
            if self.args.capture:
                folder=Path(self.args.capture);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
                self.capture=(folder/'native.mp4').open('wb')
            public=crypto.public(bytes.fromhex(self.identity['seed'])).hex()
            self.helper=await asyncio.create_subprocess_exec(self.args.helper,'62000',public,'0',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
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
                        elif value.get('event')=='timing_sync':self.clock_offset=float(value['offset_seconds'])
                    if self.generation==generation and value.get('event')=='native_completion' and value.get('success') is False:
                        self.native_error=value.get('error') or 'CarKit returned success=false without an error description'
                    self.log('native_helper',detail=value)
                except (ValueError,KeyError):self.log('native_helper_output',text=line.decode(errors='replace')[:2000])
            code=await child.wait()
            if self.helper is child:
                if code:self.error=f'Native helper exited ({code}); export diagnostics'
                await self.stop('native_helper_ended',generation=generation)
        except asyncio.CancelledError:pass
    async def stop(self,reason='user_stop',generation=None):
        async with self.lock:
            # Disconnect callbacks can wait behind another Stop/Start. Their
            # captured session must still own the receiver after that wait.
            if generation is not None and generation!=self.generation:return False
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
            for channel in self.audio_channels.values():
                self.audio_history.append(channel.status());channel.close()
            self.audio_channels.clear();self.audio_ducked=False
            for queue in list(self.audio_viewers):
                try:queue.put_nowait(None)
                except asyncio.QueueFull:pass
            self.control=self.event=self.video=None;self.pair=None;self.screen_key=None;self.ec=None;self.pending=None;self.last_pointer=None
            if self.capture:self.capture.close();self.capture=None
            self.log('native_stop',reason=reason,frames=self.frames)
            return True
    async def command(self,value,generation=None):
        expected=self.generation if generation is None else generation
        async with self.command_lock:
            need(self.active and expected==self.generation,'Stale native session')
            need(self.active and self.event and self.ec,'Native input is unavailable')
            body=plist(value);self.sequence+=1
            self.pending_commands[str(self.sequence)]=value['type']
            if len(self.pending_commands)>128:self.pending_commands.pop(next(iter(self.pending_commands)))
            wire=(f'POST /command RTSP/1.0\r\nCSeq: {self.sequence}\r\nContent-Type: application/x-apple-binary-plist\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body
            self.event.write(self.ec.encode(wire));await asyncio.wait_for(self.event.drain(),2)
            return self.sequence
    async def touch(self,value):
        need(self.active and value.get('session')==self.generation,'Stale native session')
        x,y,down=value.get('x'),value.get('y'),value.get('down')
        need(type(x) in (float,int) and type(y) in (float,int) and all(math.isfinite(v) and 0<=v<=1 for v in (x,y)) and type(down) is bool,'Touch coordinates invalid')
        need(self.frames>0,'Native video has not started')
        report=bytearray(12);report[6]=1;report[1]=int(down);struct.pack_into('<HH',report,2,round(x*1280),round(y*720))
        seq=await self.command({'type':'hidSendReport','uuid':'2a2a2a2a','hidReport':bytes(report)},value['session'])
        self.log('native_touch',sequence=seq,x=x,y=y,down=down)
        if value['session']==self.generation:self.last_pointer={'x':x,'y':y,'down':False,'session':value['session']} if down else None
        return {'sequence':seq}
    async def modes(self,generation):
        await asyncio.sleep(.5)
        if generation!=self.generation:return
        try:
            await self.command({'type':'changeModes','params':{'resources':[{'resourceID':1,'transferType':2},{'resourceID':2,'transferType':2}]}},generation)
            await self.command({'type':'showUI','params':{'url':'carplay:'}},generation)
        except Exception as e:self.log('show_ui_error',error=str(e))
    def native_command(self,body):
        if not body:return
        value=plistlib.loads(body);kind=value.get('type')
        if kind=='modesChanged':self.log('native_modes',params=value.get('params',{}))
        if kind in ('duckAudio','unduckAudio'):
            self.audio_ducked=kind=='duckAudio';self.log('audio_duck',active=self.audio_ducked)
    async def setup_audio(self,offer):
        key=(int(offer['type']),str(offer.get('audioType','default')).lower())
        need(len(key[1])<=64,'Audio type length')
        previous=self.audio_channels.get(key)
        used={c.lane for c in self.audio_channels.values()};lane=previous.lane if previous else next((i for i in range(8) if i not in used),None)
        need(lane is not None,'Audio stream limit')
        channel=AudioChannel(self,offer,lane);generation=self.generation
        result=await channel.listen()
        if not self.active or generation!=self.generation:channel.close();raise ValueError('Stale audio setup')
        if previous:self.audio_history.append(previous.status());previous.close()
        self.audio_history=self.audio_history[-16:];self.audio_channels[key]=channel
        self.log('audio_setup',**channel.status(),formatBits=offer.get('audioFormat'),latencyMs=offer.get('audioLatencyMs',150))
        return result
    def publish_audio(self,packet):
        for queue,state in self.audio_viewers.items():
            if state['closed']:continue
            if not 16<=len(packet)<=65552:
                state['closed']=True;self.log('audio_viewer_dropped',reason='packet_limit',packet_bytes=len(packet));continue
            previous=state['dropped_packets'];reason='queue_limit' if queue.full() else 'byte_limit'
            while state['bytes']+len(packet)>256*1024 or queue.full():
                dropped=queue.get_nowait()
                if dropped is None:
                    queue.put_nowait(None);state['closed']=True;break
                record,dropped=dropped
                state['bytes']-=len(dropped);state['dropped_packets']+=1;state['dropped_bytes']+=len(dropped)
                state['reset_lanes'][dropped[9]]=record
            if state['closed']:continue
            if state['dropped_packets']!=previous and (previous==0 or state['dropped_packets']//100>previous//100):
                self.log('audio_viewer_lag',reason=reason,dropped_packets=state['dropped_packets'],dropped_bytes=state['dropped_bytes'],queued_bytes=state['bytes'],queued_packets=queue.qsize())
            state['bytes']+=len(packet);state['next_record']+=1;queue.put_nowait((state['next_record'],packet))
    async def audio_viewer(self,writer,generation,reader=None):
        need(self.active and generation==self.generation,'Stale native session');need(len(self.audio_viewers)<2,'Two audio viewers are already connected')
        queue=asyncio.Queue(maxsize=64);state={'bytes':0,'closed':False,'reset_lanes':{},'next_record':0,'dropped_packets':0,'dropped_bytes':0};self.audio_viewers[queue]=state
        try:
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n');await asyncio.wait_for(writer.drain(),2)
            while self.active and generation==self.generation and not state['closed'] and not (reader and reader.at_eof()):
                try:packet=await asyncio.wait_for(queue.get(),2)
                except asyncio.TimeoutError:
                    if writer.is_closing() or (reader and reader.at_eof()):break
                    continue
                if packet is None or not self.active or generation!=self.generation or (reader and reader.at_eof()):break
                record,packet=packet;state['bytes']-=len(packet)
                # A discarded record may be the only reset for a replacement
                # channel whose serial restarted. An earlier in-flight record
                # must not consume the reset intended for newer queued data.
                lane=packet[9]
                if lane in state['reset_lanes'] and record>state['reset_lanes'][lane]:
                    packet=packet[:11]+bytes([packet[11]|1])+packet[12:];del state['reset_lanes'][lane]
                writer.write(packet);await asyncio.wait_for(writer.drain(),2)
        finally:self.audio_viewers.pop(queue,None)
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
                                elif s.get('type') in (100,101,102):
                                    streams.append(await self.setup_audio(s))
                                else:self.log('unsupported_stream',type=s.get('type'))
                            reply={'streams':streams}
                        else:
                            if value.get('timingPort'):
                                _,timing=await asyncio.open_connection('::1',62004);timing.write(struct.pack('>H',value['timingPort']));await timing.drain();timing.close()
                            reply={'timingPort':62003,'eventPort':62001,'enabledFeatures':['viewAreas']}
                        body=plist(reply);kind='application/x-apple-binary-plist'
                    elif path=='/feedback':
                        body=plist({'streams':[c.feedback(self.clock_offset) for c in self.audio_channels.values()]});kind='application/x-apple-binary-plist'
                    elif method=='TEARDOWN':
                        value=plistlib.loads(request['body']) if request['body'] else {}
                        types={s.get('type') for s in value.get('streams',[])} if value.get('streams') else None
                        for key,channel in list(self.audio_channels.items()):
                            if types is None or channel.type in types:self.audio_history.append(channel.status());channel.close();del self.audio_channels[key]
                        self.audio_history=self.audio_history[-16:]
                    elif path=='/command':self.native_command(request['body'])
                    elif method in ('RECORD','SET_PARAMETER','OPTIONS'):
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
                if self.active:asyncio.create_task(self.stop('native_control_disconnected',generation=generation))
    def event_response(self,request):
        sequence=request['headers'].get('cseq')
        kind=self.pending_commands.pop(sequence,None) if sequence is not None else None
        body=request['body'];issues=[];unparsed=False;visited=0
        # Do not serialize a raw reply: even a malformed/error response may
        # contain identity material. Only numeric protocol errors are retained.
        # Unknown property names and text/data values are always redacted.
        def inspect(value,path=(),depth=0,error_context=False):
            nonlocal visited
            if depth>5 or visited>=64 or len(issues)>=16:return
            visited+=1
            if isinstance(value,dict):
                for index,(key,child) in enumerate(value.items()):
                    if index>=16 or visited>=64 or len(issues)>=16:break
                    key=key.lower() if isinstance(key,str) else ''
                    known=key in ('error','errors','status','code','params','result','details')
                    child_path=path+(key if known else '*',)
                    flagged=key in ('error','status') or (error_context and key=='code')
                    if flagged and type(child) in (int,float,bool) and child and math.isfinite(child):
                        issues.append({'path':'.'.join(child_path),'code':child})
                    elif flagged and isinstance(child,str) and len(child)<=20 and child.isascii() and child.strip().lstrip('+-').isdigit():
                        code=int(child)
                        if code:issues.append({'path':'.'.join(child_path),'code':code})
                    elif flagged and isinstance(child,(str,bytes)) and child:
                        issues.append({'path':'.'.join(child_path),'valueType':type(child).__name__,'redacted':True})
                    if isinstance(child,(dict,list)):
                        inspect(child,child_path,depth+1,error_context or key in ('error','errors','status'))
            elif isinstance(value,list):
                for index,child in enumerate(value):
                    if index>=16 or visited>=64 or len(issues)>=16:break
                    inspect(child,path+('[]',),depth+1,error_context)
        if body:
            if len(body)>65536:unparsed=True
            else:
                try:inspect(plistlib.loads(body))
                except Exception:unparsed=True
        status=request['path']
        self.log('native_event_response',status=status,sequence=sequence[:64] if sequence is not None else None,
                 missingCSeq=sequence is None,sequenceTruncated=sequence is not None and len(sequence)>64,
                 command=kind,bodyBytes=len(body),bodyUnparsed=unparsed,bodyErrors=issues,
                 rejected=not status.startswith('2') or bool(issues))
    async def event_client(self,reader,writer):
        if not self.pair or not self.pair.verified or self.event:writer.close();return
        self.event=writer;shared=self.pair.shared;ec=ControlCipher(crypto.hkdf(shared,'Events-Salt','Events-Read-Encryption-Key'),crypto.hkdf(shared,'Events-Salt','Events-Write-Encryption-Key'));self.ec=ec;parser=RtspParser();generation=self.generation;self.log('event_connected')
        try:
            while True:
                data=await reader.read(65536)
                if not data or generation!=self.generation:break
                for request in parser.push(ec.decode(data)):
                    if generation!=self.generation:break
                    if request['method']=='RESPONSE':
                        self.event_response(request)
                    else:
                        if request['path']=='/command':self.native_command(request['body'])
                        async with self.command_lock:
                            if generation!=self.generation:break
                            writer.write(ec.encode(response(request)));await writer.drain()
        except Exception as e:self.log('event_error',error=str(e));self.error=str(e)
        finally:
            writer.close()
            if self.event is writer:self.event=None
            if self.active and generation==self.generation:asyncio.create_task(self.stop('native_event_disconnected',generation=generation))
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
                    if state['closed'] or state['session']!=self.generation:continue
                    if not state['ready']:
                        if not oldkey:continue
                        fragment_out=self.initial+fragment;state['ready']=True
                    else:fragment_out=fragment
                    if state['bytes']+len(fragment_out)>2*1024*1024 or q.full():
                        state['closed']=True;self.log('video_viewer_dropped',reason='queue_limit' if q.full() else 'byte_limit',queued_bytes=state['bytes'],queued_fragments=q.qsize());continue
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
                while True:
                    more=parser.push(data,max_packets=8);data=b''
                    # Buffered native reads can contain many small frames at once.
                    # Let HTTP writers drain instead of overflowing a healthy viewer.
                    await asyncio.sleep(0)
                    while generation==self.generation and any(not s['closed'] and q.qsize()>32 for q,s in self.viewers.items()):
                        await asyncio.sleep(.001)
                    if generation!=self.generation or not more:break
        except Exception as e:self.error=str(e);self.log('video_error',error=str(e))
        finally:
            writer.close()
            if self.video is writer:self.video=None
            self.log('video_closed',frames=self.frames)
            if self.active and generation==self.generation:asyncio.create_task(self.stop('native_video_disconnected',generation=generation))
    async def ticker(self):
        while True:
            await asyncio.sleep(2)
            if not self.active:continue
            generation=self.generation
            failure=startup_failure(self.active,self.frames,self.started,time.monotonic(),self.native_error)
            if failure:
                self.error=failure;self.log('native_start_failed',error=failure,native=self.native)
                await self.stop('native_start_failed',generation=generation);continue
            elapsed=time.monotonic()-self.last_heartbeat
            if elapsed>(12 if self.had_viewer else 45):await self.stop('browser_timeout',generation=generation);continue
            if self.helper and self.helper.stdin:
                try:self.helper.stdin.write(b'H');await asyncio.wait_for(self.helper.stdin.drain(),1)
                except (BrokenPipeError,ConnectionError,asyncio.TimeoutError):await self.stop('native_lease_failed',generation=generation);continue
            if self.viewers and self.event:
                try:await self.command({'type':'forceKeyFrame','params':{'uuid':DISPLAY}})
                except Exception as e:self.log('keyframe_error',error=str(e))
    async def action(self,value,local=False):
        action=value.get('action')
        if action=='status':return self.status()
        if action=='start':return await self.start()
        if action in ('stop','heartbeat') and not local:need(self.active and value.get('session')==self.generation,'Stale native session')
        if action=='stop':
            stopped=await self.stop(generation=None if local else value.get('session'))
            need(stopped,'Stale native session');return self.status()
        if action=='heartbeat':self.last_heartbeat=time.monotonic();self.had_viewer=True;return self.status()
        if action=='touch':return await self.touch(value)
        if action=='prepare' and local:await self.prepare();return self.status()
        if action=='import' and local:return await self.import_identity()
        if action=='release_audio' and local:
            await self.command({'type':'changeModes','params':{'resources':[{'resourceID':2,'transferType':2}]}});return self.status()
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
            peer=writer.get_extra_info('peername');need(peer and allowed_peer(peer[0],self.network),'Local network only')
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
            if method=='GET' and path in ('/','/client.js','/audio.js'):
                name='index.html' if path=='/' else path[1:];data=(ROOT.parent/'web'/name).read_bytes()
                await self.reply(writer,200,data,'text/html' if path=='/' else 'text/javascript',{'Set-Cookie':f'cdv3={self.token}; HttpOnly; SameSite=Strict; Path=/'})
            elif not authenticated:await self.reply(writer,403,b'Open the CarDash page first','text/plain')
            elif method=='GET' and path=='/api/status':await self.reply(writer,200,json.dumps(self.status()).encode())
            elif method=='GET' and path=='/video':
                need(self.active and headers.get('x-cardash-session')==self.generation,'Stale native session');await self.viewer(writer,reader)
            elif method=='GET' and path=='/audio':await self.audio_viewer(writer,headers.get('x-cardash-session'),reader)
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
    async def viewer(self,writer,reader=None):
        need(self.active and self.video and self.muxer,'Native video is not ready');need(len(self.viewers)<2,'Two viewers are already connected')
        q=asyncio.Queue(maxsize=90);state={'ready':False,'bytes':0,'closed':False,'session':self.generation};self.viewers[q]=state;self.had_viewer=True;self.last_heartbeat=time.monotonic()
        try:
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n');await asyncio.wait_for(writer.drain(),3)
            await self.command({'type':'forceKeyFrame','params':{'uuid':DISPLAY}},state['session'])
            while self.active and state['session']==self.generation and not state['closed'] and not (reader and reader.at_eof()):
                try:fragment=await asyncio.wait_for(q.get(),4)
                except asyncio.TimeoutError:
                    if writer.is_closing() or (reader and reader.at_eof()):break
                    continue
                if fragment is None or not self.active or state['session']!=self.generation or (reader and reader.at_eof()):break
                state['bytes']-=len(fragment);writer.write(fragment);await asyncio.wait_for(writer.drain(),3)
        finally:
            self.viewers.pop(q,None)
            if self.last_pointer and state['session']==self.generation:
                try:await self.touch(self.last_pointer)
                except Exception:pass
    async def network_monitor(self):
        previous=None
        while True:
            value=await asyncio.to_thread(self.network.refresh)
            state={k:v for k,v in value.items() if k!='added'}
            if state!=previous:
                self.log('tesla_network',**value);previous=state
            await asyncio.sleep(10)
    async def run(self):
        servers=[];ipcpath=self.state/'control.sock';network_task=None
        # Process-wide lock in main makes an existing socket stale only for this service.
        if ipcpath.exists():ipcpath.unlink()
        try:
            for port,handler in [(62000,self.control_client),(62001,self.event_client),(62002,self.video_client)]:
                servers.append(await asyncio.start_server(handler,'::1',port,limit=65536))
            servers.append(await asyncio.start_server(self.http,'0.0.0.0',self.args.port,limit=16384))
            servers.append(await asyncio.start_unix_server(self.ipc,str(ipcpath),limit=8192));os.chmod(ipcpath,0o660)
            if os.getuid()==0:os.chown(ipcpath,0,501)
            self.log('listening',port=self.args.port)
            startup_phase('ipc_listening')
            network_task=asyncio.create_task(self.network_monitor())
            ticker=asyncio.create_task(self.ticker());stop=asyncio.Event();loop=asyncio.get_running_loop()
            for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
            await stop.wait();ticker.cancel()
        finally:
            if network_task:
                network_task.cancel();await asyncio.gather(network_task,return_exceptions=True)
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
        startup_phase('configuring_memory_budget')
        from memory_budget import configure
        budget=configure()
        startup_phase('memory_budget_ready')
        async def serve():
            receiver=Receiver(args);receiver.log('memory_budget',**budget)
            await receiver.run()
        asyncio.run(serve())
if __name__=='__main__':main()
