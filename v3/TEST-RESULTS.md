# CarDash V3 Native Preview beta 1 — validation

Tested November 6, 2026 (Pacific), on the connected iPhone 8 Plus, iOS 16.6 build 20G75, Dopamine rootless. The original CarDash/V2 files and preferences were protected throughout. This is a native video/touch preview, not a declaration that the complete CarDash product requirements are finished.

## Verified

| Check | Result |
|---|---|
| Original Mac launcher failure | A second launch collided with the still-running receiver on port 46201. The kernel lock prevents concurrent trials; reopening reused the existing viewer. The corrected live Mac trial displayed 604 frames, zero drops, and four HID reports. |
| Phone-resident package | Installed separately as `com.cfluid.cardash.v3`. Receiver, authentication, video decrypt/remux, and native input ran on the phone under launchd. The Mac forwarded only HTTP for the browser trial; it did not host the native receiver. |
| Native authentication and activation | CarKit reported both authenticated and activated. Real iOS 16.6 CarPlay frames reached Chrome; Home and Waze selection were sent through native HID. |
| Full timed trial | Passed at 303.212 seconds including setup/cleanup observation; 8,422 native frames received. Initial browser sample: 605 total frames, one drop, 0.189 s buffer lag. Late sample: 6,827 total frames, four drops, 0.182 s buffer lag, no decoder error. These are measured buffer lag values, not end-to-end touch latency. |
| Browser geometry | Decoded source stayed 1280×720 while the browser resized from 1280×760 to 1600×900. |
| Teardown | After bounded cleanup, CarKit reported no session, authenticated/activated false, video/event sockets closed, and no service error. The launchd receiver remained on its first launch for the trial. |
| Service memory correction | The rootless launchd proxy ignored the declared memory allowance and initially killed valid APK import at its 6 MB limit. The fix sets only each V3 process’s own 128 MB active/inactive limit and verifies it through the kernel. Independent readback confirmed `[128,1,128,1]`. No global or unrelated-process policy changed. |
| Identity setup | A fresh download from the pinned official DiPlay release passed SHA-256 and certificate/key verification on the phone after internet connectivity was restored. Invalid APK data was rejected. Valid APK import as mobile UID 501 succeeded after the memory fix without restarting the service. |
| Access and stale requests | During the full native trial, stale stop/heartbeat/touch requests and a cross-origin stop request returned rejection; the active native session was unchanged. |
| Diagnostic export | Mobile UID 501 retrieved the combined report, including memory-policy and native-session events. No private key, receiver seed or viewer cookie was present in the checked report. A host test covers bounded reads of oversized supporting logs. |
| Host tests | 16 V3 Python tests, 21 reference receiver JavaScript tests, and one cross-process launcher-lock test passed: 38 total. Covers crypto vectors/forgery, fragmented/replayed protocol frames, MP4 byte parity, stale input, HTTP access checks, memory-policy failure, malformed provisioning and rootless DEB boundaries. |
| Physical crypto/protocol checks | Five tests passed under the phone’s Python runtime with its signed OpenSSL bridge. The native video captured by the development lab also independently decoded in FFmpeg. The distributed release does not record video. |
| Preservation | Original project: 585 entries unchanged; original DEB unchanged. Product baseline: 203 files unchanged. Protected installed files/preferences: all 23 hashes unchanged. |

The full trial used the final native receiver/transport logic. Subsequent source changes bounded report-export reads and handled an immediate duplicate-launch startup race; these do not change the native transport. Rejected/interrupted development trials are retained privately and are not counted as passes. Raw reports/screenshots are excluded from public assets because they may contain device or location details.

## Still needs device/vehicle testing

- Tesla’s actual browser over Personal Hotspot, physical USB disconnect, network changes, sleep/reconnect, and car-specific Full screen behavior. The Mac and phone were on different networks, so browser acceptance used a USB HTTP forward.
- Locked-phone cold start, repeated app switching while locked, wake/rotation interactions, calls and Siri interruptions with this new V3 native receiver. Earlier V2 Canary results do not prove these V3 cases.
- YouTube Music playback/artwork, YouTube video, keyboard entry, long gestures/multitouch and other apps under the packaged V3 receiver. CarBridge was already installed; arbitrary-app support without it is not established.
- Other phone models/builds, other jailbreaks, fresh bootstrap installs and dependency resolution on a tester’s network. The installer intentionally rejects unverified models/builds.
- Manual companion Files-picker/share-sheet interaction and new-network Safari checks. The underlying mobile-user import/export IPC paths were tested directly.
- Long-duration battery, thermal and memory behavior beyond five-minute trials; audio output, microphone and adaptive native source resolution are not implemented.

## Tester record

Test while parked. Record package version, phone/build/jailbreak, browser/car version, app selected, whether the phone was locked, and the steps leading to any failure. Export the single report from CarDash V3 after the issue and review it before sharing. A five-minute timeout or cleanup roughly 12 seconds after browser heartbeats stop is expected. No reinstall is needed to start another trial.
