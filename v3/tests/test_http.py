import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver
class HttpTest(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/not-used'))
  self.server=await asyncio.start_server(self.r.http,'127.0.0.1',0,limit=16384);self.port=self.server.sockets[0].getsockname()[1];self.r.args.port=self.port
 async def asyncTearDown(self):
  self.server.close();await self.server.wait_closed();self.tmp.cleanup()
 async def request(self,path='/',method='GET',extra='',body=b''):
  r,w=await asyncio.open_connection('127.0.0.1',self.port)
  w.write(f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Length: {len(body)}\r\n{extra}\r\n'.encode()+body);await w.drain();result=await r.read();w.close();await w.wait_closed();return result
 async def test_automatic_cookie_and_cross_origin_rejection(self):
  first=await self.request();self.assertIn(b'200 OK',first);self.assertIn(b'HttpOnly; SameSite=Strict',first)
  forbidden=await self.request('/api/status');self.assertIn(b'403',forbidden)
  allowed=await self.request('/api/status',extra=f'Cookie: cdv3={self.r.token}\r\n');self.assertIn(b'200 OK',allowed)
  cross=await self.request('/api/start','POST',f'Cookie: cdv3={self.r.token}\r\nOrigin: https://unrelated.invalid\r\n',b'{}');self.assertIn(b'Cross-origin request rejected',cross)
  self.assertIsNone(self.r.helper)
 async def test_canvas_module_is_explicitly_served_without_expanding_file_access(self):
  with patch.object(Path,'read_bytes',return_value=b'// renderer module'):
   result=await self.request('/canvas-video.js')
  self.assertIn(b'200 OK',result);self.assertIn(b'Content-Type: text/javascript',result);self.assertTrue(result.endswith(b'// renderer module'))
  forbidden=await self.request('/../backend/server.py',extra=f'Cookie: cdv3={self.r.token}\r\n');self.assertIn(b'404',forbidden)
 async def test_unprovisioned_start_is_actionable_and_does_not_launch(self):
  result=await self.request('/api/start','POST',f'Cookie: cdv3={self.r.token}\r\n',b'{}')
  self.assertIn(b'Prepare Native Preview',result);self.assertIsNone(self.r.helper)
 async def test_old_session_cannot_deliver_touch_to_replacement(self):
  self.r.active=True;self.r.frames=10;self.r.generation='new-session'
  with self.assertRaisesRegex(ValueError,'Stale native session'):
   await self.r.touch({'x':.5,'y':.5,'down':True,'session':'old-session'})
 async def test_queued_command_rechecks_session_after_waiting(self):
  self.r.active=True;self.r.generation='old-session'
  await self.r.command_lock.acquire()
  pending=asyncio.create_task(self.r.command({'type':'hidSendReport'},'old-session'))
  await asyncio.sleep(0)
  self.r.generation='new-session';self.r.command_lock.release()
  with self.assertRaisesRegex(ValueError,'Stale native session'):await pending
 async def test_report_bounds_large_supporting_file_and_preserves_json_lines(self):
  path=Path(self.tmp.name)/'service-bootstrap.log';path.write_text('x'*(3*1024*1024))
  report=(await self.r.action({'action':'report'},local=True))['report']
  records=[json.loads(line) for line in report.splitlines()]
  self.assertEqual(len(records[0]['text']),2*1024*1024)
  self.assertTrue(any(r['event']=='service_started' for r in records))
  self.assertLessEqual(len(report),4*1024*1024)
 async def test_timed_out_error_reply_closes_request_without_escaping(self):
  # Device Python 3.9's asyncio.TimeoutError is not an OSError. Newer host
  # Python aliases it to the built-in TimeoutError, which can hide this bug.
  class DeviceTimeoutError(Exception):pass
  class StalledWriter:
   def __init__(self,port):self.port=port;self.closed=False;self.writes=[]
   def get_extra_info(self,name):return ('127.0.0.1',self.port)
   def write(self,data):self.writes.append(data)
   async def drain(self):raise DeviceTimeoutError()
   def close(self):self.closed=True
  reader=asyncio.StreamReader();writer=StalledWriter(self.port)
  reader.feed_data(f'GET /api/status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nCookie: cdv3={self.r.token}\r\n\r\n'.encode());reader.feed_eof()
  with patch.object(asyncio,'TimeoutError',DeviceTimeoutError):
   await self.r.http(reader,writer)
  self.assertTrue(writer.closed);self.assertNotIn(writer,self.r.connections)
  self.assertEqual(len(writer.writes),1)
  self.assertTrue(writer.writes[0].startswith(b'HTTP/1.1 200'))
  self.assertIn(b'200 OK',await self.request())
if __name__=='__main__':unittest.main()
