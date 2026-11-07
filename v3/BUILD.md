# Build

Build on the prepared Mac with Xcode/iPhoneOS SDK, Python3, Node20+ (tests), FFmpeg (validation), and Homebrew OpenSSL3 headers. Run `python3 v3/build.py` from the diagnostics repository. It builds/signs arm64 executables, the UIKit companion, native service launcher, crypto bridge, AudioToolbox AAC decoder, network-address bridge and APTransport/MediaExperience adapters, then constructs a root-owned rootless DEB under `dist/v3`.

The link input at `build/v3/device/libcrypto.3.dylib` must be from the rootless Procursus libssl3 3.2.1 package used on the target. It is an external build dependency and is not copied into the output package. Its install name must resolve to `/var/jb/usr/lib/libcrypto.3.dylib`. Use the package manager's verified package/library; do not substitute an unrelated desktop dylib.

The `src/Common.m`, `src/NativeIdentity.mm`, `src/HostPayload.mm` and associated headers are required alongside `v3/`. A matching source archive accompanies the beta. The package builder neither connects to nor installs on a phone. `v3/tests/` contains host tests; set `CDV3_CRYPTO` to the host-built OpenSSL bridge when running them. The separate Mac `receiver/` remains a research/reference implementation, with its duplicate-launch fix and its own manual launcher.

The release source archive includes `SOURCE-COMMIT.txt`, expanded by Git during export, so building the archive does not require a `.git` directory. It includes V3, shared native sources, and reference libraries/tests; the Mac-specific research launcher remains available in the repository.

Build the host crypto bridge before running Python tests:

```sh
mkdir -p build/v3/host
xcrun clang -dynamiclib -Wall -Wextra -Werror -I"$(brew --prefix openssl@3)/include" v3/native/Crypto.c -L"$(brew --prefix openssl@3)/lib" -lcrypto -o build/v3/host/libcardashcrypto.dylib
codesign --force --sign - build/v3/host/libcardashcrypto.dylib
xcrun clang -dynamiclib -Wall -Wextra -Werror v3/native/AudioDecode.c -framework AudioToolbox -o build/v3/host/libcardashaudio.dylib
codesign --force --sign - build/v3/host/libcardashaudio.dylib
CDV3_CRYPTO="$PWD/build/v3/host/libcardashcrypto.dylib" CDV3_AUDIO="$PWD/build/v3/host/libcardashaudio.dylib" python3 -m unittest discover -s v3/tests
node --test v3/tests/test_audio_browser.mjs v3/tests/test_client_recovery.mjs
node --test receiver/test/*.test.mjs
python3 receiver/test/session_lock_test.py
```

The loopback adapter is compiled from `v3/native/Loopback.mm` and injected only into `mediaserverd` through the installed Substrate-compatible provider. Its supported APTransport image UUID is `BCC474F5-2745-3652-995F-A06F650F76FC`; both hook locations also require matching instruction prologues. Do not relax these guards to enable another firmware without analyzing and testing that firmware. Readiness is published through Darwin notification state because the media service is sandboxed. The backend rejects startup if the matching adapter is unavailable. Device cache extracts and Apple framework binaries used for analysis are private research inputs and are not build or distribution payloads.

The service launchd job invokes `cardash-v3-service`, which records the exec boundary and executes the packaged Python backend. Fixed stderr phase labels identify Python entry, import completion and later startup boundaries without logging credentials. `DISABLE_TWEAKS=1` applies only to the V3 daemon and its helper children; it does not disable injection in SpringBoard, CarPlay apps or the media service. The job uses `ProcessType=Interactive`: the Adaptive configuration stalled before its entry point during a fresh userspace boot, while Interactive passed the recorded reboot trial with CarDash V3 closed. Warm restarts had passed under both modes and were not treated as boot proof. This result is specific to the tested device/bootstrap; see `TEST-RESULTS.md`. The installer/removal scripts restart the media service to load/unload this package's adapter. Installation does not start a CarPlay session.

Build the DEB first for the package audit. The browser test requires `npm ci --prefix receiver` and a deliberately started, supported physical-phone service forwarded to localhost:8890. It is not a simulator test. A forwarded USB browser test alone cannot validate the USB-free fix: separately disconnect USB and exercise a fresh session from a browser on the phone’s Wi-Fi/hotspot network. `CDV3_FULL_TRIAL=1 node v3/tests/browser-check.mjs <existing-evidence-directory>` keeps its owned headless browser open for the six-minute endurance trial and explicitly stops it afterward.

The service verifies its own 128 MB active/inactive budget through the XNU memorystatus API. On the tested Dopamine bootstrap, launchd's declared JetsamProperties were ignored; the kernel readback is the acceptance check. No other process's memory policy is changed. API definitions: [Apple XNU 8796 kern_memorystatus.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-8796.121.2/bsd/sys/kern_memorystatus.h).

The optional-audio route adapter (`AudioRoute.mm`, `AudioVM.h`) requires MediaExperience UUID `1790DBAE-04B6-32B7-B5E7-AA39E571B208`, exact setter instructions and readable/executable or writable leaf VM mappings. It changes transient media-service state only during an owned CarDash host and a live PID-bound audio lease. The backend refreshes the lease every two seconds; the monitor expires it after eight seconds and preserves the latest observed native routing intent. It does not alter firmware on disk or Tesla driving restrictions. Do not relax identity guards for another firmware.

Beta 5's display geometry is negotiated per native session from the browser viewport. The geometry budget is at most 1,280 pixels wide, 960 pixels high and 921,600 total pixels; dimensions are even and the source remains at least as wide as tall. Native display declarations, HID bounds and MP4 dimensions must agree with the actual H.264 SPS. Browser presentation preserves aspect ratio, and iOS chooses the app grid. A fixed four-column layout is not a build guarantee. Viewport changes restart the owned native session; preserve generation checks and the selected audio output.

The release keeps H.264 in fragmented MP4 with the existing MediaSource renderer. It includes no vehicle-restriction bypass. The browser retains random-access points reported from emitted MP4 fragments. It must not remove a range in the current GOP: MSE may extend removal through the next random-access point. Keep the one-tick safety margin and stale-session ownership checks. iOS’s wire-level `forceKeyFrame` restarts its screen bitstream, so continuous heartbeat-driven encoder resets are prohibited; only joining viewers and bounded long-GOP recovery request them.
