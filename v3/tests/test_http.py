import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
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
if __name__=='__main__':unittest.main()
