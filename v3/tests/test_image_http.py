import asyncio
import threading
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver
from h264_fixture import configuration

JPEG=b'\xff\xd8test-jpeg\xff\xd9'
class Decoder:
    def __init__(self,ready=True):self.closed=0;self.fed=[];self.frame={'sequence':1,'data':JPEG,'width':1280,'height':720,'timestamp':1234567} if ready else None
    def feed(self,data,timestamp):self.fed.append((data,timestamp));return True
    def latest(self,after=0):return self.frame if self.frame and self.frame['sequence']>after and not self.closed else None
    @property
    def stats(self):return {'submitted':len(self.fed),'jpegFrames':int(self.frame is not None),'pending':0,'width':1280,'height':720,'fps':10,'secret':'never expose'}
    def close(self):self.closed+=1

class ImageHTTPTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/unused'))
        self.r.active=True;self.r.generation='current';self.r.audio_lease=Mock();self.r.video=types.SimpleNamespace(close=Mock());self.r.command=AsyncMock(return_value=1);self.r.configure(configuration())
        self.factory=Mock(return_value=Decoder());self.patch=patch('server.create_image_decoder',self.factory,create=True);self.patch.start()
        self.server=await asyncio.start_server(self.r.http,'127.0.0.1',0,limit=16384);self.port=self.server.sockets[0].getsockname()[1];self.r.args.port=self.port
    async def asyncTearDown(self):
        await self.r.stop();self.server.close();await self.server.wait_closed();self.patch.stop();self.tmp.cleanup()
    async def request(self,*,session='current',sequence='0',cookie=True):
        reader,writer=await asyncio.open_connection('127.0.0.1',self.port)
        headers=f'Host: 127.0.0.1:{self.port}\r\nX-CarDash-Session: {session}\r\nX-CarDash-Frame: {sequence}\r\n'
        if cookie:headers+=f'Cookie: cdv3={self.r.token}\r\n'
        writer.write(('GET /image HTTP/1.1\r\n'+headers+'\r\n').encode());await writer.drain();result=await reader.read();writer.close();await writer.wait_closed();return result
    def writer(self):return types.SimpleNamespace(write=Mock(),drain=AsyncMock(),is_closing=lambda:False)

    async def test_first_authenticated_image_lazily_constructs_once_and_exposes_bounded_headers(self):
        self.assertEqual(self.r.status()['imageStats']['active'],False);self.factory.assert_not_called()
        for _ in range(2):
            result=await self.request();self.assertIn(b'200 OK',result);self.assertIn(b'Content-Type: image/jpeg',result);self.assertIn(b'Cache-Control: no-store',result);self.assertIn(b'X-CarDash-Frame: 1',result);self.assertIn(b'X-CarDash-Time: 1234567',result);self.assertTrue(result.endswith(JPEG))
        self.factory.assert_called_once();self.assertEqual(self.r.command.await_count,1);self.assertTrue(self.r.status()['imageStats']['active']);self.assertNotIn('secret',self.r.status()['imageStats'])
        self.r.frame(bytes.fromhex('000000026501'),100);self.assertEqual(self.factory.return_value.fed,[(bytes.fromhex('000000026501'),100)])
        await self.r.stop();self.assertEqual(self.factory.return_value.closed,1);self.assertFalse(self.r.status()['imageStats']['active'])

    async def test_stale_invalid_and_unauthenticated_requests_do_no_decoder_work(self):
        self.assertIn(b'403',await self.request(cookie=False));self.assertIn(b'Stale native session',await self.request(session='old'))
        for sequence in ('-1','1.2','+2','nan','9007199254740992','x'*17):self.assertIn(b'400',await self.request(sequence=sequence))
        self.factory.assert_not_called()
        self.r.frame(bytes.fromhex('000000026501'),100);self.factory.assert_not_called()

    async def test_pending_images_are_limited_and_timeout_returns_empty_204(self):
        decoder=Decoder(False);self.factory.return_value=decoder
        first=asyncio.create_task(self.r.image_viewer(self.writer(),'current','0'));second=asyncio.create_task(self.r.image_viewer(self.writer(),'current','0'))
        for _ in range(100):
            if getattr(self.r,'image_waiters',0)==2 and self.r.images is not None:break
            await asyncio.sleep(.01)
        with self.assertRaisesRegex(ValueError,'Two'):await self.r.image_viewer(self.writer(),'current','0')
        decoder.frame={'sequence':1,'data':JPEG,'width':1280,'height':720,'timestamp':1234567};await asyncio.gather(first,second)
        writer=self.writer()
        with patch('server.IMAGE_WAIT_SECONDS',0.03):await self.r.image_viewer(writer,'current','1')
        self.assertTrue(writer.write.call_args.args[0].startswith(b'HTTP/1.1 204'));self.assertEqual(self.r.image_waiters,0)

    async def test_stop_waits_for_inflight_constructor_and_closes_stale_result_only(self):
        entered=threading.Event();release=threading.Event();decoder=Decoder()
        def make(*_):entered.set();release.wait(3);return decoder
        self.factory.side_effect=make
        image=asyncio.create_task(self.r.image_viewer(self.writer(),'current','0'))
        while not entered.is_set():await asyncio.sleep(.01)
        stop=asyncio.create_task(self.r.stop());await asyncio.sleep(.01);self.assertFalse(stop.done());self.assertFalse(self.r.active)
        release.set()
        with self.assertRaisesRegex(ValueError,'Stale'):await image
        await stop;self.assertEqual(decoder.closed,1);self.assertIsNone(self.r.images)

    async def test_old_waiting_response_cannot_send_a_frame_from_replacement(self):
        decoder=Decoder(False);self.factory.return_value=decoder;writer=self.writer();request=asyncio.create_task(self.r.image_viewer(writer,'current','0'))
        while self.r.images is None:await asyncio.sleep(.01)
        self.r.generation='replacement';decoder.frame={'sequence':1,'data':JPEG,'width':1280,'height':720,'timestamp':1234567}
        with self.assertRaisesRegex(ValueError,'Stale'):await request
        writer.write.assert_not_called()

    async def test_idle_expiry_and_config_change_detach_the_specific_decoder(self):
        await self.request();old=self.factory.return_value;self.r.images['lastRequest']=0
        await self.r.expire_images(now=11);self.assertEqual(old.closed,1);self.assertIsNone(self.r.images)
        new=Decoder();self.factory.return_value=new;await self.request();self.assertTrue(self.r.status()['imageStats']['active'])
        changed=bytearray(configuration());changed[3]=32;self.r.configure(bytes(changed));self.assertIsNone(self.r.images)
        await self.r.close_images();self.assertEqual(new.closed,1)
        await self.r.stop();self.assertEqual(new.closed,1)

    async def test_config_change_during_constructor_discards_old_decoder_before_publishing(self):
        entered=threading.Event();release=threading.Event();old=Decoder()
        def make(*_):entered.set();release.wait(3);return old
        self.factory.side_effect=make;request=asyncio.create_task(self.r.image_viewer(self.writer(),'current','0'))
        while not entered.is_set():await asyncio.sleep(.01)
        changed=bytearray(configuration());changed[3]=32;self.r.configure(bytes(changed));release.set()
        with self.assertRaisesRegex(ValueError,'Stale'):await request
        self.assertEqual(old.closed,1);self.assertIsNone(self.r.images)
        new=Decoder();self.factory.side_effect=None;self.factory.return_value=new;await self.request()
        await asyncio.sleep(.02);self.assertEqual(new.closed,0);self.assertIs(self.r.images['decoder'],new)

    async def test_old_async_close_cannot_detach_or_close_replacement(self):
        old=self.factory.return_value;await self.request();entered=threading.Event();release=threading.Event()
        def close():entered.set();release.wait(3);old.closed+=1
        old.close=close;changed=bytearray(configuration());changed[3]=32;self.r.configure(bytes(changed))
        while not entered.is_set():await asyncio.sleep(.01)
        new=Decoder();self.factory.return_value=new;await self.request();release.set()
        tasks=list(self.r.image_close_tasks)
        if tasks:await asyncio.gather(*tasks)
        self.assertEqual(old.closed,1);self.assertEqual(new.closed,0);self.assertIs(self.r.images['decoder'],new)

    async def test_cancelled_constructor_is_reaped_without_publishing_native_resources(self):
        entered=threading.Event();release=threading.Event();decoder=Decoder()
        def make(*_):entered.set();release.wait(3);return decoder
        self.factory.side_effect=make;request=asyncio.create_task(self.r.image_viewer(self.writer(),'current','0'))
        while not entered.is_set():await asyncio.sleep(.01)
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):await request
        release.set();await self.r.close_images();self.assertEqual(decoder.closed,1);self.assertIsNone(self.r.images)

    async def test_sequence_remains_monotonic_after_idle_decoder_recreation(self):
        first=await self.request();self.assertIn(b'X-CarDash-Frame: 1',first)
        self.r.images['lastRequest']=0;await self.r.expire_images(now=11);self.factory.return_value=Decoder()
        with patch('server.IMAGE_WAIT_SECONDS',0.03):second=await self.request(sequence='1')
        self.assertIn(b'200 OK',second);self.assertIn(b'X-CarDash-Frame: 2',second)
