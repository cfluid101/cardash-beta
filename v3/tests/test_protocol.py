import importlib.util
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))

class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('protocol'),'Missing native protocol port')
        import protocol
        self.p=protocol
    def test_fragmented_rtsp_and_duplicate_lengths(self):
        raw=b'GET /info RTSP/1.0\r\nCSeq: 1\r\nContent-Length: 4\r\n\r\ndata'
        parser=self.p.RtspParser();result=[]
        for b in raw:result+=parser.push(bytes([b]))
        self.assertEqual(result[0]['body'],b'data')
        with self.assertRaises(ValueError):self.p.RtspParser().push(b'GET /info RTSP/1.0\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n')
    def test_cipher_fragmentation_forgery_and_replay(self):
        key=bytes(range(32));writer=self.p.ControlCipher(key,key);reader=self.p.ControlCipher(key,key)
        wire=writer.encode(b'x'*20000);plain=b''
        for i in range(0,len(wire),7):plain+=reader.decode(wire[i:i+7])
        self.assertEqual(plain,b'x'*20000)
        with self.assertRaises(ValueError):reader.decode(wire)
        broken=wire[:-1]+bytes([wire[-1]^1])
        with self.assertRaises(ValueError):self.p.ControlCipher(key,key).decode(broken)
    def test_tlv_boundaries_and_invalid_pair_order(self):
        items={3:bytes(range(256))*2,6:b'\x01'}
        self.assertEqual(self.p.untlv(self.p.tlv(items)),items)
        with self.assertRaises(ValueError):self.p.untlv(b'\x03\x04a')
        pair=self.p.Pairing({'id':'test','seed':'01'*32,'peers':{}},lambda:None)
        self.assertIn(7,self.p.untlv(pair.setup(self.p.tlv({6:b'\x05'}))))
        self.assertFalse(pair.verified)

if __name__=='__main__':unittest.main()
