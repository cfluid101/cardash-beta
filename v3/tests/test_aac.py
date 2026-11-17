import array
import ctypes as C
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'v3/backend'))
from aac import AACDecoder, AACError, MAX_OUTPUT_FRAMES


def adts_packets(data, rate):
    result=[];at=0
    while at<len(data):
        if data[at:at+2] not in (b'\xff\xf1',b'\xff\xf9'):
            raise ValueError('Fixture does not contain plain AAC ADTS')
        header=data[at:at+7]
        if ((header[2]>>6)+1)!=2 or (header[6]&3):
            raise ValueError('Fixture is not single-block AAC-LC')
        if ((header[2]>>2)&15)!=(4 if rate==44100 else 3):
            raise ValueError('Fixture sample rate differs')
        size=((header[3]&3)<<11)|(header[4]<<3)|(header[5]>>5)
        if size<=7 or at+size>len(data):raise ValueError('Truncated ADTS fixture')
        result.append(data[at+7:at+size]);at+=size
    return result


class LazyAACTest(unittest.TestCase):
    def test_import_has_no_native_library_dependency(self):
        env={**os.environ,'CDV3_AUDIO':'/does/not/exist/libcardashaudio.dylib'}
        subprocess.run([sys.executable,'-c',
            'import sys;sys.path.insert(0,"v3/backend");import aac;assert aac.AAC_FORMATS[0x800000]==(48000,2)'],
            cwd=ROOT,env=env,check=True,capture_output=True)

    def test_unadvertised_rates_channels_reject_before_library_load(self):
        for rate,channels in [(8000,2),(44100,0),(48000,8),(True,2)]:
            with self.assertRaises(ValueError):AACDecoder(rate,channels)


@unittest.skipUnless(sys.platform=='darwin' and os.environ.get('CDV3_AUDIO') and shutil.which('ffmpeg'),
                     'Set CDV3_AUDIO to a built host AudioToolbox bridge; FFmpeg required')
class NativeAACTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures={}
        for rate in (44100,48000):
            adts=subprocess.check_output(['ffmpeg','-v','error','-f','lavfi','-i',
                f'sine=frequency=997:sample_rate={rate}:duration=0.25','-ac','2',
                '-c:a','aac','-profile:a','aac_low','-b:a','128k','-f','adts','pipe:1'])
            reference=subprocess.check_output(['ffmpeg','-v','error','-f','aac','-c:a','aac',
                '-i','pipe:0','-f','s16le','-acodec','pcm_s16le','pipe:1'],input=adts)
            cls.fixtures[rate]=(adts_packets(adts,rate),reference)

    def test_two_rates_decode_independent_aac_to_expected_nonzero_pcm(self):
        for rate,(packets,reference) in self.fixtures.items():
            with self.subTest(rate=rate),AACDecoder(rate,2) as decoder:
                pieces=[decoder.decode(packet) for packet in packets]
                pieces.append(decoder.flush());pcm=b''.join(pieces)
                self.assertTrue(all(len(p)<=MAX_OUTPUT_FRAMES*4 for p in pieces))
                self.assertEqual(len(pcm),len(reference))
                self.assertEqual(len(pcm)//4,len(packets)*1024)
                samples=array.array('h',pcm);expected=array.array('h',reference)
                if sys.byteorder!='little':samples.byteswap();expected.byteswap()
                rms=math.sqrt(sum(v*v for v in samples)/len(samples))
                ref_rms=math.sqrt(sum(v*v for v in expected)/len(expected))
                self.assertGreater(rms,100)
                self.assertLess(abs(rms-ref_rms)/ref_rms,.05)
                self.assertTrue(any(v<0 for v in samples) and any(v>0 for v in samples))
                self.assertEqual(decoder.flush(),b'')

    def test_bad_input_bounds_closed_handle_and_reset(self):
        packets,_=self.fixtures[44100]
        decoder=AACDecoder(44100)
        for bad in (b'',b'0'*8193,bytearray(b'123'),None):
            with self.assertRaises(ValueError):decoder.decode(bad)
        # AudioToolbox consumes a truncated AAC unit without producing PCM on
        # this OS rather than returning an error. Do not invent strict syntax
        # validation that the system decoder does not provide.
        self.assertEqual(decoder.decode(b'\x00'),b'')
        decoder.reset()
        pcm=decoder.decode(packets[0]);self.assertEqual(len(pcm),4096)
        decoder.flush()
        with self.assertRaises(AACError):decoder.decode(packets[1])
        decoder.reset();self.assertEqual(len(decoder.decode(packets[0])),4096)
        decoder.close();decoder.close()
        with self.assertRaisesRegex(ValueError,'closed'):decoder.decode(packets[0])

    def test_native_output_capacity_guards_do_not_write_memory(self):
        packets,_=self.fixtures[48000]
        with AACDecoder(48000) as decoder:
            output=C.create_string_buffer(b'canary',32);frames=C.c_uint32(123)
            for capacity in (0,8193):
                status=decoder._lib.cd_aac_decode(decoder._handle,packets[0],len(packets[0]),
                                                   output,capacity,C.byref(frames))
                self.assertNotEqual(status,0);self.assertEqual(frames.value,0)
                self.assertEqual(output.raw[:6],b'canary')
            self.assertEqual(len(decoder.decode(packets[0])),4096)


if __name__=='__main__':unittest.main()
