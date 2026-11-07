# SPDX-License-Identifier: GPL-3.0-only
import ctypes as C
import hashlib
import hmac
import os
from pathlib import Path

path=Path(os.environ.get('CDV3_CRYPTO',str(Path(__file__).with_name('libcardashcrypto.dylib'))))
lib=C.CDLL(str(path))
P=C.c_void_p;I=C.c_int
for name,args in {'cp_public':[I,P,P],'cp_shared':[P,P,P],'cp_sign':[P,P,I,P],
                  'cp_verify':[P,P,I,P],'cp_crypt':[I,I,P,P,P,I,P,I,P],
                  'cp_accessory':[P,I,P,I,P],'cp_certmatch':[P,I,P,I]}.items():
    f=getattr(lib,name);f.argtypes=args;f.restype=I

def exact(value,n):
    if not isinstance(value,bytes) or len(value)!=n:raise ValueError('key/nonce size')
    return value

def output(name,n,*args):
    out=C.create_string_buffer(n)
    if getattr(lib,name)(*args,out)!=1:raise ValueError(name+' failed')
    return out.raw

def public(seed,exchange=False):return output('cp_public',32,int(exchange),exact(seed,32))
def exchange(seed,peer):return output('cp_shared',32,exact(seed,32),exact(peer,32))
def sign(seed,message):return output('cp_sign',64,exact(seed,32),message,len(message))
def verify(public,message,signature):
    return lib.cp_verify(exact(public,32),message,len(message),exact(signature,64))==1
def crypt(enc,key,nonce,data,aad=b'',aead=True):
    exact(key,32 if aead else 16);exact(nonce,12 if aead else 16)
    if len(data)>8388608 or len(aad)>65536:raise ValueError('crypto input limit')
    out=C.create_string_buffer(len(data)+32)
    n=lib.cp_crypt(enc,int(aead),key,nonce,aad,len(aad),data,len(data),out)
    if n<0:raise ValueError('authentication failed')
    return out.raw[:n]
def encrypt(key,nonce,data,aad=b''):return crypt(1,key,nonce,data,aad)
def decrypt(key,nonce,data,aad=b''):return crypt(0,key,nonce,data,aad)
def ctr(key,iv,data):return crypt(1,key,iv,data,aead=False)
def accessory_sign(der,message):return output('cp_accessory',64,der,len(der),message,len(message))
def certificate_matches(der,pem):return lib.cp_certmatch(der,len(der),pem,len(pem))==1
def hkdf(secret,salt,info):
    prk=hmac.new(salt.encode(),secret,hashlib.sha512).digest()
    return hmac.new(prk,info.encode()+b'\x01',hashlib.sha512).digest()[:32]
