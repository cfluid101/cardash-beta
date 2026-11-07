# SPDX-License-Identifier: GPL-3.0-only
# Port of the device-verified receiver; provenance in ../NOTICE.md.
import hashlib
import hmac
import os
import re
import struct
import crypto as c


def need(condition,message):
    if not condition:raise ValueError(message)
def digest(*values):return hashlib.sha512(b''.join(values)).digest()
def integer(data):return int.from_bytes(data,'big')
def number(n,size=0):return n.to_bytes(max(size,(n.bit_length()+7)//8),'big')
def nonce(counter):return b'\0'*4+struct.pack('<Q',counter)
def label(value):return b'\0'*4+value.encode()
def tlv(values):
    out=bytearray()
    for tag,value in values.items():
        need(len(value)<=65535,'TLV size')
        for i in range(0,max(1,len(value)),255):
            part=value[i:i+255];out+=bytes([tag,len(part)])+part
    return bytes(out)
def untlv(data):
    need(len(data)<=65536,'TLV size');out={};i=0
    while i<len(data):
        need(i+2<=len(data),'TLV header');tag,n=data[i:i+2];i+=2
        need(i+n<=len(data),'TLV truncated');out[tag]=out.get(tag,b'')+data[i:i+n];i+=n
    return out

N=int('ffffffffffffffffc90fdaa22168c234c4c6628b80dc1cd129024e088a67cc74020bbea63b139b22514a08798e3404ddef9519b3cd3a431b302b0a6df25f14374fe1356d6d51c245e485b576625e7ec6f44c42e9a637ed6b0bff5cb6f406b7edee386bfb5a899fa5ae9f24117c4b1fe649286651ece45b3dc2007cb8a163bf0598da48361c55d39a69163fa8fd24cf5f83655d23dca3ad961c62f356208552bb9ed529077096966d670c354e4abc9804f1746c08ca18217c32905e462e36ce3be39e772c180e86039b2783a2ec07a28fb5c55df06f4c52c9de2bcbf6955817183995497cea956ae515d2261898fa051015728e5a8aaac42dad33170d04507a33a85521abdf1cba64ecfb850458dbef0a8aea71575d060c7db3970f85a6e1e4c7abf5ae8cdb0933d71e8c94e04a25619dcee3d2261ad2ee6bf12ffa06d98a0864d87602733ec86a64521f2b18177b200cbbe117577a615d6c770988c0bad946e208e24fa074e5ab3143db5bfce0fd108e4b82d120a93ad2caffffffffffffffff',16)
G=5
K=integer(digest(number(N),number(G,384)))

class Pairing:
    def __init__(self,identity,save):
        self.identity=identity;self.save=save;self.setup_state=0;self.verify_state=0;self.verified=False
        self.seed=bytes.fromhex(identity['seed']);self.public=c.public(self.seed);self.error=None
    def fail(self,state,error):
        self.error=str(error);return tlv({6:bytes([min(255,state+1 if state%2 else state)]),7:b'\x02'})
    def setup(self,body):
        state=0
        try:
            t=untlv(body);need(len(t.get(6,b''))==1,'state length');state=t[6][0]
            if state==1:
                need(self.setup_state==0,'setup order');self.salt=os.urandom(16)
                x=integer(digest(self.salt,digest(b'Pair-Setup:3939')));self.v=pow(G,x,N)
                self.b=integer(os.urandom(32));self.B=(K*self.v+pow(G,self.b,N))%N;self.setup_state=2
                return tlv({6:b'\x02',3:number(self.B,384),2:self.salt})
            if state==3:
                need(self.setup_state==2,'setup order');a=t.get(3,b'');proof=t.get(4,b'')
                need(len(a)==384 and len(proof)==64,'SRP input');A=integer(a);need(A%N!=0,'SRP zero')
                u=integer(digest(a,number(self.B,384)));need(u!=0,'SRP u')
                secret=pow(A*pow(self.v,u,N)%N,self.b,N);self.session_key=digest(number(secret))
                xor=bytes(x^y for x,y in zip(digest(number(N)),digest(number(G))))
                expected=digest(xor,digest(b'Pair-Setup'),self.salt,a,number(self.B,384),self.session_key)
                need(hmac.compare_digest(proof,expected),'SRP proof');self.setup_state=4
                return tlv({6:b'\x04',4:digest(a,proof,self.session_key)})
            if state==5:
                need(self.setup_state==4,'setup order')
                key=c.hkdf(self.session_key,'Pair-Setup-Encrypt-Salt','Pair-Setup-Encrypt-Info')
                sub=untlv(c.decrypt(key,label('PS-Msg05'),t[5]));ident=sub[1];public=sub[3];signature=sub[10]
                need(0<len(ident)<=256,'controller identity')
                ck=c.hkdf(self.session_key,'Pair-Setup-Controller-Sign-Salt','Pair-Setup-Controller-Sign-Info')
                need(c.verify(public,ck+ident+public,signature),'controller signature')
                own=self.identity['id'].encode();ak=c.hkdf(self.session_key,'Pair-Setup-Accessory-Sign-Salt','Pair-Setup-Accessory-Sign-Info')
                signature=c.sign(self.seed,ak+own+self.public)
                self.identity['peers'][ident.decode()]=public.hex();self.save();self.setup_state=6
                return tlv({6:b'\x06',5:c.encrypt(key,label('PS-Msg06'),tlv({1:own,3:self.public,10:signature}))})
            raise ValueError('setup state')
        except (ValueError,KeyError,UnicodeError) as error:
            self.setup_state=-1;return self.fail(state,error)
    def verify(self,body):
        state=0
        try:
            t=untlv(body);need(len(t.get(6,b''))==1,'state length');state=t[6][0]
            if state==1:
                need(self.verify_state==0,'verify order');self.client=t[3];seed=os.urandom(32)
                self.ep=c.public(seed,True);self.shared=c.exchange(seed,self.client)
                self.key=c.hkdf(self.shared,'Pair-Verify-Encrypt-Salt','Pair-Verify-Encrypt-Info')
                own=self.identity['id'].encode();signature=c.sign(self.seed,self.ep+own+self.client);self.verify_state=2
                return tlv({6:b'\x02',3:self.ep,5:c.encrypt(self.key,label('PV-Msg02'),tlv({1:own,10:signature}))})
            if state==3:
                need(self.verify_state==2,'verify order')
                sub=untlv(c.decrypt(self.key,label('PV-Msg03'),t[5]));ident=sub[1]
                need(0<len(ident)<=256,'verify identity')
                public=bytes.fromhex(self.identity['peers'][ident.decode()])
                need(c.verify(public,self.client+ident+self.ep,sub[10]),'verify signature')
                self.read_key=c.hkdf(self.shared,'Control-Salt','Control-Write-Encryption-Key')
                self.write_key=c.hkdf(self.shared,'Control-Salt','Control-Read-Encryption-Key')
                self.verified=True;self.verify_state=4;return tlv({6:b'\x04'})
            raise ValueError('verify state')
        except (ValueError,KeyError,UnicodeError) as error:
            self.verify_state=-1;return self.fail(state,error)

class RtspParser:
    def __init__(self):self.buffer=bytearray()
    def push(self,data):
        need(len(self.buffer)+len(data)<=1064964,'receive limit');self.buffer+=data;messages=[]
        while self.buffer:
            end=self.buffer.find(b'\r\n\r\n')
            if end<0:need(len(self.buffer)<=16384,'header limit');break
            need(end<=16384,'header limit');raw=bytes(self.buffer[:end]);need(all(x in (9,10,13) or 32<=x<127 for x in raw),'header bytes')
            lines=raw.decode('ascii').split('\r\n');first=lines.pop(0)
            match=re.fullmatch(r'(RTSP/1\.0|HTTP/1\.[01]) ([0-9]{3}) [ -~]*',first)
            if match:method,path,proto='RESPONSE',match[2],match[1]
            else:
                match=re.fullmatch(r'([A-Z_]+) (\S{1,2048}) (RTSP/1\.0|HTTP/1\.[01])',first)
                need(match,'request line');method,path,proto=match.groups()
            headers={}
            for line in lines:
                m=re.fullmatch(r'([A-Za-z0-9-]+):[ \t]*([^\r\n]*)',line);need(m,'header')
                k=m[1].lower();need(k not in headers,'duplicate header');headers[k]=m[2].strip()
            need('transfer-encoding' not in headers,'transfer encoding')
            length=headers.get('content-length','0');need(re.fullmatch(r'0|[1-9][0-9]{0,7}',length),'length');n=int(length);need(n<=1048576,'body limit')
            if len(self.buffer)<end+4+n:break
            messages.append(dict(method=method,path=path,protocol=proto,headers=headers,body=bytes(self.buffer[end+4:end+4+n])))
            del self.buffer[:end+4+n];need(len(messages)<=128,'pipeline limit')
        return messages

class ControlCipher:
    def __init__(self,read_key,write_key):
        self.read_key=read_key;self.write_key=write_key;self.rc=0;self.wc=0;self.buffer=bytearray()
    def encode(self,data):
        need(len(data)<=1048576,'control output limit');out=[]
        for i in range(0,max(len(data),1),16384):
            part=data[i:i+16384];header=struct.pack('<H',len(part));out+=[header,c.encrypt(self.write_key,nonce(self.wc),part,header)];self.wc+=1
        return b''.join(out)
    def decode(self,data):
        need(len(self.buffer)+len(data)<=131072,'cipher buffer limit');self.buffer+=data;out=[]
        while len(self.buffer)>=2:
            n=struct.unpack_from('<H',self.buffer)[0];need(n<=16384,'cipher frame limit')
            if len(self.buffer)<n+18:break
            out.append(c.decrypt(self.read_key,nonce(self.rc),bytes(self.buffer[2:n+18]),bytes(self.buffer[:2])))
            self.rc+=1;del self.buffer[:n+18]
        return b''.join(out)

class ScreenReceiver:
    def __init__(self,key,on_config,on_frame):
        self.key=key;self.on_config=on_config;self.on_frame=on_frame;self.counter=0;self.buffer=bytearray();self.configured=False
    def push(self,data,max_packets=None):
        need(len(self.buffer)+len(data)<=8388736,'screen buffer limit');self.buffer+=data
        processed=0
        while len(self.buffer)>=128 and (max_packets is None or processed<max_packets):
            header=bytes(self.buffer[:128]);n=struct.unpack_from('<I',header)[0];op=header[4]
            need(n<=8388608 and op in (0,1,2),'screen header')
            if len(self.buffer)<128+n:return False
            body=bytes(self.buffer[128:128+n])
            if op==1:
                need(n<=65536,'codec config limit');at=body.find(b'avcC');config=body[at+4:] if at>=4 else body
                need(len(config)>=9 and config[0]==1,'codec config');self.on_config(config);self.configured=True
            elif op==0 and n:
                need(self.configured,'frame before config');plain=c.decrypt(self.key,nonce(self.counter),body,header);self.counter+=1
                raw=struct.unpack_from('<Q',header,8)[0];us=(raw>>32)*1000000+((raw&0xffffffff)*1000000>>32)
                self.on_frame(plain,us)
            del self.buffer[:128+n]
            processed+=1
        return len(self.buffer)>=128

def mfi_sap(body,der,certificate):
    need(len(body)==33 and body[0]==1,'MFiSAP input');seed=os.urandom(32);public=c.public(seed,True)
    shared=c.exchange(seed,body[1:]);signature=c.accessory_sign(der,public+body[1:])
    key=hashlib.sha1(b'AES-KEY'+shared).digest()[:16];iv=hashlib.sha1(b'AES-IV'+shared).digest()[:16]
    encrypted=c.ctr(key,iv,signature)
    return public+struct.pack('>I',len(certificate))+certificate+struct.pack('>I',len(encrypted))+encrypted
