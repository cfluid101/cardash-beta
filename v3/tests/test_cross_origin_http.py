import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver
from h264_fixture import configuration

ORIGIN='https://cfluid101.github.io'

class CrossOriginHTTPTest(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/not-used'))
  self.server=await asyncio.start_server(self.r.http,'127.0.0.1',0,limit=16384)
  self.port=self.server.sockets[0].getsockname()[1];self.r.args.port=self.port
 async def asyncTearDown(self):
  await self.r.close_images()
  self.server.close();await self.server.wait_closed();self.tmp.cleanup()
 async def request(self,path='/api/status',method='GET',headers=None,body=b''):
  reader,writer=await asyncio.open_connection('127.0.0.1',self.port)
  h={'Host':f'127.0.0.1:{self.port}','Origin':ORIGIN,'Sec-Fetch-Site':'cross-site','Content-Length':str(len(body)),**(headers or {})}
  writer.write((f'{method} {path} HTTP/1.1\r\n'+''.join(f'{k}: {v}\r\n' for k,v in h.items())+'\r\n').encode()+body)
  await writer.drain();raw=await asyncio.wait_for(reader.read(),5);writer.close();await writer.wait_closed()
  head,data=raw.split(b'\r\n\r\n',1);lines=head.decode().split('\r\n')
  return int(lines[0].split()[1]),dict(x.split(': ',1) for x in lines[1:]),data
 async def bootstrap(self,client='a'*32):
  code,headers,body=await self.request('/api/browser_session','POST',{'Content-Type':'application/json'},json.dumps({'version':1,'clientId':client}).encode())
  self.assertEqual(code,200,body);self.assertEqual(headers.get('Access-Control-Allow-Origin'),ORIGIN)
  self.assertNotIn('Set-Cookie',headers);self.assertIn('no-store',headers['Cache-Control'])
  return json.loads(body)['token']
 async def test_trusted_origin_bootstrap_status_and_existing_cookie_is_not_remote_auth(self):
  token=await self.bootstrap();self.assertNotEqual(token,self.r.token);self.assertFalse(self.r.active)
  code,headers,body=await self.request(headers={'Authorization':'Bearer '+token})
  self.assertEqual(code,200);self.assertEqual(json.loads(body)['version'],self.r.status()['version'])
  code,headers,body=await self.request(headers={'Cookie':'cdv3='+self.r.token})
  self.assertEqual(code,401);self.assertEqual(headers['Access-Control-Allow-Origin'],ORIGIN)
  self.assertNotIn(token,(Path(self.tmp.name)/'diagnostic.ndjson').read_text())
 async def test_origin_and_host_fail_closed_without_cors_or_native_mutation(self):
  token=await self.bootstrap()
  for changed in ({'Origin':'https://cfluid101.github.io.evil.invalid'},{'Origin':'null'},{'Origin':'http://cfluid101.github.io'},{'Host':'evil.invalid:8890'}):
   code,headers,body=await self.request('/api/start','POST',{'Authorization':'Bearer '+token,'Content-Type':'application/json',**changed},b'{}')
   self.assertGreaterEqual(code,400);self.assertNotIn('Access-Control-Allow-Origin',headers);self.assertFalse(self.r.active)
 async def test_preflight_needs_no_cookie_but_cannot_authorize_an_unlisted_route(self):
  code,headers,body=await self.request('/video','OPTIONS',{'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization,x-cardash-session'})
  self.assertEqual(code,204,body);self.assertEqual(headers['Access-Control-Allow-Methods'],'GET')
  self.assertNotIn('Access-Control-Allow-Credentials',headers);self.assertFalse(self.r.active)
  for path,method,names in [('/api/report','POST','authorization'),('/video','POST','authorization'),('/video','GET','authorization,x-evil')]:
   code,headers,body=await self.request(path,'OPTIONS',{'Access-Control-Request-Method':method,'Access-Control-Request-Headers':names})
   self.assertGreaterEqual(code,400);self.assertNotIn('Access-Control-Allow-Methods',headers);self.assertEqual(headers.get('Access-Control-Allow-Origin'),ORIGIN)
 async def test_auth_and_stale_generation_errors_are_readable_without_credentials_leak(self):
  code,headers,body=await self.request(headers={'Authorization':'Bearer '+('f'*64)})
  self.assertEqual(code,401);self.assertEqual(headers['Access-Control-Allow-Origin'],ORIGIN)
  token=await self.bootstrap();self.r.active=True;self.r.generation='new'
  code,headers,body=await self.request('/api/touch','POST',{'Authorization':'Bearer '+token,'Content-Type':'application/json'},b'{"session":"old","x":0.5,"y":0.5,"down":true}')
  self.assertEqual(code,400);self.assertIn(b'Stale native session',body);self.assertEqual(headers['Access-Control-Allow-Origin'],ORIGIN)
  self.assertNotIn(token,body.decode());self.r.active=False
 async def test_image_bytes_metadata_and_empty_poll_are_readable_cross_origin(self):
  token=await self.bootstrap();self.r.active=True;self.r.generation='current';self.r.video=object();self.r.configure(configuration())
  self.r.request_keyframe=AsyncMock()
  jpeg=b'\xff\xd8test-jpeg\xff\xd9'
  class Decoder:
   closed=False
   stats={}
   def latest(self,after):return {'sequence':1,'data':jpeg,'width':1280,'height':720,'timestamp':1234} if after<1 else None
   def close(self):self.closed=True
  decoder=Decoder()
  headers={'Authorization':'Bearer '+token,'X-CarDash-Session':'current','X-CarDash-Frame':'0'}
  with patch('server.create_image_decoder',return_value=decoder),patch('server.IMAGE_WAIT_SECONDS',.01):
   code,h,data=await self.request('/image',headers=headers)
   self.assertEqual(code,200,data);self.assertEqual(data,jpeg);self.assertEqual(h['Access-Control-Allow-Origin'],ORIGIN)
   self.assertEqual(h['X-CarDash-Frame'],'1');self.assertIn('X-CarDash-Frame',h['Access-Control-Expose-Headers']);self.assertIn('X-CarDash-Time',h['Access-Control-Expose-Headers'])
   code,h,data=await self.request('/image',headers={**headers,'X-CarDash-Frame':'1'})
   self.assertEqual(code,204);self.assertEqual(data,b'');self.assertEqual(h['Access-Control-Allow-Origin'],ORIGIN)
  self.r.active=False
 async def test_local_bearer_is_not_a_cookie_and_remote_token_does_not_grant_local_only_actions(self):
  token=await self.bootstrap()
  code,h,data=await self.request(headers={'Origin':f'http://127.0.0.1:{self.port}','Sec-Fetch-Site':'same-origin','Authorization':'Bearer '+token})
  self.assertEqual(code,403);self.assertNotIn('Access-Control-Allow-Origin',h)
  for action in ('prepare','import','report','release_audio'):
   code,h,data=await self.request('/api/'+action,'POST',{'Authorization':'Bearer '+token,'Content-Type':'application/json'},b'{}')
   self.assertGreaterEqual(code,400);self.assertEqual(h.get('Access-Control-Allow-Origin'),ORIGIN)
  self.assertFalse(self.r.provisioning);self.assertIsNone(self.r.helper)
 async def test_local_transport_asset_keeps_automatic_cookie_bootstrap(self):
  code,h,data=await self.request('/transport.js',headers={'Origin':f'http://127.0.0.1:{self.port}','Sec-Fetch-Site':'same-origin'})
  self.assertEqual(code,200);self.assertEqual(h['Content-Type'],'text/javascript');self.assertIn('HttpOnly; SameSite=Strict',h['Set-Cookie'])
  self.assertNotIn('Access-Control-Allow-Origin',h)
 async def test_canvas_draw_diagnostics_are_bounded_integers_not_visibility_claims(self):
  log=Path(self.tmp.name)/'diagnostic.ndjson'
  self.r.browser_metrics({'canvasDrawCalls':17})
  rows=[json.loads(line) for line in log.read_text().splitlines()]
  self.assertEqual(rows[-1].get('canvasDrawCalls'),17)
  before=log.read_text()
  for invalid in (True,-1,1.5,10**10+1,'17'):
   self.r.last_browser_metrics=-float('inf');self.r.browser_metrics({'canvasDrawCalls':invalid})
  self.assertEqual(log.read_text(),before)
 async def test_streaming_headers_are_cors_enabled_before_video_and_audio_bytes(self):
  token=await self.bootstrap();self.r.active=True;self.r.generation='generation';self.r.video=object();self.r.muxer=object();self.r.audio_output='browser'
  async def keyframe(*args,**kwargs):pass
  for path,kind in (('/video','video/mp4'),('/audio','application/octet-stream')):
   reader,writer=await asyncio.open_connection('127.0.0.1',self.port)
   writer.write(f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nOrigin: {ORIGIN}\r\nSec-Fetch-Site: cross-site\r\nAuthorization: Bearer {token}\r\nX-CarDash-Session: generation\r\n\r\n'.encode());await writer.drain()
   with patch.object(self.r,'request_keyframe',keyframe):head=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),2)
   self.assertIn(b'200 OK',head);self.assertIn(f'Access-Control-Allow-Origin: {ORIGIN}'.encode(),head);self.assertIn(f'Content-Type: {kind}'.encode(),head)
   writer.close();await writer.wait_closed()
  self.r.active=False
  for q in list(self.r.viewers):q.put_nowait(None)
  for q in list(self.r.audio_viewers):q.put_nowait(None)
  await asyncio.sleep(.02)


if __name__=='__main__':unittest.main()
