import asyncio,struct,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import crypto
from audio_transport import AudioChannel

class Transport:
 def __init__(self):self.sent=[];self.closed=False
 def sendto(self,data,address):self.sent.append((data,address))
 def close(self):self.closed=True

class AudioTransportTest(unittest.IsolatedAsyncioTestCase):
 async def test_muted_uplink_is_authenticated_silence_and_stops_with_generation(self):
  owner=SimpleNamespace(generation='one',active=True,pair=SimpleNamespace(shared=b'x'*32),log=lambda *a,**k:None)
  offer={'type':100,'audioType':'telephony','streamConnectionID':42,'audioFormat':0x10,'framesPerPacket':320,'dataPort':23000}
  c=AudioChannel(owner,offer,0);c.data_transport=Transport()
  try:
   c.send_muted_input();wire,address=c.data_transport.sent[0]
   self.assertEqual(address,('::1',23000));self.assertEqual(len(wire),676)
   self.assertEqual(struct.unpack('>BBHII',wire[:12]),(0x80,100,0,0,0))
   key=crypto.hkdf(owner.pair.shared,'DataStream-Salt42','DataStream-Input-Encryption-Key')
   self.assertEqual(crypto.decrypt(key,b'\0'*4+wire[-8:],wire[12:-8],wire[4:12]),bytes(640))
   self.assertTrue(c.status()['mutedInput']);self.assertEqual(c.status()['mutedInputPackets'],1)
   owner.generation='two';await asyncio.sleep(.035);self.assertEqual(len(c.data_transport.sent),1)
  finally:c.close()
  self.assertIsNone(c.input_timer);self.assertTrue(c.data_transport.closed)
 async def test_media_has_no_input_and_unadvertised_input_rate_rejects(self):
  owner=SimpleNamespace(generation='one',active=True,pair=SimpleNamespace(shared=b'x'*32))
  c=AudioChannel(owner,{'type':100,'audioType':'media','streamConnectionID':1,'audioFormat':0x8000,'dataPort':23000},0)
  self.assertFalse(c.status()['mutedInput']);c.close()
  with self.assertRaisesRegex(ValueError,'muted input format'):
   AudioChannel(owner,{'type':100,'audioType':'telephony','streamConnectionID':1,'audioFormat':0x8000,'dataPort':23000},0)
