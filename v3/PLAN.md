# V3 native preview implementation

User authorized fixing the launcher, re-verifying native CarPlay and shipping a beta to testers. Original and V2 files/state are protected.

- Confirmed launcher failure: concurrent trial on 20261106-154154 collided with still-running 153943 receiver, EADDRINUSE 46201. Add kernel session lock/reopen behavior, retain exact failure logs.
- V3 is a separate com.cfluid.cardash.v3 package, version 3.0.0~beta.1. No V2 replacement, hooks or respring.
- Move receiver onto phone: Python3 stdlib network/plist/SRP/remux, small OpenSSL3 signed crypto bridge, existing ABI-gated native session helper. Dependencies Python3/libssl3 available from Procursus. No Mac/SSH needed in tester flow.
- Native H264 and HID only in initial native preview; audio/microphone and CarBridge independence remain explicit limitations. Retain native iOS16 rendering; do not advertise iOS27 runtime.
- Phone app: prepare identity, start/stop, show hotspot URL, export bounded diagnostic log. Setup uses verified pinned public DiPlay APK only when user taps Prepare; no accessory/phone private identity in distributed DEB or Git.
- One session at a time, bounded 5-minute beta trials, strict model/build gate (iPhone8Plus 16.6 20G75), private state under /var/jb/var/lib/cardash-v3; root local IPC. Browser port8890, automatic browser token, no pairing code. Browser inactivity ends native session. Loopback-only native protocol ports.
- Add cross-language crypto/protocol/muxer tests, install/remove/package audits, live phone/browser trials and dependency/provisioning failure checks. Publish pre-release + matching source/checksum/tester guide only after actual device validation.
