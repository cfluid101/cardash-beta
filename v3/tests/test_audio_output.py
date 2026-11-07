import asyncio
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock,Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from server import Receiver, ROOT

class AudioOutputTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.args=types.SimpleNamespace(state=self.tmp.name,port=0,capture=None,helper='/unused')
        self.r=Receiver(self.args)

    async def asyncTearDown(self):self.tmp.cleanup()

    async def test_default_preserves_complete_native_declarations_and_disables_browser_audio(self):
        base=plistlib.loads((ROOT/'receiver-info.plist').read_bytes())
        info=self.r.receiver_info()
        self.assertEqual(self.r.status()['audioOutput'],'phone')
        self.assertEqual(info['features'],base['features'])
        self.assertEqual(info['audioFormats'],base['audioFormats'])
        for key in ('displays','hidDevices'):self.assertEqual(info[key],base[key])
        audio=next(r for r in info['modes']['resources'] if r['resourceID']==2)
        self.assertEqual(info,base)
        with self.assertRaisesRegex(ValueError,'Browser audio is disabled'):
            await self.r.audio_viewer(None,None)

    async def test_browser_is_explicit_persistent_and_restores_complete_audio_formats(self):
        identity=Path(self.tmp.name,'identity.json').read_bytes()
        await self.r.action({'action':'audio_output','mode':'browser'})
        replacement=Receiver(self.args)
        self.assertEqual(replacement.status()['audioOutput'],'browser')
        self.assertEqual(replacement.receiver_info(),plistlib.loads((ROOT/'receiver-info.plist').read_bytes()))
        self.assertEqual(Path(self.tmp.name,'identity.json').read_bytes(),identity)
        await replacement.action({'action':'audio_output','mode':'phone'})
        self.assertEqual(Receiver(self.args).status()['audioOutput'],'phone')

    async def test_active_or_queued_change_cannot_modify_live_session_capabilities(self):
        self.r.active=True
        with self.assertRaisesRegex(ValueError,'Stop'):await self.r.action({'action':'audio_output','mode':'browser'})
        self.assertEqual(self.r.audio_output,'phone')
        self.r.active=False;await self.r.lock.acquire()
        task=asyncio.create_task(self.r.action({'action':'audio_output','mode':'browser'}))
        await asyncio.sleep(0);self.r.active=True;self.r.lock.release()
        with self.assertRaisesRegex(ValueError,'Stop'):await task
        self.assertEqual(self.r.audio_output,'phone')

    async def test_invalid_or_damaged_setting_falls_back_without_overwriting_identity(self):
        for value in ('',None,True,{},'unknown'):
            with self.assertRaises(ValueError):await self.r.action({'action':'audio_output','mode':value})
        Path(self.tmp.name,'settings.json').write_text('{broken')
        self.assertEqual(Receiver(self.args).audio_output,'phone')

    async def test_stop_clears_audio_lease_only_for_current_generation(self):
        self.r.audio_lease=Mock();self.r.active=True;self.r.generation='new'
        self.assertFalse(await self.r.stop(generation='old'))
        self.r.audio_lease.clear.assert_not_called()
        self.assertTrue(await self.r.stop(generation='new'))
        self.r.audio_lease.clear.assert_called_once_with()

    async def test_phone_start_fails_before_launch_when_adapter_is_missing(self):
        self.r.ready=lambda:True
        with patch('server.transport_status',return_value={'ready':True}), patch('server.audio_route_status',return_value={'ready':False,'error':'Audio adapter unavailable'}), patch('server.asyncio.create_subprocess_exec',new_callable=AsyncMock) as launch:
            with self.assertRaisesRegex(ValueError,'Audio adapter'):await self.r.start()
            launch.assert_not_called()
        self.assertFalse(self.r.active)

    async def test_failed_native_launch_cleans_capture_even_if_lease_clear_fails(self):
        self.r.ready=lambda:True;self.r.args.capture=self.tmp.name
        self.r.audio_lease=Mock();self.r.audio_lease.clear.side_effect=OSError('notify clear failed')
        with patch('server.transport_status',return_value={'ready':True}), patch('server.audio_route_status',return_value={'ready':True}), patch('server.Path.read_bytes',return_value=b'cert'), patch('server.CERT_SHA256',__import__('hashlib').sha256(b'cert').hexdigest()), patch('server.crypto.certificate_matches',return_value=True), patch('server.asyncio.create_subprocess_exec',side_effect=OSError('launch failed')):
            with self.assertRaisesRegex(OSError,'launch failed'):await self.r.start()
        self.assertIsNone(self.r.capture);self.assertIsNone(self.r.generation);self.assertFalse(self.r.active)

    async def test_phone_mode_releases_resources_with_route_managed_by_native_adapter(self):
        self.r.active=True;self.r.generation='test';self.r.command=AsyncMock()
        await self.r.modes('test')
        resources=self.r.command.call_args_list[0].args[0]['params']['resources']
        self.assertEqual(resources[0],{'resourceID':1,'transferType':2})
        self.assertEqual(resources[1]['resourceID'],2)
        self.assertEqual(resources[1]['transferType'],2)

if __name__=='__main__':unittest.main()
