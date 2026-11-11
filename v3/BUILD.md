# Build

Build on the prepared Mac with Xcode/iPhoneOS SDK, Python3, Node20+ (tests), FFmpeg (validation), and Homebrew OpenSSL3 headers. Run `python3 v3/build.py` from the diagnostics repository. It builds/signs arm64 executables, the UIKit companion, native service launcher, crypto bridge, AudioToolbox AAC decoder and network-address bridge, plus a universal arm64/arm64e media-service adapter, then constructs a root-owned rootless DEB under `dist/v3`.

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
node --test v3/tests/test_*.mjs
node --test receiver/test/*.test.mjs
python3 receiver/test/session_lock_test.py
```

The loopback adapter is compiled from `v3/native/Loopback.mm` and injected only into `mediaserverd` through the installed Substrate-compatible provider. Its supported APTransport image UUID is `BCC474F5-2745-3652-995F-A06F650F76FC`; both hook locations also require matching instruction prologues. Do not relax these guards to enable another firmware without analyzing and testing that firmware. Readiness is published through Darwin notification state because the media service is sandboxed. The backend rejects startup if the matching adapter is unavailable. Device cache extracts and Apple framework binaries used for analysis are private research inputs and are not build or distribution payloads.

The service launchd job invokes `cardash-v3-service`, which records the exec boundary and executes the packaged Python backend. Fixed stderr phase labels identify Python entry, import completion and later startup boundaries without logging credentials. `DISABLE_TWEAKS=1` applies only to the V3 daemon and its helper children; it does not disable injection in SpringBoard, CarPlay apps or the media service. The job uses `ProcessType=Interactive`: the Adaptive configuration stalled before its entry point during a fresh userspace boot, while Interactive passed the recorded reboot trial with CarDash V3 closed. Warm restarts had passed under both modes and were not treated as boot proof. This result is specific to the tested device/bootstrap; see `TEST-RESULTS.md`. The installer/removal scripts restart the media service to load/unload this package's adapter. Installation does not start a CarPlay session.

Build the DEB first for the package audit. The browser test requires `npm ci --prefix receiver` and a deliberately started, supported physical-phone service forwarded to localhost:8890. It is not a simulator test. A forwarded USB browser test alone cannot validate the USB-free fix: separately disconnect USB and exercise a fresh session from a browser on the phone’s Wi-Fi/hotspot network. `CDV3_FULL_TRIAL=1 node v3/tests/browser-check.mjs <existing-evidence-directory>` keeps its owned headless browser open for the six-minute endurance trial and explicitly stops it afterward.

The service verifies its own 128 MB active/inactive budget through the XNU memorystatus API. On the tested Dopamine bootstrap, launchd's declared JetsamProperties were ignored; the kernel readback is the acceptance check. No other process's memory policy is changed. API definitions: [Apple XNU 8796 kern_memorystatus.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-8796.121.2/bsd/sys/kern_memorystatus.h).

The optional-audio route adapter (`AudioRoute.mm`, `AudioVM.h`) requires MediaExperience UUID `1790DBAE-04B6-32B7-B5E7-AA39E571B208`, exact setter instructions and readable/executable or writable leaf VM mappings. It changes transient media-service state only during an owned CarDash host and a live PID-bound audio lease. The backend refreshes the lease every two seconds; the monitor expires it after eight seconds and preserves the latest observed native routing intent. It does not alter firmware on disk or Tesla driving restrictions. Do not relax identity guards for another firmware.

Beta 5's display geometry is negotiated per native session from the browser viewport. The geometry budget is at most 1,280 pixels wide, 960 pixels high and 921,600 total pixels; dimensions are even and the source remains at least as wide as tall. Native display declarations, HID bounds and MP4 dimensions must agree with the actual H.264 SPS. Browser presentation preserves aspect ratio, and iOS chooses the app grid. A fixed four-column layout is not a build guarantee. Viewport changes restart the owned native session; preserve generation checks and the selected audio output.

HTTPS2 adds an experimental hosted frontend at `https://cfluid101.github.io/cardash-beta/option1/?v=https2`. Static assets use relative paths. The approved HTTPS origin obtains a memory-only browser token from the local phone; all media and control requests go directly to that local endpoint. Browser Local Network Access permission and secure WebCodecs support are required. The hosted path parses the existing bounded H.264/fMP4 stream and paints VideoDecoder output to WebGL/canvas; it does not silently select JPEG or MediaSource. The existing local HTTP page retains its capability-based fallback behavior, but the native-JPEG experiment failed on the supported iPhone with callback status `-12780` and is not a validated fallback. No Tesla firmware, gear state or vehicle setting is changed.

Keep overlay controls outside native geometry measurement: their visibility must not restart CarPlay. Only actual window resizing by the owning viewer, or explicit Fit display, applies new geometry. HTTPS2 network and timeline recovery replaces the browser video stream only; it must not stop the native session or audio. Preserve the three-recoveries-per-minute bound, ten-second timeline-catchup cooldown, stale-callback checks and generation-bound touch release ordering.

The retained MediaSource path tracks random-access points from emitted MP4 fragments. It must not remove a range in the current GOP: MSE may extend removal through the next random-access point. Keep the one-tick safety margin and stale-session ownership checks. iOS’s wire-level `forceKeyFrame` restarts its screen bitstream, so continuous heartbeat-driven encoder resets are prohibited; only joining viewers and bounded long-GOP recovery request them. Canvas joins and recovery must remain bounded for the same reason.

HTTPS3 also compiles `v3/native/VideoBudget.mm` into the media-service adapter. It requires the AirPlaySender UUID `9CD94B73-B47B-3B7F-A87E-DE176FCE841D`, matching function bytes and executable mapping. The network-info override checks CarDash's display UUID and wired-CarPlay flags, then reduces only its advertised bandwidth while a valid PID-bound eight-second lease exists. Other displays receive the original dictionary. No Apple preference or framework file is modified. Startup checks this adapter before launching.

## HTTPS3 open-testing revision 1

The package version is `3.0.0~beta.5+https.3.open.1`. Firmware dependencies and explicit installer/helper/backend model/build allowlists are removed. All bundled Mach-O images and the companion now target iOS 16.0. This matches the existing rootless libcrypto link input’s minimum. It is the binary deployment floor, not a tested compatibility range. Rootless layout, arm64 architecture, runtime packages, memory-policy readback, and exact native identity/instruction/method checks remain required. The existing HTTPS3 release URL is reused; its matching revised source archive records the new commit. The original release tag and the old tested DEB are preserved for rollback. No new physical-device compatibility claim is made.

## Local service diagnostics candidate

The diagnostics candidates link UIKit-independent ServiceClient, ServiceEnvironment and ServiceDiagnostics helpers into the companion. Host tests exercise real temporary Unix sockets and files. The standard rootless runtime/startup/native adapter paths remain unchanged. Offline `.jbroot` discovery is read-only evidence collection, not a RootHide package flavor. See SERVICE-DIAGNOSTICS.md.

## Architecture candidate 2

Version `3.0.0~beta.5+https.3.open.1.diag.2` builds the injected media-service library with both arm64 and arm64e slices. Standalone processes remain arm64. The package test inspects the actual DEB payload with lipo, checks both slices' iOS deployment floor and verifies signatures across all architectures. Installer model/firmware allowlists remain absent.

The companion automatically includes model, iOS version/build and package version in an exported diagnostic report. Users do not select an architecture or copy build numbers manually. Exact framework identity/instruction checks remain unchanged; this corrects an architecture packaging gap and does not establish working native CarPlay on iOS 16.0/arm64e. See COMPATIBILITY.md for the remaining work.

## Compatibility diagnostics 3

The universal adapter also compiles `v3/native/NativeInventory.mm`, a read-only media-framework identity publisher. The standalone session helper includes `v3/native/SessionInspection.mm` and accepts `--inspect` before normal session argument handling. Export invokes that bounded mode independently of startup guards. Neither collector changes native hook implementations or requests a session. The build still targets iOS 16.0, with warnings treated as errors; the app's package label and build number identify diagnostics 3. See SERVICE-DIAGNOSTICS.md for collection and rollback.
