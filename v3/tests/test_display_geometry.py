import asyncio
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver,ROOT
from h264_fixture import configuration

class DisplayGeometryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/unused'));self.r.audio_lease=Mock()
        folder=Path(self.tmp.name,'accessory');folder.mkdir();(folder/'certificate.p7b').write_bytes(b'cert');(folder/'identity.pk8').write_bytes(b'key')
        self.child=types.SimpleNamespace(pid=123,returncode=None,terminate=Mock(),kill=Mock(),wait=AsyncMock(return_value=0))
        self.stack=ExitStack()
        for name,value in [('transport_status',{'ready':True}),('audio_route_status',{'ready':True}),('crypto.certificate_matches',True),('crypto.public',bytes(32))]:self.stack.enter_context(patch('server.'+name,return_value=value))
        self.stack.enter_context(patch('server.CERT_SHA256',hashlib.sha256(b'cert').hexdigest()));self.stack.enter_context(patch('server.asyncio.create_subprocess_exec',new_callable=AsyncMock,return_value=self.child));self.r.watch_helper=AsyncMock()
    async def asyncTearDown(self):
        await self.r.stop();self.stack.close();self.tmp.cleanup()

    async def test_tesla_viewport_changes_native_display_hid_and_mp4_together(self):
        before=json.loads(Path(self.tmp.name,'identity.json').read_text())
        status=await self.r.action({'action':'start','viewport':{'width':773,'height':601}})
        self.assertEqual((status['sourceWidth'],status['sourceHeight']),(1088,846))
        self.assertEqual(status['requestedViewport'],{'width':773,'height':601})
        info=self.r.receiver_info();d=info['displays'][0]
        self.assertEqual((d['widthPixels'],d['heightPixels'],d['widthPhysical'],d['heightPhysical']),(1088,846,260,202))
        self.assertEqual((d['viewAreas'][0]['widthPixels'],d['viewAreas'][0]['safeArea']['heightPixels']),(1088,846))
        descriptor=info['hidDevices'][0]['hidDescriptor'];self.assertEqual(descriptor.count(b'\x26'+struct.pack('<H',1088)+b'\x09\x30'),2);self.assertEqual(descriptor.count(b'\x26'+struct.pack('<H',846)+b'\x09\x31'),2)
        self.r.configure(configuration(1088,846));self.assertEqual((self.r.muxer.width,self.r.muxer.height),(1088,846));self.assertTrue(self.r.status()['displayVerified'])
        self.r.frames=1;self.r.command=AsyncMock(return_value=1)
        await self.r.touch({'session':self.r.generation,'x':1,'y':1,'down':True})
        self.assertEqual(struct.unpack_from('<HH',self.r.command.call_args.args[0]['hidReport'],2),(1088,846))
        self.assertEqual(json.loads(Path(self.tmp.name,'identity.json').read_text()),before);self.assertFalse(Path(self.tmp.name,'settings.json').exists())

    async def test_start_does_not_mutate_active_geometry_and_resize_is_generation_scoped(self):
        a=await self.r.action({'action':'start','viewport':{'width':773,'height':526}});session=a['session']
        again=await self.r.action({'action':'start','viewport':{'width':1920,'height':800}})
        self.assertEqual(again['session'],session);self.assertEqual(again['requestedViewport'],a['requestedViewport'])
        await self.r.lock.acquire();stale=asyncio.create_task(self.r.action({'action':'resize','session':'old','viewport':{'width':773,'height':601}}));await asyncio.sleep(0);self.r.lock.release()
        with self.assertRaisesRegex(ValueError,'Stale'):await stale
        self.assertEqual(self.r.generation,session)
        changed=await self.r.action({'action':'resize','session':session,'viewport':{'width':773,'height':601}})
        self.assertNotEqual(changed['session'],session);self.assertEqual((changed['sourceWidth'],changed['sourceHeight']),(1088,846));self.assertEqual(changed['audioOutput'],'phone')
        with self.assertRaisesRegex(ValueError,'Stale'):await self.r.touch({'session':session,'x':.5,'y':.5,'down':True})
        self.assertFalse(await self.r.stop(generation=session));self.assertTrue(self.r.active)

    async def test_invalid_resize_cannot_end_current_session_and_same_geometry_is_noop(self):
        s=await self.r.action({'action':'start'})
        for viewport in [None,{},True,{'width':float('nan'),'height':700},{'width':-1,'height':600},{'width':True,'height':700},{'width':1e9,'height':700}]:
            with self.assertRaises(ValueError):await self.r.action({'action':'resize','session':s['session'],'viewport':viewport})
            self.assertEqual(self.r.generation,s['session'])
        same=await self.r.action({'action':'resize','session':s['session'],'viewport':{'width':1280,'height':720}})
        self.assertEqual(same['session'],s['session'])
        self.assertEqual(self.r.receiver_info(),plistlib.loads((ROOT/'receiver-info.plist').read_bytes()))

    async def test_resize_holds_lifecycle_lock_and_rejects_second_old_request(self):
        first=await self.r.action({'action':'start'});entered=asyncio.Event();release=asyncio.Event()
        async def wait_child():entered.set();await release.wait();return 0
        self.child.wait=wait_child
        changing=asyncio.create_task(self.r.action({'action':'resize','session':first['session'],'viewport':{'width':773,'height':601}}))
        await entered.wait()
        stale=asyncio.create_task(self.r.action({'action':'resize','session':first['session'],'viewport':{'width':773,'height':526}}))
        output=asyncio.create_task(self.r.action({'action':'audio_output','mode':'browser'}))
        await asyncio.sleep(0);self.assertFalse(stale.done());self.assertFalse(output.done());release.set()
        newer=await changing
        with self.assertRaisesRegex(ValueError,'Stale'):await stale
        with self.assertRaisesRegex(ValueError,'Stop'):await output
        self.assertEqual(self.r.generation,newer['session']);self.assertEqual(self.r.display.viewport,{'width':773,'height':601});self.assertEqual(self.r.audio_output,'phone')

    async def test_sps_mismatch_cannot_be_mislabeled_as_requested_resolution(self):
        await self.r.action({'action':'start','viewport':{'width':773,'height':601}})
        with self.assertRaisesRegex(ValueError,'1088.*846'):
            self.r.configure(configuration(1280,720))
        self.assertIsNone(self.r.muxer);self.assertFalse(self.r.status()['displayVerified'])
        self.assertEqual(self.r.status()['actualSource'],{'width':1280,'height':720})

class DisplayParserTest(unittest.TestCase):
    def test_geometry_is_even_bounded_and_tesla_aspect_is_not_clamped_to_4_by_3(self):
        from display import geometry
        for w,h in [(773,526),(773,601),(1920,800),(1280,720),(900,950),(16384,4096)]:
            g=geometry({'width':w,'height':h});self.assertLessEqual(g.width,1280);self.assertLessEqual(g.height,960);self.assertLessEqual(g.width*g.height,921600);self.assertEqual(g.width%2,0);self.assertEqual(g.height%2,0);self.assertGreaterEqual(g.width,g.height)
            self.assertLess(abs(g.width/g.height-max(1,w/h))/max(1,w/h),.005)
        self.assertEqual(geometry().width,1280)
    def test_crop_aware_sps_dimensions_and_malformed_input(self):
        from display import avc_dimensions
        for width,height,opts in [(1280,720,{}),(1088,846,{}),(1162,790,{'profile':66}),(640,476,{'interlaced':True}),(639,479,{'chroma':3})]:
            self.assertEqual(avc_dimensions(configuration(width,height,**opts)),(width,height))
        for raw in [b'',b'\x01'*8,configuration()[:10],bytes.fromhex('0164001fffe100046764001f01000268ee')]:
            with self.assertRaises(ValueError):avc_dimensions(raw)

class IndependentSpsTest(unittest.TestCase):
    def test_native_sizing_parser_reads_independently_encoded_h264(self):
        import re,shutil,subprocess
        from display import avc_dimensions
        if not shutil.which('ffmpeg'):self.skipTest('ffmpeg host encoder unavailable')
        data=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','color=size=1088x846:rate=1','-frames:v','1','-c:v','libx264','-profile:v','high','-pix_fmt','yuv420p','-f','h264','pipe:1'])
        nals=[n for n in re.split(b'\x00\x00(?:\x00)?\x01',data) if n]
        sps=next(n for n in nals if n[0]&31==7);pps=next(n for n in nals if n[0]&31==8)
        record=b'\x01'+sps[1:4]+b'\xff\xe1'+len(sps).to_bytes(2,'big')+sps+b'\x01'+len(pps).to_bytes(2,'big')+pps
        self.assertEqual(avc_dimensions(record),(1088,846))
