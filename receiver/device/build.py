from pathlib import Path
import subprocess,plistlib,hashlib,json
root=Path(__file__).resolve().parents[2]
out=root/'build/receiver';out.mkdir(parents=True,exist_ok=True)
sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
args=['xcrun','--sdk','iphoneos','clang++','-arch','arm64','-miphoneos-version-min=16.6','-isysroot',sdk,'-x','objective-c++','-std=c++17','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations','-I',str(root/'src'),str(root/'receiver/device/SessionProbe.mm'),str(root/'src/Common.m'),str(root/'src/NativeIdentity.mm'),str(root/'src/HostPayload.mm'),'-framework','Foundation','-o',str(out/'session-probe')]
subprocess.run(args,check=True)
ent=out/'entitlements.plist';ent.write_bytes(plistlib.dumps({'platform-application':True,'com.apple.private.security.no-sandbox':True,'com.apple.private.carkit.sessionRequest':True,'com.apple.private.carkit':True}))
subprocess.run(['codesign','--force','--sign','-','--entitlements',str(ent),str(out/'session-probe')],check=True)
subprocess.run(['codesign','--verify','--strict',str(out/'session-probe')],check=True)
print(json.dumps({'sha256':hashlib.sha256((out/'session-probe').read_bytes()).hexdigest()}))
