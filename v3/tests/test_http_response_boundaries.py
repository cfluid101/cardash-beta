import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver


class HTTPResponseBoundaryTest(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.r=Receiver(types.SimpleNamespace(state=self.tmp.name,port=8890,capture=None,helper='/unused'))
  self.r.active=True;self.r.generation='current';self.r.video=object();self.r.muxer=object()
  self.r.audio_output='browser';self.r.command=AsyncMock(return_value=1)
 async def asyncTearDown(self):self.tmp.cleanup()
 async def fail_response(self,path,body_failure=False):
  receiver=self.r
  class Writer:
   closed=False
   def __init__(self):self.writes=[];self.drains=0
   def get_extra_info(self,name):return ('127.0.0.1',8890)
   def write(self,data):self.writes.append(data)
   def is_closing(self):return False
   def close(self):self.closed=True
   async def drain(self):
    self.drains+=1
    if body_failure and self.drains==1:
     if path=='/video':
      q,state=next(iter(receiver.viewers.items()));state['bytes']=5;q.put_nowait(b'frame')
     elif path=='/audio':
      q,state=next(iter(receiver.audio_viewers.items()));state['bytes']=12;q.put_nowait((1,b'\x00'*12))
     return
    raise asyncio.TimeoutError()
  writer=Writer();reader=asyncio.StreamReader()
  reader.feed_data(f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:8890\r\nCookie: cdv3={receiver.token}\r\nX-CarDash-Session: current\r\n\r\n'.encode())
  await receiver.http(reader,writer)
  return writer,[json.loads(v) for v in (Path(self.tmp.name)/'diagnostic.ndjson').read_text().splitlines()]
 async def test_video_and_audio_failures_never_append_an_http_error_to_media(self):
  for path in ('/video','/audio'):
   for body_failure in (False,True):
    with self.subTest(path=path,body_failure=body_failure):
     writer,events=await self.fail_response(path,body_failure)
     data=b''.join(writer.writes)
     self.assertEqual(data.count(b'HTTP/1.1'),1,data)
     self.assertNotIn(b'400 Error',data);self.assertTrue(writer.closed)
     self.assertFalse(self.r.viewers);self.assertFalse(self.r.audio_viewers);self.assertFalse(self.r.connections)
     failure=events[-1];self.assertEqual(failure['event'],'browser_response_failed')
     self.assertEqual(failure['phase'],path[1:]+('_drain' if body_failure else '_headers'))
     self.assertEqual(failure['errorType'],'TimeoutError');self.assertTrue(failure['responseStarted'])
     self.assertNotIn(self.r.token,json.dumps(events))
 async def test_json_drain_failure_cannot_send_a_second_response(self):
  writer,events=await self.fail_response('/api/status')
  self.assertEqual(len(writer.writes),1)
  self.assertTrue(writer.writes[0].startswith(b'HTTP/1.1 200'))
  self.assertEqual(events[-1]['event'],'browser_response_failed')
 async def test_temporary_video_capacity_is_retryable_without_raising_the_limit(self):
  existing=[asyncio.Queue(),asyncio.Queue()]
  for q in existing:self.r.viewers[q]={'session':'current','closed':False}
  writer=Mock();writer.drain=AsyncMock();writer.get_extra_info.return_value=('127.0.0.1',8890)
  reader=asyncio.StreamReader()
  reader.feed_data(f'GET /video HTTP/1.1\r\nHost: 127.0.0.1:8890\r\nCookie: cdv3={self.r.token}\r\nX-CarDash-Session: current\r\n\r\n'.encode())
  await self.r.http(reader,writer)
  data=b''.join(call.args[0] for call in writer.write.call_args_list)
  self.assertTrue(data.startswith(b'HTTP/1.1 503 '),data)
  self.assertIn(b'Two viewers',data);self.assertEqual(list(self.r.viewers),existing)
  self.assertTrue(self.r.active);self.r.command.assert_not_awaited()


if __name__=='__main__':unittest.main()
