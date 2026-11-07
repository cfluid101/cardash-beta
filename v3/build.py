#!/usr/bin/env python3
"""Build an isolated V3 rootless DEB. This script never deploys or connects."""
from pathlib import Path
import subprocess,plistlib,hashlib,json,shutil,io,tarfile,os,importlib.util,re
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'v3';OUT=ROOT/'build/v3/release';VERSION='3.0.0~beta.4'
def run(args):subprocess.run([str(x) for x in args],check=True,cwd=ROOT)
def writeplist(path,value):path.write_bytes(plistlib.dumps(value))
def source_commit():
 path=ROOT/'SOURCE-COMMIT.txt';value=path.read_text().strip() if path.exists() else ''
 if re.fullmatch('[0-9a-f]{40}',value):return value
 return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def sign(path,ent=None):
 run(['codesign','--force','--sign','-',*(['--entitlements',ent] if ent else []),path]);run(['codesign','--verify','--strict',path])
def main():
 OUT.mkdir(parents=True,exist_ok=True);sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
 flags=['xcrun','--sdk','iphoneos','clang++','-arch','arm64','-miphoneos-version-min=16.6','-isysroot',sdk,'-x','objective-c++','-std=c++17','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations']
 helper=OUT/'cardash-v3-session';run([*flags,'-I',ROOT/'src',SRC/'native/SessionProbe.mm',ROOT/'src/Common.m',ROOT/'src/NativeIdentity.mm',ROOT/'src/HostPayload.mm','-framework','Foundation','-o',helper])
 ent=OUT/'session-entitlements.plist';writeplist(ent,{'platform-application':True,'com.apple.private.security.no-sandbox':True,'com.apple.private.carkit.sessionRequest':True,'com.apple.private.carkit':True});sign(helper,ent)
 download=OUT/'cardash-v3-download';run([*flags,SRC/'native/Download.mm','-framework','Foundation','-o',download]);basic=OUT/'basic-entitlements.plist';writeplist(basic,{'platform-application':True,'com.apple.private.security.no-sandbox':True});sign(download,basic)
 service=OUT/'cardash-v3-service';run(['xcrun','--sdk','iphoneos','clang','-arch','arm64','-isysroot',sdk,'-miphoneos-version-min=16.6','-Wall','-Wextra','-Werror',SRC/'native/Service.c','-o',service]);sign(service,basic)
 crypto=OUT/'libcardashcrypto.dylib';openssl=Path(subprocess.check_output(['brew','--prefix','openssl@3'],text=True).strip())
 stub=ROOT/'build/v3/device/libcrypto.3.dylib'
 if not stub.is_file():raise RuntimeError('The exact rootless libssl3 3.2.1 link input is required; see BUILD.md')
 run(['xcrun','--sdk','iphoneos','clang','-arch','arm64','-isysroot',sdk,'-miphoneos-version-min=16.6','-dynamiclib','-Wall','-Wextra','-Werror','-I',openssl/'include',SRC/'native/Crypto.c',stub,'-install_name','/var/jb/usr/lib/cardash-v3/backend/libcardashcrypto.dylib','-o',crypto]);sign(crypto)
 audio=OUT/'libcardashaudio.dylib';run(['xcrun','--sdk','iphoneos','clang','-arch','arm64','-isysroot',sdk,'-miphoneos-version-min=16.6','-dynamiclib','-Wall','-Wextra','-Werror',SRC/'native/AudioDecode.c','-framework','AudioToolbox','-install_name','/var/jb/usr/lib/cardash-v3/backend/libcardashaudio.dylib','-o',audio]);sign(audio)
 network=OUT/'libcardashnetwork.dylib';run(['xcrun','--sdk','iphoneos','clang','-arch','arm64','-isysroot',sdk,'-miphoneos-version-min=16.6','-dynamiclib','-Wall','-Wextra','-Werror',SRC/'native/Network.c','-install_name','/var/jb/usr/lib/cardash-v3/backend/libcardashnetwork.dylib','-o',network]);sign(network)
 loopback=OUT/'CarDashV3Loopback.dylib';run([*flags,SRC/'native/Loopback.mm',SRC/'native/AudioRoute.mm','-dynamiclib','-framework','Foundation','-install_name','/var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.dylib','-o',loopback]);sign(loopback)
 app=OUT/'CarDashV3.app';app.mkdir(exist_ok=True);run([*flags,SRC/'app/main.mm','-framework','Foundation','-framework','UIKit','-o',app/'CarDashV3'])
 writeplist(app/'Info.plist',{'CFBundleIdentifier':'com.cfluid.cardash.v3.host','CFBundleExecutable':'CarDashV3','CFBundleName':'CarDash V3','CFBundleDisplayName':'CarDash V3','CFBundlePackageType':'APPL','CFBundleInfoDictionaryVersion':'6.0','CFBundleVersion':'3','CFBundleShortVersionString':'3.0.0','MinimumOSVersion':'16.6','CFBundleSupportedPlatforms':['iPhoneOS'],'LSRequiresIPhoneOS':True,'UIDeviceFamily':[1],'UILaunchScreen':{},'UIUserInterfaceStyle':'Dark','UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait'],'CFBundleIconFiles':['AppIcon'],'CFBundleIcons':{'CFBundlePrimaryIcon':{'CFBundleIconFiles':['AppIcon']}}})
 spec=importlib.util.spec_from_file_location('diagnostic_build',ROOT/'build.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.icon(app/'AppIcon@2x.png',120);module.icon(app/'AppIcon@3x.png',180)
 appent=OUT/'app-entitlements.plist';writeplist(appent,{'application-identifier':'com.cfluid.cardash.v3.host','platform-application':True,'com.apple.private.security.no-sandbox':True,'com.apple.private.security.container-required':False});sign(app,appent)
 stage=OUT/'stage'
 if stage.exists():shutil.rmtree(stage)
 for name in ['DEBIAN','var/jb/usr/libexec','var/jb/usr/lib/cardash-v3/backend','var/jb/usr/lib/cardash-v3/web','var/jb/Applications','var/jb/Library/LaunchDaemons','var/jb/Library/MobileSubstrate/DynamicLibraries']:(stage/name).mkdir(parents=True,exist_ok=True)
 for name in ['control','preinst','postinst','prerm','postrm']:shutil.copy2(SRC/'packaging'/name,stage/'DEBIAN'/name)
 for path in [helper,download,service]:shutil.copy2(path,stage/'var/jb/usr/libexec'/path.name)
 shutil.copy2(loopback,stage/'var/jb/Library/MobileSubstrate/DynamicLibraries'/loopback.name)
 writeplist(stage/'var/jb/Library/MobileSubstrate/DynamicLibraries/CarDashV3Loopback.plist',{'Filter':{'Executables':['mediaserverd']}})
 shutil.copytree(app,stage/'var/jb/Applications/CarDashV3.app')
 for path in (SRC/'backend').iterdir():
  if path.is_file() and path.suffix in ('.py','.plist'):shutil.copy2(path,stage/'var/jb/usr/lib/cardash-v3/backend'/path.name)
 for library in [crypto,audio,network]:shutil.copy2(library,stage/'var/jb/usr/lib/cardash-v3/backend'/library.name)
 for path in (SRC/'web').iterdir():
  if path.is_file():shutil.copy2(path,stage/'var/jb/usr/lib/cardash-v3/web'/path.name)
 for name in ['README.md','NOTICE.md','LICENSE','TEST-RESULTS.md']:
  if (SRC/name).exists():shutil.copy2(SRC/name,stage/'var/jb/usr/lib/cardash-v3'/name)
 writeplist(stage/'var/jb/Library/LaunchDaemons/com.cfluid.cardash.v3.plist',{'Label':'com.cfluid.cardash.v3','ProgramArguments':['/var/jb/usr/libexec/cardash-v3-service'],'EnvironmentVariables':{'PATH':'/var/jb/usr/bin:/var/jb/bin:/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','DISABLE_TWEAKS':'1'},'UserName':'root','ProcessType':'Interactive','RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':15,'ExitTimeOut':8,'JetsamProperties':{'MemoryLimit':128,'MemoryLimitInactive':128,'Priority':10},'Umask':0o077,'StandardOutPath':'/var/jb/var/lib/cardash-v3/service-bootstrap.log','StandardErrorPath':'/var/jb/var/lib/cardash-v3/service-bootstrap.log'})
 files={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((stage/'var').rglob('*')) if p.is_file()}
 manifest={'version':VERSION,'target':'iPhone10,2 / iOS16.6 / 20G75 / rootless','source_commit':source_commit(),'files':files,'audio_supported':True,'session_limit_seconds':None,'private_credentials_included':False}
 (stage/'var/jb/usr/lib/cardash-v3/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 def tar(base,paths):
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w:xz',format=tarfile.GNU_FORMAT) as archive:
   for p in paths:
    info=archive.gettarinfo(str(p),arcname='./'+str(p.relative_to(base)));info.uid=info.gid=0;info.uname=info.gname='root';info.mtime=1793923200
    exe=p.name in ('preinst','postinst','prerm','postrm','CarDashV3','cardash-v3-session','cardash-v3-download','cardash-v3-service')
    info.mode=0o755 if p.is_dir() or exe else 0o644
    with p.open('rb') if p.is_file() else open(os.devnull,'rb') as f:archive.addfile(info,f if p.is_file() else None)
  return out.getvalue()
 deb=bytearray(b'!<arch>\n')
 for name,data in [('debian-binary',b'2.0\n'),('control.tar.xz',tar(stage/'DEBIAN',sorted((stage/'DEBIAN').rglob('*')))),('data.tar.xz',tar(stage,sorted((stage/'var').rglob('*'))))]:
  deb+=f'{name:<16}{1793923200:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode()+data+(b'\n' if len(data)%2 else b'')
 dist=ROOT/'dist/v3';dist.mkdir(parents=True,exist_ok=True);path=dist/('com.cfluid.cardash.v3_'+VERSION+'_iphoneos-arm64.deb');path.write_bytes(deb)
 sha=hashlib.sha256(deb).hexdigest();(dist/'SHA256SUMS.txt').write_text(sha+'  '+path.name+'\n');print(json.dumps({'deb':str(path),'bytes':len(deb),'sha256':sha}))
if __name__=='__main__':main()
