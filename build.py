#!/usr/bin/env python3
"""Local build only. Never connects to, installs on, or restarts a phone."""
from pathlib import Path
import argparse,hashlib,json,os,plistlib,subprocess,sys,io,tarfile,shutil,zlib,struct
ROOT=Path(__file__).resolve().parent
def run(args):
    p=subprocess.run([str(x) for x in args],cwd=ROOT,text=True,capture_output=True)
    if p.returncode:raise RuntimeError('Command failed: '+' '.join(map(str,args))+'\n'+p.stdout+p.stderr)
    if p.stdout.strip():print(p.stdout.strip())
    return p.stdout.strip()
def prepare():
    shared=ROOT/'build/shared';shared.mkdir(parents=True,exist_ok=True)
    key=shared/'PublicKey.h'
    if not key.exists():
        p=subprocess.run(['node','-e',"const c=require('node:crypto');const {publicKey}=c.generateKeyPairSync('ed25519');process.stdout.write(publicKey.export({type:'spki',format:'der'}).subarray(-32).toString('hex'));"],capture_output=True,text=True,check=True)
        raw=bytes.fromhex(p.stdout);assert len(raw)==32
        key.write_text('// Generated public test key only. Private key was discarded, not packaged.\nstatic const unsigned char CDPublicKey[32]={'+','.join(str(x) for x in raw)+'};\n')
    return shared
def flags(shared):return ['-x','objective-c++','-std=c++17','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations','-I',ROOT/'src','-I',shared]
def host():
    shared=prepare();out=ROOT/'build/host';out.mkdir(exist_ok=True)
    run(['xcrun','clang++',*flags(shared),'-DCD_HOST_TEST=1','src/Common.m','src/Runner.mm','src/Worker.mm','src/main.mm','-framework','Foundation','-o',out/'cardash-diagnostics'])
    run(['xcrun','clang++',*flags(shared),'tests/GatesTests.m','src/Common.m','-framework','Foundation','-o',out/'gate-tests'])
    run([out/'gate-tests'])
    return out
def icon(path,size):
    # Original geometric diagnostic icon, not an Apple/CarPlay asset.
    raw=bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            X=x/size;Y=y/size
            frame=(.19<X<.81 and (.24<Y<.29 or .71<Y<.76)) or (.24<Y<.76 and (.19<X<.24 or .76<X<.81))
            pulse=.31<X<.69 and abs(Y-(.50+(.16 if .43<X<.48 else -.16 if .48<=X<.53 else 0)))<.025
            raw.extend((232,244,255,255) if frame else (64,218,191,255) if pulse else (24,40,67,255))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(raw),9))+chunk(b'IEND',b''))
def plist(path,data):path.write_bytes(plistlib.dumps(data,sort_keys=True))
def app(shared,out,sdk,sim=False):
    bundle=out/'CarDashDiagnostics.app';bundle.mkdir(exist_ok=True)
    base=['xcrun','--sdk',sdk,'clang++',*flags(shared)]
    if sim:base+=['-target','x86_64-apple-ios16.6-simulator','-DCD_SIM_TEST=1']
    else:base+=['-arch','arm64','-miphoneos-version-min=16.6']
    sdkpath=run(['xcrun','--sdk',sdk,'--show-sdk-path'])
    run([*base,'-isysroot',sdkpath,'app/main.mm','src/Common.m','-framework','Foundation','-framework','UIKit','-o',bundle/'CarDashDiagnostics'])
    plist(bundle/'Info.plist',{'CFBundleIdentifier':'com.cfluid.cardash.diagnostics.app','CFBundleExecutable':'CarDashDiagnostics','CFBundleName':'CarPlay Diagnostics','CFBundleDisplayName':'CarPlay Diagnostics','CFBundlePackageType':'APPL','CFBundleInfoDictionaryVersion':'6.0','CFBundleVersion':'2','CFBundleShortVersionString':'0.1.1','MinimumOSVersion':'16.6','CFBundleSupportedPlatforms':['iPhoneSimulator' if sim else 'iPhoneOS'],'LSRequiresIPhoneOS':True,'UIDeviceFamily':[1],'UILaunchScreen':{},'UIUserInterfaceStyle':'Dark','UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait'],'CFBundleIconFiles':['AppIcon'],'CFBundleIcons':{'CFBundlePrimaryIcon':{'CFBundleIconFiles':['AppIcon']}}})
    icon(bundle/'AppIcon@2x.png',120);icon(bundle/'AppIcon@3x.png',180)
    # The device client needs IPC outside an application container. The simulator
    # intentionally keeps its own container for the synthetic Run/Share tests.
    ent=out/'app-entitlements.plist';plist(ent,{'application-identifier':'com.cfluid.cardash.diagnostics.app','platform-application':True,'com.apple.private.security.no-sandbox':True,'com.apple.private.security.container-required':bool(sim)})
    run(['/usr/bin/codesign','--force','--sign','-','--entitlements',ent,bundle]);run(['/usr/bin/codesign','--verify','--strict',bundle]);return bundle
def native():
    shared=prepare();out=ROOT/'build/device';out.mkdir(exist_ok=True)
    sdk=run(['xcrun','--sdk','iphoneos','--show-sdk-path'])
    binary=out/'cardash-diagnostics'
    run(['xcrun','--sdk','iphoneos','clang++',*flags(shared),'-arch','arm64','-isysroot',sdk,'-miphoneos-version-min=16.6','src/Common.m','src/Runner.mm','src/Worker.mm','src/main.mm','-framework','Foundation','-o',binary])
    ent=out/'helper-entitlements.plist';plist(ent,{'platform-application':True,'com.apple.private.security.no-sandbox':True})
    run(['/usr/bin/codesign','--force','--sign','-','--entitlements',ent,binary]);run(['/usr/bin/codesign','--verify','--strict',binary]);bundle=app(shared,out,'iphoneos')
    stage=ROOT/'build/stage'
    if stage.exists():shutil.rmtree(stage)
    for path in ['DEBIAN','var/jb/Applications','var/jb/usr/libexec','var/jb/Library/LaunchDaemons','var/jb/usr/share/cardash-diagnostics']:(stage/path).mkdir(parents=True,exist_ok=True)
    shutil.copytree(bundle,stage/'var/jb/Applications/CarDashDiagnostics.app');shutil.copy2(binary,stage/'var/jb/usr/libexec/cardash-diagnostics')
    for name in ['control','postinst','prerm','postrm']:shutil.copy2(ROOT/'packaging'/name,stage/'DEBIAN'/name)
    job={'Label':'com.cfluid.cardash.diagnostics','ProgramArguments':['/var/jb/usr/libexec/cardash-diagnostics','--daemon'],'UserName':'root','RunAtLoad':False,'KeepAlive':False,'ProcessType':'Adaptive','ExitTimeOut':8,'ThrottleInterval':10,'Umask':0o027,'StandardOutPath':'/var/jb/var/lib/cardash-diagnostics/helper-bootstrap.log','StandardErrorPath':'/var/jb/var/lib/cardash-diagnostics/helper-bootstrap.log','Sockets':{'ControlListeners':{'SockPathName':'/var/jb/var/lib/cardash-diagnostics/control.sock','SockPathMode':0o660,'SockPathOwner':0,'SockPathGroup':501,'SockType':'stream','SockFamily':'Unix'}}}
    plist(stage/'var/jb/Library/LaunchDaemons/com.cfluid.cardash.diagnostics.plist',job)
    manifest={'version':'0.1.1','target':'iPhone10,2 / 20G75 / Dopamine rootless','device_tested':False,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'sha256':{}}
    for path in sorted((stage/'var/jb').rglob('*')):
        if path.is_file():manifest['sha256'][str(path.relative_to(stage))]=hashlib.sha256(path.read_bytes()).hexdigest()
    (stage/'var/jb/usr/share/cardash-diagnostics/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    readme=ROOT/'README.md'
    if readme.exists():shutil.copy2(readme,stage/'var/jb/usr/share/cardash-diagnostics/README.txt')
    def tar_bytes(base):
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w:xz',format=tarfile.GNU_FORMAT) as tar:
            paths=sorted(base.rglob('*')) if base.name=='DEBIAN' else sorted((base/'var').rglob('*'))
            for path in paths:
                info=tar.gettarinfo(str(path),arcname='./'+str(path.relative_to(base)))
                info.uid=info.gid=0;info.uname=info.gname='root';info.mtime=1793923200
                executable=path.name in ['CarDashDiagnostics','cardash-diagnostics','postinst','prerm','postrm']
                info.mode=0o755 if path.is_dir() or executable else 0o644
                if path.is_file():
                    with path.open('rb') as f:tar.addfile(info,f)
                else:tar.addfile(info)
        return output.getvalue()
    payload=bytearray(b'!<arch>\n')
    for name,data in [('debian-binary',b'2.0\n'),('control.tar.xz',tar_bytes(stage/'DEBIAN')),('data.tar.xz',tar_bytes(stage))]:
        header=f'{name:<16}{1793923200:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode('ascii');assert len(header)==60
        payload+=header+data+(b'\n' if len(data)%2 else b'')
    dist=ROOT/'dist';dist.mkdir(exist_ok=True);deb=dist/'com.cfluid.cardash.diagnostics_0.1.1_iphoneos-arm64.deb';deb.write_bytes(payload)
    sha=hashlib.sha256(payload).hexdigest();(dist/(deb.name+'.sha256')).write_text(sha+'  '+deb.name+'\n')
    (dist/'manifest.json').write_text(json.dumps({**manifest,'deb_sha256':sha,'bytes':len(payload)},indent=2)+'\n');print(json.dumps({'deb':str(deb),'sha256':sha,'bytes':len(payload)},indent=2))
def simulator():
    shared=prepare();out=ROOT/'build/simulator';out.mkdir(exist_ok=True);app(shared,out,'iphonesimulator',True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',action='store_true');p.add_argument('--device',action='store_true');p.add_argument('--simulator',action='store_true');a=p.parse_args()
    if a.host:host()
    elif a.device:native()
    elif a.simulator:simulator()
    else:host();native()
