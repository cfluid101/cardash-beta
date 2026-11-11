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
from display import geometry,apply_geometry,avc_dimensions
from provision import CERT_SHA256
from audio_transport import AudioChannel
from network import TeslaNetwork,allowed_peer
from transport import transport_status,startup_failure,AudioLease,audio_route_status
from video_budget import VideoBudget, VideoBudgetLease, budget_status
from browser_access import BrowserAccess,BrowserAccessError

startup_phase('imports_ready')

ROOT=Path(__file__).resolve().parent
VERSION='3.0.0-beta.5-https.3-open.1-diag.2'
DISPLAY='b7e6c5a0-1111-4000-8000-000000000001'
IMAGE_WAIT_SECONDS=4

class HTTPBusyError(ValueError):
    status=503

class HTTPResponseWriter:
    """Track one response boundary without changing the underlying transport."""
    def __init__(self,writer):
        self.writer=writer;self.started=False;self.phase='request_headers';self.bytes_written=0
    def __getattr__(self,name):return getattr(self.writer,name)
    def write(self,data):
        # Mark before write: a failed write may already have sent partial bytes.
        self.started=True;self.bytes_written=min(10**12,self.bytes_written+len(data))
        return self.writer.write(data)

def response_phase(writer,phase):
    if isinstance(writer,HTTPResponseWriter):writer.phase=phase

def create_image_decoder(config,width,height):
    from video_image import JPEGDecoder
    return JPEGDecoder(config,width,height,fps=10)


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
        self.token=os.urandom(32).hex();self.browser_access=BrowserAccess();self.lock=asyncio.Lock();self.command_lock=asyncio.Lock()
        self.images=None;self.image_lock=asyncio.Lock();self.image_waiters=0;self.image_epoch=0;self.image_close_tasks=set();self.image_error='';self.image_sequence=0
        self.helper=None;self.active=False;self.started=0;self.last_heartbeat=0;self.had_viewer=False
        self.error='';self.native_error='';self.native={};self.frames=0;self.codec=None;self.muxer=None;self.pending=None
        self.control=None;self.event=None;self.video=None;self.pair=None;self.screen_key=None;self.ec=None
        self.viewers={};self.connections=set();self.sequence=0;self.native_watch=None;self.provisioning=False
        self.capture=None;self.capture_bytes=0;self.last_pointer=None
        self.provision_task=None;self.provision_child=None
        self.generation=None
        self.reset_video_history();self.last_keyframe_request=-float('inf')
        self.audio_channels={};self.audio_history=[];self.audio_viewers={};self.audio_ducked=False;self.clock_offset=0
        self.pending_commands={}
        self.settings_path=self.state/'settings.json'
        try:
            settings=json.loads(self.settings_path.read_text()) if self.settings_path.exists() else {}
            self.settings=settings if isinstance(settings,dict) else {}
        except (OSError,ValueError):self.settings={}
        self.audio_output='browser' if self.settings.get('audioOutput')=='browser' else 'phone'
        self.audio_lease=AudioLease();self.video_budget=VideoBudget();self.video_lease=VideoBudgetLease()
        self.video_rate_at=time.monotonic();self.video_rate_bytes=0;self.video_bps=0
        self.last_browser_metrics=-float('inf');self.browser_metrics_clients={}
        self.display=geometry();self.actual_source=None;self.display_verified=False
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
                    nativeFrames=self.frames,codec=self.codec,videoContinuousDecode=True,videoBudget={**budget_status(),"targetBps":self.video_budget.bps,"measuredBps":self.video_bps},videoConnected=bool(self.video),eventConnected=bool(self.event),videoKeyframes=self.video_keyframes,videoTimelineTicks=self.video_ticks,
                    native=self.native,error=self.error,sessionSeconds=int(time.monotonic()-self.started) if self.active else 0,sessionLimitSeconds=None,
                    audioSupported=True,audioOutput=self.audio_output,audioRouting=audio_route_status(),microphoneSupported=False,audio=[c.status() for c in self.audio_channels.values()],audioHistory=self.audio_history[-16:],audioDucked=self.audio_ducked,sourceWidth=self.display.width,sourceHeight=self.display.height,requestedViewport=self.display.viewport,actualSource=self.actual_source,displayVerified=self.display_verified,imageStats=self.image_stats())
    def receiver_info(self):
        # iOS still requires complete CarPlay authentication/audio declarations.
        # The scoped native adapter preserves the phone route independently.
        return apply_geometry(plistlib.loads((ROOT/'receiver-info.plist').read_bytes()),self.display)
    async def set_audio_output(self,mode):
        need(mode in ('phone','browser'),'Invalid audio output')
        async with self.lock:
            need(not self.active and not self.provisioning,'Stop CarPlay before changing audio output')
            settings={**self.settings,'audioOutput':mode}
            tmp=self.settings_path.with_suffix('.tmp')
            fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as f:json.dump(settings,f)
            tmp.replace(self.settings_path)
            self.settings=settings;self.audio_output=mode
            self.log('audio_output_changed',mode=mode)
            return self.status()
    def browser_metrics(self,value):
        now=time.monotonic()
        if not isinstance(value,dict):return
        instance=value.get('browserInstance')
        if not isinstance(instance,str) or len(instance)!=32 or any(c not in '0123456789abcdef' for c in instance):instance=None
        if instance:
            for old,last in list(self.browser_metrics_clients.items()):
                if now-last>600:del self.browser_metrics_clients[old]
            if instance not in self.browser_metrics_clients and len(self.browser_metrics_clients)>=16:return
            if now-self.browser_metrics_clients.get(instance,-float('inf'))<12:return
        elif now-self.last_browser_metrics<12:return
        clean={}
        limits={'width':16384,'height':16384,'decodedFrames':10**10,'droppedFrames':10**10,'currentTime':10**8,'readyState':4,'mediaError':4,'videoErrors':10**8,'presentedFrames':10**10,'frameAgeMs':10**9,'decoderQueueSize':10000,'heartbeatRttMs':60000,'statusRttMs':60000,'inputRttMs':60000,'streamLagMs':10**9}
        for key,limit in limits.items():
            n=value.get(key)
            if type(n) in (int,float) and math.isfinite(n) and 0<=n<=limit:clean[key]=n
        for key in ('paused','hidden','secureContext','webCodecs','webGL','webGPU'):
            if type(value.get(key)) is bool:clean[key]=value[key]
        if type(value.get('canvasDrawCalls')) is int and 0<=value['canvasDrawCalls']<=10**10:clean['canvasDrawCalls']=value['canvasDrawCalls']
        for key,limit in {'inputQueued':5,'inputCoalesced':10**10,'inputErrors':10**10,'heartbeatErrors':10**10,'videoRetries':10**10,'streamRecoveries':10**10}.items():
            if type(value.get(key)) is int and 0<=value[key]<=limit:clean[key]=value[key]
        if value.get('renderer') in ('mse','webcodecs-webgl','webcodecs-2d','jpeg-canvas','unavailable'):clean['renderer']=value['renderer']
        if clean:
            if instance:clean['browserInstance']=instance;self.browser_metrics_clients[instance]=now
            else:self.last_browser_metrics=now
            self.log('browser_metrics',**clean)
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
    async def start(self,viewport=None):
        async with self.lock:return await self._start_locked(viewport)
    async def _start_locked(self,viewport=None):
        if self.active:return self.status()
        need(not self.provisioning,'Wait for identity preparation to finish')
        need(self.ready(),'Open CarDash V3 on the phone and tap Prepare Native Preview first')
        transport=transport_status(self.state);need(transport['ready'],transport.get('error','Transport unavailable'))
        if self.audio_output=='phone':
            routing=audio_route_status();need(routing['ready'],routing.get('error','Audio routing unavailable'))
        budget=budget_status();need(budget['ready'] and budget.get('pid')==transport.get('pid'),'Video bandwidth adapter unavailable; reinstall this beta to reload the media service')
        self.display=geometry(viewport);self.actual_source=None;self.display_verified=False;self.image_error='';self.image_sequence=0
        self.der=(self.state/'accessory/identity.pk8').read_bytes();self.cert=(self.state/'accessory/certificate.p7b').read_bytes()
        need(hashlib.sha256(self.cert).hexdigest()==CERT_SHA256 and crypto.certificate_matches(self.der,self.cert),'Accessory identity invalid')
        self.frames=0;self.codec=None;self.muxer=None;self.pending=None;self.native={};self.error='';self.native_error='';self.capture_bytes=0
        self.reset_video_history();self.last_keyframe_request=-float('inf')
        self.audio_history=[];self.audio_ducked=False;self.clock_offset=0
        self.pending_commands.clear()
        self.video_budget=VideoBudget()
        self.video_rate_at=time.monotonic();self.video_rate_bytes=0;self.video_bps=0
        self.generation=os.urandom(16).hex()
        if self.args.capture:
            folder=Path(self.args.capture);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            self.capture=(folder/'native.mp4').open('wb')
        public=crypto.public(bytes.fromhex(self.identity['seed'])).hex()
        try:
            self.audio_lease.refresh(self.audio_output=='phone')
            self.video_lease.refresh(self.video_budget.bps)
            self.helper=await asyncio.create_subprocess_exec(self.args.helper,'62000',public,'0',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        except BaseException:
            self.clear_leases()
            if self.capture:self.capture.close();self.capture=None
            self.generation=None
            raise
        self.active=True;self.started=time.monotonic();self.last_heartbeat=self.started;self.had_viewer=False
        self.native_watch=asyncio.create_task(self.watch_helper(self.helper,self.generation))
        self.log('native_start',pid=self.helper.pid,sessionTag=self.session_tag(),audioOutput=self.audio_output,requestedViewport=self.display.viewport,display={'width':self.display.width,'height':self.display.height,'widthPhysical':260,'heightPhysical':self.display.physical_height});return self.status()
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
        async with self.lock:return await self._stop_locked(reason,generation)
    def clear_leases(self):
        for name,lease in [('video',self.video_lease),('audio',self.audio_lease)]:
            try:lease.clear()
            except OSError as e:self.log(name+'_lease_clear_failed',error=str(e))
    def session_tag(self):
        return hashlib.sha256(self.generation.encode()).hexdigest()[:12] if self.generation else None
    async def _stop_locked(self,reason='user_stop',generation=None):
        # Disconnect callbacks can wait behind another Stop/Start. Their
        # captured session must still own the receiver after that wait.
        if generation is not None and generation!=self.generation:return False
        now=time.monotonic();tag=self.session_tag()
        lifetime=min(10**9,max(0,round((now-self.started)*1000))) if self.active else 0
        heartbeat_age=min(10**9,max(0,round((now-self.last_heartbeat)*1000))) if self.active else 0
        self.clear_leases()
        child=self.helper;self.helper=None;self.active=False;self.generation=None
        await self.close_images()
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
        self.log('native_stop',reason=reason,frames=self.frames,sessionTag=tag,lifetimeMs=lifetime,heartbeatAgeMs=heartbeat_age)
        return True
    async def resize(self,value):
        # Validate before ending anything, then re-check generation under the
        # same lock held through teardown and the replacement native request.
        need(value.get('viewport') is not None,'Viewport is required')
        target=geometry(value['viewport'])
        async with self.lock:
            need(self.active and value.get('session')==self.generation,'Stale native session')
            if (target.width,target.height)==(self.display.width,self.display.height):return self.status()
            await self._stop_locked('viewport_changed',value['session'])
            return await self._start_locked(target.viewport)
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
        report=bytearray(12);report[6]=1;report[1]=int(down);struct.pack_into('<HH',report,2,round(x*self.display.width),round(y*self.display.height))
        seq=await self.command({'type':'hidSendReport','uuid':'2a2a2a2a','hidReport':bytes(report)},value['session'])
        self.log('native_touch',sequence=seq,x=x,y=y,down=down)
        if value['session']==self.generation:self.last_pointer={'x':x,'y':y,'down':False,'session':value['session']} if down else None
        return {'sequence':seq}
    async def modes(self,generation):
        await asyncio.sleep(.5)
        if generation!=self.generation:return
        try:
            resources=[{'resourceID':1,'transferType':2},{'resourceID':2,'transferType':2}]
            await self.command({'type':'changeModes','params':{'resources':resources}},generation)
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
    async def audio_viewer(self,writer,generation,reader=None,response_headers=None):
        need(self.audio_output=='browser','Browser audio is disabled')
        need(self.active and generation==self.generation,'Stale native session');need(len(self.audio_viewers)<2,'Two audio viewers are already connected')
        queue=asyncio.Queue(maxsize=64);state={'bytes':0,'closed':False,'reset_lanes':{},'next_record':0,'dropped_packets':0,'dropped_bytes':0};self.audio_viewers[queue]=state
        try:
            response_phase(writer,'audio_headers')
            writer.write(self.stream_headers('application/octet-stream',response_headers));await asyncio.wait_for(writer.drain(),2)
            while self.active and generation==self.generation and not state['closed'] and not (reader and reader.at_eof()):
                response_phase(writer,'audio_wait')
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
                response_phase(writer,'audio_drain');writer.write(packet);await asyncio.wait_for(writer.drain(),2)
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
                    elif path=='/info':body=plist(self.receiver_info());kind='application/x-apple-binary-plist'
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
    def reset_video_history(self):
        self.video_keyframes=[];self.video_ticks=0;self.video_gop_bytes=0;self.video_last_idr_at=0
    async def request_keyframe(self,generation,reason):
        need(self.active and generation==self.generation,'Stale native session')
        now=time.monotonic()
        if reason!='viewer_join' and now-self.last_keyframe_request<30:return False
        # Set before the awaited command so concurrent demand cannot request a
        # burst of encoder restarts. A failed attempt also keeps this cooldown.
        self.last_keyframe_request=now
        await self.command({'type':'forceKeyFrame','params':{'uuid':DISPLAY}},generation)
        self.log('keyframe_requested',reason=reason,gopBytes=self.video_gop_bytes)
        return True
    def configure(self,config):
        if self.muxer and self.muxer.config==config:return
        self.invalidate_images('configuration_changed')
        self.display_verified=False
        width,height=avc_dimensions(config);self.actual_source={'width':width,'height':height}
        need((width,height)==(self.display.width,self.display.height),f'Native display returned {width}x{height}; requested {self.display.width}x{self.display.height}')
        self.display_verified=True
        self.muxer=Muxer(config,width,height);self.codec=self.muxer.codec;self.initial=self.muxer.initialization();self.pending=None
        self.reset_video_history()
        self.log('native_video_config',codec=self.codec,width=width,height=height)
        if self.capture:self.capture.write(self.initial)
        for q in list(self.viewers):
            try:q.put_nowait(None)
            except asyncio.QueueFull:pass
    def frame(self,data,timestamp):
        self.video_rate_bytes+=len(data);now=time.monotonic()
        if now-self.video_rate_at>=5:
            self.video_bps=round(self.video_rate_bytes*8/(now-self.video_rate_at))
            self.log('video_rate',bps=self.video_bps,budget=self.video_budget.bps,queue_bytes=max((s['bytes'] for s in self.viewers.values()),default=0),native_budget=budget_status(),audio_policy=audio_route_status())
            self.video_rate_bytes=0;self.video_rate_at=now
        key=keyframe(data)
        owner=self.images
        if owner and self.image_current(owner,self.generation):
            try:owner['decoder'].feed(data,timestamp)
            except Exception as e:
                self.image_error=str(e)[:256];self.log('image_feed_error',error=self.image_error);self.invalidate_images('feed_error')
        if self.pending:
            old,ts,oldkey=self.pending;fragment=self.muxer.fragment(old,ts,timestamp)
            if fragment:
                ticks=(ts-self.muxer.base)*90000//1000000
                self.video_ticks=(timestamp-self.muxer.base)*90000//1000000
                if oldkey:
                    self.video_keyframes.append(ticks);self.video_keyframes=self.video_keyframes[-32:]
                    self.video_gop_bytes=0;self.video_last_idr_at=time.monotonic()
                self.video_gop_bytes+=len(old)
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
                    # Yield briefly for a healthy burst, but never let one slow
                    # browser block the native timeline indefinitely. Its own
                    # bounded queue will close it while native ingress stays live.
                    until=time.monotonic()+.02
                    while generation==self.generation and time.monotonic()<until and any(not s['closed'] and q.qsize()>32 for q,s in self.viewers.items()):
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
            try:
                self.audio_lease.refresh(self.audio_output=='phone')
                self.video_lease.refresh(self.video_budget.bps)
            except OSError as e:
                self.error='Audio route lease failed: '+str(e);self.log('audio_lease_failed',error=self.error)
                await self.stop('audio_lease_failed',generation=generation);continue
            failure=startup_failure(self.active,self.frames,self.started,time.monotonic(),self.native_error)
            if failure:
                self.error=failure;self.log('native_start_failed',error=failure,native=self.native)
                await self.stop('native_start_failed',generation=generation);continue
            elapsed=time.monotonic()-self.last_heartbeat
            if elapsed>(12 if self.had_viewer else 45):await self.stop('browser_timeout',generation=generation);continue
            if self.helper and self.helper.stdin:
                try:self.helper.stdin.write(b'H');await asyncio.wait_for(self.helper.stdin.drain(),1)
                except (BrokenPipeError,ConnectionError,asyncio.TimeoutError):await self.stop('native_lease_failed',generation=generation);continue
            # This command restarts the hardware encoder on iOS 16.6. A long
            # GOP needs a bounded recovery point for safe browser eviction, but
            # healthy heartbeats must not repeatedly rebuild the encoder.
            now=time.monotonic()
            await self.expire_images(now)
            if (any(not state.get('continuous_decode',False) and not state.get('closed',False) for state in self.viewers.values()) or self.images) and self.event and self.video_last_idr_at and (self.video_gop_bytes>8*1024*1024 or now-self.video_last_idr_at>30):
                try:await self.request_keyframe(generation,'long_gop')
                except Exception as e:self.log('keyframe_error',error=str(e))
    async def action(self,value,local=False):
        action=value.get('action')
        if action=='status':return self.status()
        if action=='start':return await self.start(value.get('viewport'))
        if action=='resize':return await self.resize(value)
        if action=='audio_output':return await self.set_audio_output(value.get('mode'))
        if action in ('stop','heartbeat') and not local:need(self.active and value.get('session')==self.generation,'Stale native session')
        if action=='stop':
            stopped=await self.stop(generation=None if local else value.get('session'))
            need(stopped,'Stale native session');return self.status()
        if action=='heartbeat':
            self.last_heartbeat=time.monotonic();self.had_viewer=True;self.video_budget.feedback(value.get('link',value.get('browser')),time.monotonic());self.browser_metrics(value.get('browser'));return self.status()
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
        raw_writer=writer;self.connections.add(raw_writer);writer=HTTPResponseWriter(raw_writer);cors={};began=time.monotonic()
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
            origin=headers.get('origin','http://'+host);remote=origin!='http://'+host
            if remote:
                need(self.browser_access.trusted(origin),'Cross-origin request rejected')
                cors=self.browser_access.response_headers(origin)
                requested_method=headers.get('access-control-request-method','') if method=='OPTIONS' else method
                need(self.browser_access.allowed(requested_method,path),'Cross-origin route or method rejected')
                need(headers.get('sec-fetch-site','cross-site')=='cross-site','Cross-site request metadata rejected')
            else:need(headers.get('sec-fetch-site','same-origin') in ('same-origin','none'),'Cross-site request rejected')
            need('transfer-encoding' not in headers,'Transfer encoding rejected')
            length=int(headers.get('content-length','0'));need(0<=length<=4096,'Request limit')
            writer.phase='request_body'
            body=await asyncio.wait_for(reader.readexactly(length),5) if length else b''
            writer.phase='dispatch'
            if remote and method=='OPTIONS':
                need(not body,'Preflight request body rejected')
                extra=self.browser_access.preflight(origin,path,headers.get('access-control-request-method',''),headers.get('access-control-request-headers',''))
                await self.reply(writer,204,b'',extra=extra);return
            if remote and path=='/api/browser_session':
                need(headers.get('content-type','').split(';',1)[0].strip().lower()=='application/json','Browser session requires JSON')
                result=self.browser_access.issue(origin,json.loads(body or b'{}'))
                await self.reply(writer,200,json.dumps(result).encode(),extra=cors);return
            if remote:
                self.browser_access.authorize(origin,headers.get('authorization',''));authenticated=True
            else:
                cookie=dict(v.strip().split('=',1) for v in headers.get('cookie','').split(';') if '=' in v)
                authenticated=hmac.compare_digest(cookie.get('cdv3',''),self.token)
            if method=='GET' and path in ('/','/client.js','/audio.js','/canvas-video.js','/transport.js'):
                name='index.html' if path=='/' else path[1:];data=(ROOT.parent/'web'/name).read_bytes()
                await self.reply(writer,200,data,'text/html' if path=='/' else 'text/javascript',{'Set-Cookie':f'cdv3={self.token}; HttpOnly; SameSite=Strict; Path=/'})
            elif not authenticated:await self.reply(writer,403,b'Open the CarDash page first','text/plain')
            elif method=='GET' and path=='/api/status':await self.reply(writer,200,json.dumps(self.status()).encode(),extra=cors)
            elif method=='GET' and path=='/video':
                need(self.active and headers.get('x-cardash-session')==self.generation,'Stale native session');await self.viewer(writer,reader,response_headers=cors,continuous_decode=headers.get('x-cardash-renderer')=='webcodecs')
            elif method=='GET' and path=='/image':await self.image_viewer(writer,headers.get('x-cardash-session'),headers.get('x-cardash-frame','0'),reader,response_headers=cors)
            elif method=='GET' and path=='/audio':await self.audio_viewer(writer,headers.get('x-cardash-session'),reader,response_headers=cors)
            elif method=='POST' and path.startswith('/api/'):
                value=json.loads(body or b'{}');value['action']=path[5:];result=await self.action(value);await self.reply(writer,200,json.dumps(result).encode(),extra=cors)
            else:await self.reply(writer,404,b'Not found','text/plain')
        except Exception as e:
            error=str(e)[:256]
            self.log('browser_response_failed' if writer.started else 'browser_request_rejected',error=error,errorType=type(e).__name__[:64],phase=writer.phase,responseStarted=writer.started,responseBytes=writer.bytes_written,elapsedMs=min(10**9,max(0,round((time.monotonic()-began)*1000))))
            # Once headers/body were sent, another HTTP response would become
            # corrupt media (or trailing JSON) inside the existing response.
            if not writer.started:
                try:await self.reply(writer,e.status if isinstance(e,(BrowserAccessError,HTTPBusyError)) else 400,json.dumps({'error':error}).encode(),extra=cors)
                except (ConnectionError,OSError,asyncio.TimeoutError):pass
        finally:self.connections.discard(raw_writer);writer.close()
    @staticmethod
    def stream_headers(kind,extra=None):
        values={'Content-Type':kind,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Connection':'close',**(extra or {})}
        return ('HTTP/1.1 200 OK\r\n'+''.join(k+': '+v+'\r\n' for k,v in values.items())+'\r\n').encode()
    async def reply(self,writer,status,data,kind='application/json',extra=None):
        values={'Content-Type':kind,'Content-Length':str(len(data)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Connection':'close',**(extra or {})}
        header=f'HTTP/1.1 {status} '+({200:'OK',204:'No Content'}.get(status,'Error'))+'\r\n'+''.join(k+': '+v+'\r\n' for k,v in values.items())+'\r\n'
        response_phase(writer,'image_reply' if kind=='image/jpeg' else 'json_reply' if kind=='application/json' else 'asset_reply')
        writer.write(header.encode()+data);await asyncio.wait_for(writer.drain(),5)
    @staticmethod
    def clean_image_stats(value):
        allowed={'submitted','decoded','jpegFrames','inputDrops','decodedDrops','outputReplaced','decodeFailures','jpegFailures','pending','maxPending','latestSequence','latestBytes','workerBusy','waitingForKeyframe','hardwareAcceleration','lastStatus','width','height','fps'}
        return {k:v for k,v in value.items() if k in allowed and type(v) is int and -(2**31)<=v<=10**16}
    def image_stats(self):
        owner=self.images
        result={'active':bool(owner),'consumers':self.image_waiters,'error':self.image_error,'sequence':self.image_sequence}
        if owner:
            try:result.update(self.clean_image_stats(owner['decoder'].stats))
            except Exception:result['error']='Native image statistics unavailable'
        return result
    def schedule_image_close(self,owner,reason):
        if owner.get('closeTask'):return owner['closeTask']
        async def close():
            try:
                def finish():
                    owner['decoder'].close();return self.clean_image_stats(owner['decoder'].stats)
                counters=await asyncio.to_thread(finish)
                self.log('image_decoder_closed',reason=reason,stats=counters)
            except Exception as e:self.log('image_close_error',error=str(e)[:256])
        task=asyncio.create_task(close());owner['closeTask']=task;self.image_close_tasks.add(task);task.add_done_callback(self.image_close_tasks.discard);return task
    def invalidate_images(self,reason):
        # Synchronous configuration callbacks detach immediately. A constructor
        # currently awaiting its worker observes this epoch before publishing.
        self.image_epoch+=1;owner=self.images;self.images=None
        if owner:self.schedule_image_close(owner,reason)
    async def close_images(self,reason='session_end'):
        async with self.image_lock:self.invalidate_images(reason)
        pending=list(self.image_close_tasks)
        if pending:await asyncio.gather(*pending,return_exceptions=True)
    async def expire_images(self,now=None):
        now=time.monotonic() if now is None else now
        async with self.image_lock:
            owner=self.images
            if owner and now-owner['lastRequest']>10:self.invalidate_images('idle_timeout')
            else:owner=None
        if owner:await owner['closeTask']
    def image_current(self,owner,generation):
        return self.active and generation==self.generation and self.images is owner and self.muxer and owner['config']==self.muxer.config and self.display_verified
    async def get_images(self,generation):
        async with self.image_lock:
            need(self.active and generation==self.generation,'Stale native session')
            need(self.video and self.muxer and self.display_verified,'Native video is not ready')
            if self.images:
                need(self.images['session']==generation,'Stale image decoder')
                self.images['lastRequest']=time.monotonic();return self.images,False
            config=self.muxer.config;epoch=self.image_epoch;display=self.display
            build=asyncio.create_task(asyncio.to_thread(create_image_decoder,config,display.width,display.height))
            try:decoder=await asyncio.shield(build)
            except asyncio.CancelledError:
                # to_thread cannot cancel native construction. Retain its result
                # long enough to close it; never publish it into a new session.
                async def discard():
                    try:
                        decoder=await build;await asyncio.to_thread(decoder.close)
                    except Exception as e:self.log('image_close_error',error=str(e)[:256])
                task=asyncio.create_task(discard());self.image_close_tasks.add(task);task.add_done_callback(self.image_close_tasks.discard);raise
            except Exception as e:
                if generation==self.generation:self.image_error=str(e)[:256]
                self.log('image_init_error',error=str(e)[:256]);raise
            owner={'decoder':decoder,'session':generation,'config':config,'lastRequest':time.monotonic(),'responses':0,'sequenceBase':self.image_sequence}
            if not self.active or generation!=self.generation or epoch!=self.image_epoch or not self.muxer or config!=self.muxer.config:
                await self.schedule_image_close(owner,'stale_construction');raise ValueError('Stale native session or video configuration')
            self.images=owner;self.image_error='';self.log('image_decoder_started',width=display.width,height=display.height,fps=10)
            return owner,True
    async def image_viewer(self,writer,generation,after='0',reader=None,response_headers=None):
        need(self.active and generation==self.generation,'Stale native session')
        need(isinstance(after,str) and after.isdigit() and len(after)<=16 and int(after)<=9007199254740991,'Image sequence invalid')
        need(self.image_waiters<2,'Two image requests are already pending')
        sequence=int(after);self.image_waiters+=1
        try:
            owner,created=await self.get_images(generation)
            need(self.image_current(owner,generation),'Stale native session or video configuration')
            self.had_viewer=True;self.last_heartbeat=time.monotonic()
            if created:
                try:await self.request_keyframe(generation,'viewer_join')
                except Exception:
                    if self.images is owner:self.invalidate_images('keyframe_error')
                    raise
            deadline=time.monotonic()+IMAGE_WAIT_SECONDS
            while True:
                need(self.image_current(owner,generation),'Stale native session or video configuration')
                if writer.is_closing() or (reader and reader.at_eof()):return
                frame=owner['decoder'].latest(max(0,sequence-owner['sequenceBase']))
                if frame:
                    local_sequence,timestamp,data=frame.get('sequence'),frame.get('timestamp'),frame.get('data')
                    need(type(local_sequence) is int and local_sequence>0,'Native JPEG sequence invalid')
                    n=owner['sequenceBase']+local_sequence
                    need(sequence<n<=9007199254740991 and type(timestamp) is int and 0<=timestamp<2**63,'Native JPEG metadata invalid')
                    need((frame.get('width'),frame.get('height'))==(self.display.width,self.display.height),'Native JPEG dimensions invalid')
                    need(isinstance(data,bytes) and 4<=len(data)<=4*1024*1024 and data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'),'Native JPEG payload invalid')
                    # No await occurs between the final generation check and
                    # reply() writing its response bytes to this exact socket.
                    need(self.image_current(owner,generation),'Stale native session or video configuration')
                    self.image_sequence=max(self.image_sequence,n)
                    await self.reply(writer,200,data,'image/jpeg',{**(response_headers or {}),'X-CarDash-Frame':str(n),'X-CarDash-Time':str(timestamp)})
                    owner['responses']+=1
                    if owner['responses']==1 or owner['responses']%300==0:self.log('image_frame',sequence=n,bytes=len(data),width=frame['width'],height=frame['height'])
                    return
                if time.monotonic()>=deadline:
                    await self.reply(writer,204,b'','image/jpeg',response_headers);return
                await asyncio.sleep(.02)
        except Exception as e:
            if generation==self.generation:self.image_error=str(e)[:256]
            raise
        finally:self.image_waiters-=1
    async def viewer(self,writer,reader=None,response_headers=None,continuous_decode=False):
        need(self.active and self.video and self.muxer,'Native video is not ready')
        if len(self.viewers)>=2:raise HTTPBusyError('Two viewers are already connected')
        q=asyncio.Queue(maxsize=90);state={'ready':False,'bytes':0,'closed':False,'session':self.generation,'continuous_decode':continuous_decode};self.viewers[q]=state;self.had_viewer=True;self.last_heartbeat=time.monotonic()
        try:
            response_phase(writer,'video_headers')
            writer.write(self.stream_headers('video/mp4',response_headers));await asyncio.wait_for(writer.drain(),3)
            if not self.active:return
            response_phase(writer,'video_keyframe')
            await self.request_keyframe(state['session'],'viewer_join')
            while self.active and state['session']==self.generation and not state['closed'] and not (reader and reader.at_eof()):
                response_phase(writer,'video_wait')
                try:fragment=await asyncio.wait_for(q.get(),4)
                except asyncio.TimeoutError:
                    if writer.is_closing() or (reader and reader.at_eof()):break
                    continue
                if fragment is None or not self.active or state['session']!=self.generation or (reader and reader.at_eof()):break
                state['bytes']-=len(fragment);response_phase(writer,'video_drain');writer.write(fragment);await asyncio.wait_for(writer.drain(),3)
        finally:
            self.viewers.pop(q,None)
            # A retiring connection must not release a replacement viewer's contact.
            if self.last_pointer and state['session']==self.generation and not any(v['session']==self.generation and not v.get('closed',False) for v in self.viewers.values()):
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
