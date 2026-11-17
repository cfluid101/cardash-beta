import asyncio
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver
import crypto
from protocol import ControlCipher


class NativeEventsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.receiver=Receiver(types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/unused'))
        self.receiver.log=Mock()

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def reply(self,sequence=None,status='200',value=None,raw=None):
        body=raw if raw is not None else (plistlib.dumps(value) if value is not None else b'')
        self.receiver.event_response({'method':'RESPONSE','path':status,
                                     'headers':{} if sequence is None else {'cseq':sequence},'body':body})
        return self.receiver.log.call_args.kwargs

    async def test_known_hid_ack_and_missing_cseq_are_not_conflated(self):
        self.receiver.pending_commands['12']='hidSendReport'
        result=self.reply(value={'status':0})
        self.assertIsNone(result['sequence'])
        self.assertTrue(result['missingCSeq'])
        self.assertIsNone(result['command'])
        self.assertIn('12',self.receiver.pending_commands)
        result=self.reply(sequence='12')
        self.assertEqual(result['command'],'hidSendReport')
        self.assertFalse(result['missingCSeq'])
        self.assertEqual(result['status'],'200')
        self.assertNotIn('12',self.receiver.pending_commands)
        self.assertFalse(result['rejected'])

    async def test_http_and_nested_numeric_errors_are_recorded_without_payload_secrets(self):
        secret='private-session-material'
        result=self.reply(sequence='77',status='403',value={
            'error':{'code':-6705,'description':secret,'key':b'private-key'},
            'params':{'status':-23,'sessionKey':secret},'certificate':b'certificate',
            'user-entered-private-key':{'status':12}})
        self.assertTrue(result['rejected'])
        self.assertIsNone(result['command'])
        self.assertIn(-6705,[item.get('code') for item in result['bodyErrors']])
        self.assertIn(-23,[item.get('code') for item in result['bodyErrors']])
        output=json.dumps(result)
        for hidden in (secret,'private-key','certificate','sessionKey','user-entered'):
            self.assertNotIn(hidden,output)

    async def test_zero_status_unknown_body_and_malformed_body_are_not_raw_logged(self):
        self.assertFalse(self.reply(value={'status':0,'error':0})['rejected'])
        self.assertFalse(self.reply(value={'status':'0','error':'0'})['rejected'])
        self.assertEqual(self.reply(value={'status':'-6705'})['bodyErrors'][0]['code'],-6705)
        result=self.reply(value={'error':'credential-sensitive error detail'})
        self.assertTrue(result['rejected'])
        self.assertNotIn('credential-sensitive',json.dumps(result))
        result=self.reply(raw=b'not a plist: secret')
        self.assertTrue(result['bodyUnparsed'])
        self.assertNotIn('secret',json.dumps(result))
        large=self.reply(raw=b'private'*12000)
        self.assertTrue(large['bodyUnparsed'])
        self.assertEqual(large['bodyBytes'],84000)

    async def test_response_diagnostics_have_bounded_field_count_and_header_length(self):
        result=self.reply(sequence='x'*16000,value={'params':[{'error':i+1} for i in range(1000)]})
        self.assertLessEqual(len(result['sequence']),64)
        self.assertLessEqual(len(result['bodyErrors']),16)
        self.assertLess(len(json.dumps(result)),3000)

    async def test_touch_diagnostics_include_sent_coordinates_and_contact_state(self):
        r=self.receiver;r.active=True;r.generation='current';r.frames=1
        r.command=AsyncMock(return_value=51)
        await r.touch({'x':.052,'y':.5,'down':True,'session':'current'})
        r.log.assert_called_once_with('native_touch',sequence=51,x=.052,y=.5,down=True)

    async def test_encrypted_native_event_reply_reaches_sanitized_diagnostics(self):
        r=self.receiver;r.generation='current';shared=b'\x11'*32
        r.pair=types.SimpleNamespace(verified=True,shared=shared)
        r.pending_commands['13']='hidSendReport'
        body=plistlib.dumps({'error':-50,'privateKey':b'do-not-log'})
        reply=(f'RTSP/1.0 200 OK\r\nCSeq: 13\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body
        read_key=crypto.hkdf(shared,'Events-Salt','Events-Read-Encryption-Key')
        peer=ControlCipher(b'\0'*32,read_key)
        reader=types.SimpleNamespace(read=AsyncMock(side_effect=[peer.encode(reply),b'']))
        await r.event_client(reader,Mock())
        responses=[c.kwargs for c in r.log.call_args_list if c.args[0]=='native_event_response']
        self.assertEqual(len(responses),1)
        self.assertEqual(responses[0]['command'],'hidSendReport')
        self.assertEqual(responses[0]['bodyErrors'],[{'path':'error','code':-50}])
        self.assertTrue(responses[0]['rejected'])
        self.assertNotIn('do-not-log',json.dumps(responses))

    async def test_delayed_disconnect_cannot_stop_a_replacement_session(self):
        r=self.receiver;r.active=True;r.generation='old'
        await r.lock.acquire()
        task=asyncio.create_task(r.stop('native_event_disconnected',generation='old'))
        await asyncio.sleep(0)
        r.generation='new';writer=Mock();r.video=writer
        r.lock.release()
        self.assertFalse(await task)
        self.assertTrue(r.active)
        self.assertEqual(r.generation,'new')
        writer.close.assert_not_called()
        r.log.assert_not_called()

    async def test_delayed_browser_stop_is_rejected_after_session_replacement(self):
        r=self.receiver;r.active=True;r.generation='old'
        await r.lock.acquire()
        task=asyncio.create_task(r.action({'action':'stop','session':'old'}))
        await asyncio.sleep(0)
        r.generation='new'
        r.lock.release()
        with self.assertRaisesRegex(ValueError,'Stale native session'):
            await task
        self.assertTrue(r.active)

    async def test_matching_disconnect_still_stops_and_closes_transport(self):
        r=self.receiver;r.active=True;r.generation='current';writer=Mock();r.video=writer
        self.assertTrue(await r.stop('native_event_disconnected',generation='current'))
        self.assertFalse(r.active)
        self.assertIsNone(r.generation)
        writer.close.assert_called_once()


if __name__=='__main__':unittest.main()
