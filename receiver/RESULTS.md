# Native CarPlay live results — 2026-11-06

## Result and scope

A real native CarPlay session ran on the connected iPhone 8 Plus, iOS 16.6 (20G75), Dopamine rootless. The native `CARSessionStatus.currentSession` reported present, authenticated and activated. The receiver decoded the phone’s encrypted 1280 × 720 H.264 output and delivered HID touch reports that visibly navigated Waze, the native dashboard, the native home grid and YouTube Music. This is the iOS 16.6 CarPlay renderer, not a recreation of the home screen and not an iOS 27 runtime port.

The receiver runs on the Mac through USB SSH forwards. A bounded, separately signed arm64 probe invokes CarKit on the phone and serves its loopback timing endpoint. The existing CarDash beta was not replaced. This is a working native video/input prototype, **not a complete Tesla-ready release**.

## What prevented the previous request from becoming usable

1. A successful CarKit request callback did not prove a live session. The phone required the receiver to complete SRP pairing, Ed25519/X25519 pair verification, encrypted control framing, and a separate accessory-authentication exchange.
2. The initial video-only capability declaration produced an AirPlay endpoint but no usable native CarPlay session. On this specific iOS 16.6 target, the full CarPlay feature declaration with audio-format metadata produced an authenticated, activated session and a native screen-stream offer. Audio transport remains unimplemented; metadata alone is not audio support.
3. Apple’s binary plist represented some 64-bit stream identifiers as negative integers. Deriving the screen key with the equivalent unsigned decimal value fixed authenticated video decryption.
4. Empty screen heartbeats and repeated codec configuration are valid. Treating them as errors broke an otherwise live stream.
5. Browser remuxing required durations calculated from successive native timestamps. Fixed-duration rounding produced overlapping samples. Static CarPlay screens also legitimately pause frame delivery. Regular keyframe requests while a browser is viewing let its rolling buffer be trimmed without discarding the frames needed to continue decoding.

These are observations from controlled iterations on this phone, not guarantees for other iOS versions.

## Evidence

Private raw evidence stays in `../evidence/receiver-live/`. Each run has `native.ndjson`, `receiver.ndjson`, filtered `service.log`, `combined.ndjson`, a source/binary hash manifest, and captured native video. The final run is `20261106-152709`; its sanitized numeric summary is `validation-summary.json` beside this document.

- The earlier two-minute run `20261106-151145` captured about 3,500 native frames and demonstrated native dashboard/home/Waze/YouTube Music navigation. A teardown timestamp issue found there was fixed before the final run.
- The final 150-second trial observed an authenticated, activated native session for 148.875 seconds and received 2,579 native frames with zero receiver errors. Independent FFmpeg decoding also reported zero errors. Normal cleanup returned `currentSession` to nil; the phone remained unlocked with its display on.
- Final browser run: 601 displayed native frames, one browser-reported dropped frame out of 605 total, four acknowledged HID reports, three buffer trims, and 0.203 seconds of video buffered ahead of playback at the final measurement.
- Closing and reopening the browser within the same native session: 605 displayed native frames, three browser-reported dropped frames out of 611 total, four acknowledged HID reports, three buffer trims, and 0.205 seconds buffered ahead at the final measurement. This is a buffer-depth measurement, **not measured end-to-end input latency**.
- Both browser runs decoded 1280 × 720 video after resizing the viewer to 1600 × 900. The receiver’s source geometry remains fixed at 1280 × 720; adaptive native resizing is not established.
- All 21 host tests passed, covering cryptographic/framing rejection, pairing verification, unsigned stream identifiers, input lease behavior and independent decoding of test media. Synthetic fixtures exist only in tests; live video came from the phone.
- REA inspected the tested arm64 helper: SHA-256 `a80f40f3debd498aaf53aaa30326889b22bcf68cb9dd323bfe5a70b8293eaef2`, evidence ID `ev_3762c7342e0c1a430494b9fb82a44854221bbd8c206a98ae5157f701de412a03`. Static inspection establishes binary identity, not successful runtime behavior; the device and browser logs establish the live result.

One earlier browser result (`20261106-152312`) was rejected during review: a null buffer-depth value incorrectly satisfied a JavaScript comparison. Its separate review record marks it unaccepted. The final harness requires finite buffer depth and observed trimming, and both final browser runs passed those stronger checks.

## Identity and independence limits

Pairing uses a generated, separately stored receiver identity. The accessory exchange used the experimental identity in the verified public DiPlay 0.2.22 APK. iOS accepted it on this device. No Apple framework or authentication check was patched. This does not establish MFi certification, universal compatibility or an identity appropriate for a public product release. Credentials and raw reports are excluded from Git and any source distribution.

CarBridge was already installed on this phone. Therefore the observed wide YouTube Music/arbitrary-app surfaces do **not** prove an independent replacement for CarBridge. The installed YouTube Music version’s unsupported-version banner also remained visible. Audio playback and video-content compatibility were not tested by this native receiver trial.

## Still required before a release

- Implement and verify audio output, audio focus, microphone and reconnect behavior.
- Port or package the receiver on the iPhone so operation does not require this Mac and SSH tunnel.
- Verify switching and cold-starting apps while locked on this native path; this trial intentionally kept the phone unlocked.
- Establish arbitrary-app behavior independently of installed CarBridge, including keyboard and full gesture/multitouch support.
- Test Tesla browser networking, fullscreen geometry, long-duration recovery, heat and battery use.
- Resolve accessory-identity provisioning and distribution for a product.

## Preservation

The original host project’s 585 entries and original DEB matched their recorded baseline. All 23 protected device files/preferences and all 203 tracked product-file baseline hashes also matched. The final trial’s cleanup and phone state are recorded in the validation summary. The original daemon was already stopped before this work and was left in that state. No original project, original preference migration, beta package replacement, or respring was performed.
