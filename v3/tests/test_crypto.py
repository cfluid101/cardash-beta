import importlib.util
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

class CryptoTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('crypto'), 'Missing on-phone crypto implementation')
        import crypto
        self.c = crypto

    def test_rfc8032_vector_and_forgery(self):
        seed=bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
        public=bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
        signature=bytes.fromhex('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
        self.assertEqual(self.c.public(seed),public)
        self.assertEqual(self.c.sign(seed,b''),signature)
        self.assertTrue(self.c.verify(public,b'',signature))
        self.assertFalse(self.c.verify(public,b'x',signature))

    def test_x25519_and_authenticated_encryption(self):
        a,b=bytes(range(32)),bytes(range(32,64))
        key=self.c.exchange(a,self.c.public(b,True))
        self.assertEqual(key,self.c.exchange(b,self.c.public(a,True)))
        nonce=b'\0'*12;message=b'native frame'*100
        encrypted=self.c.encrypt(key,nonce,message,b'header')
        self.assertEqual(self.c.decrypt(key,nonce,encrypted,b'header'),message)
        with self.assertRaises(ValueError):self.c.decrypt(key,nonce,encrypted,b'wrong header')
        with self.assertRaises(ValueError):self.c.decrypt(key,nonce,encrypted[:-1]+bytes([encrypted[-1]^1]),b'header')

if __name__=='__main__':unittest.main()
