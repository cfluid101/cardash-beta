import os,sys,unittest,struct,subprocess,array,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import crypto
from audio_rtp import AACPacketDecoder
from test_aac import adts_packets

@unittest.skipUnless(sys.platform=='darwin' and os.environ.get('CDV3_AUDIO') and shutil.which('ffmpeg'),'Native AudioToolbox and FFmpeg required')
class AACRTPTest(unittest.TestCase):
 def test_authenticated_aac_stream_and_replay_and_tamper(self):
  key=bytes(range(32))
  adts=subprocess.check_output(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=997:sample_rate=48000:duration=0.1','-ac','2','-c:a','aac','-profile:a','aac_low','-f','adts','pipe:1'])
  packets=adts_packets(adts,48000);d=AACPacketDecoder(key,0x800000);frames=0
  try:
   for i,payload in enumerate(packets):
    h=struct.pack('>BBHII',0x80,102,i,i*1024,123);tail=struct.pack('<Q',i+1);wire=h+crypto.encrypt(key,b'\0'*4+tail,payload,h[4:12])+tail
    bad=bytearray(wire);bad[12]^=1
    with self.assertRaisesRegex(ValueError,'authentication'):d.decode(bytes(bad))
    value=d.decode(wire);frames+=value['sampleFrames'];self.assertEqual(value['reset'],i==0)
    with self.assertRaisesRegex(ValueError,'nonce'):d.decode(wire)
   self.assertEqual(frames,len(packets)*1024);self.assertGreater(value['nonzeroSamples'],0)
  finally:d.close()
