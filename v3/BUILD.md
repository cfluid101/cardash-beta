# Build

Build on the prepared Mac with Xcode/iPhoneOS SDK, Python3, Node20+ (tests), FFmpeg (validation), and Homebrew OpenSSL3 headers. Run `python3 v3/build.py` from the diagnostics repository. It builds/signs arm64 executables, the UIKit companion and crypto bridge, then constructs a root-owned rootless DEB under `dist/v3`.

The link input at `build/v3/device/libcrypto.3.dylib` must be from the rootless Procursus libssl3 3.2.1 package used on the target. It is an external build dependency and is not copied into the output package. Its install name must resolve to `/var/jb/usr/lib/libcrypto.3.dylib`. Use the package manager's verified package/library; do not substitute an unrelated desktop dylib.

The `src/Common.m`, `src/NativeIdentity.mm`, `src/HostPayload.mm` and associated headers are required alongside `v3/`. A matching source archive accompanies the beta. The package builder neither connects to nor installs on a phone. `v3/tests/` contains host tests; set `CDV3_CRYPTO` to the host-built OpenSSL bridge when running them. The separate Mac `receiver/` remains a research/reference implementation, with its duplicate-launch fix and its own manual launcher.

Build the host crypto bridge before running Python tests:

```sh
mkdir -p build/v3/host
xcrun clang -dynamiclib -Wall -Wextra -Werror -I"$(brew --prefix openssl@3)/include" v3/native/Crypto.c -L"$(brew --prefix openssl@3)/lib" -lcrypto -o build/v3/host/libcardashcrypto.dylib
codesign --force --sign - build/v3/host/libcardashcrypto.dylib
CDV3_CRYPTO="$PWD/build/v3/host/libcardashcrypto.dylib" python3 -m unittest discover -s v3/tests
node --test receiver/test/*.test.mjs
python3 receiver/test/session_lock_test.py
```

Build the DEB first for the package audit. The browser test requires `npm ci --prefix receiver` and a deliberately started, supported physical-phone service forwarded to localhost:8890. It is not a simulator test. `CDV3_FULL_TRIAL=1 node v3/tests/browser-check.mjs <existing-evidence-directory>` keeps its owned headless browser open for the complete five-minute trial.

The service verifies its own 128 MB active/inactive budget through the XNU memorystatus API. On the tested Dopamine bootstrap, launchd's declared JetsamProperties were ignored; the kernel readback is the acceptance check. No other process's memory policy is changed. API definitions: [Apple XNU 8796 kern_memorystatus.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-8796.121.2/bsd/sys/kern_memorystatus.h).
