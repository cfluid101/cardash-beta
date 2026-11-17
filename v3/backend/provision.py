# SPDX-License-Identifier: GPL-3.0-only
# Explicit user-triggered experimental identity provisioning. Never bundled keys.
from pathlib import Path
import hashlib
import io
import os
import urllib.request
import zipfile
import crypto
import time

URL='https://github.com/shihabal3amri/DiPlay/releases/download/v0.2.22/DiPlay-0.2.22.apk'
APK_SHA256='7d04db263834f22010a86847766928113d3503a273e4d2d3440d21552e173139'
CERT_SHA256='634a93dd6c4338080524025411752597ecb828591839cd062a8292fd7e9e844e'
LIMIT=32*1024*1024

def provision(state,apk=None):
    if apk is None:
        request=urllib.request.Request(URL,headers={'User-Agent':'CarDash-V3-Native-Preview/3.0.0-beta.2'})
        with urllib.request.urlopen(request,timeout=25) as response:
            apk=response.read(LIMIT+1)
    if len(apk)>LIMIT or hashlib.sha256(apk).hexdigest()!=APK_SHA256:
        raise ValueError('Upstream download checksum mismatch; identity was not installed')
    with zipfile.ZipFile(io.BytesIO(apk)) as archive:
        names={'certificate.p7b':'assets/offline-mfi/certificate.p7b','identity.pk8':'assets/offline-mfi/identity.pk8'}
        values={}
        for name,entry in names.items():
            if archive.getinfo(entry).file_size>16384:raise ValueError('Oversized identity file')
            values[name]=archive.read(entry)
    if hashlib.sha256(values['certificate.p7b']).hexdigest()!=CERT_SHA256 or not crypto.certificate_matches(values['identity.pk8'],values['certificate.p7b']):
        raise ValueError('Accessory certificate and key do not match')
    folder=Path(state)/'accessory';folder.mkdir(exist_ok=True,mode=0o700)
    for name,data in values.items():
        p=folder/(name+'.tmp');fd=os.open(p,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(p,folder/name)

if __name__=='__main__':
    import sys
    from memory_budget import configure
    configure()
    if len(sys.argv)>3 and sys.argv[2]=='--fd':
        with os.fdopen(int(sys.argv[3]),'rb') as f:apk=f.read(LIMIT+1)
    else:apk=Path(sys.argv[2]).read_bytes() if len(sys.argv)>2 else None
    provision(sys.argv[1],apk)
