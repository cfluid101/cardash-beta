# CarDash V3 Native Preview — 3.0.0 beta 1

This is a **separate rootless native CarPlay video/touch beta**, running entirely on the iPhone. It is not a complete replacement for the V2 daily-use dashboard. No Mac, USB connection, SSH login or browser setup code is required after installation. The original CarDash and V2 packages/preferences remain separate.

## Supported test device

**iPhone 8 Plus, iOS 16.6 build 20G75, rootless jailbreak.** The installer and native helper reject other models/builds. This is the hardware/build on which native API identity and signatures were verified. Do not install by bypassing these checks.

Install the DEB with Sileo or another dependency-aware package manager. It needs `python3`, `libssl3` and `uikittools` from the existing rootless bootstrap. Installing only the DEB with plain `dpkg -i` does not fetch missing dependencies. No respring is requested.

## First run

1. Open **CarDash V3** on the iPhone. Keep it unlocked for the first test.
2. Tap **Prepare Native Preview** and confirm the one-time approximately 18 MB download. The phone needs internet access for this step. The app fetches the pinned public DiPlay 0.2.22 APK, checks its SHA-256 and verifies that the experimental accessory certificate matches its key. It stores only the required identity locally; the downloaded APK is removed. No personal or accessory private keys are bundled in this release.
   If the background download times out, download **DiPlay-0.2.22.apk** from the [official DiPlay release](https://github.com/shihabal3amri/DiPlay/releases/tag/v0.2.22) in Safari, then use **Import downloaded DiPlay APK** in the V3 app and select it from Files. The same checksum and certificate checks apply. This also permits offline import of a file already copied to the phone.
3. Enable Personal Hotspot and connect the car or test computer to it. Open the address shown by the V3 phone app, including port **8890**. The usual hotspot address is `http://172.20.10.1:8890/`.
4. Press **Start** in the browser. A trial lasts five minutes. Use the native icons and bottom-left Home button. Press Full screen to hide the preview toolbar.
5. Press Stop, close the browser, or wait for the timer. The native request ends automatically. Start another trial to repeat. Reopening a browser reuses the active native session.

A browser disconnect stops the session after about 12 seconds; a trial started on the phone waits up to 45 seconds for its first browser. The five-minute cap is intentional in this preview. Static native screens can stop emitting new video until something changes; that alone is not a connection failure.

## What this beta does and does not establish

- Receives and decrypts the real iOS 16.6 native CarPlay H.264 stream, sends native HID touches, and remuxes video for the browser without a second encode. Fixed 1280 × 720 landscape source.
- **No audio output or microphone support.** Audio capabilities are declared for native-session negotiation, but audio streams are not accepted by this build. Do not use it as the only source of audible navigation instructions.
- Locked-phone switching, cold-start while locked, adaptive source sizing and Tesla-specific browser/network behavior still require dedicated testing. Initial acceptance testing uses an unlocked phone.
- CarBridge was installed on the development phone. Wide/arbitrary-app behavior is not established independently of CarBridge; native CarPlay-compatible apps and CarBridge-hosted apps are different compatibility categories. The release does not bundle or replace CarBridge.
- Experimental accessory authentication was accepted on the test device; this is not MFi certification or a guarantee on other iOS versions. This package does not install the iOS 27 CarPlay runtime.

## Privacy and network access

Use a trusted Personal Hotspot. Connected local-network devices can open and control the preview without a pairing code. The browser gets an automatic short-lived service token; cross-origin requests are rejected. Native protocol listeners are loopback-only. No analytics or automatic report uploads are included.

The release stores bounded diagnostic logs and its own private receiver identity under `/var/jb/var/lib/cardash-v3`. It does not record video. **Export diagnostic report** creates one shareable report with install/service/native-session events, counts and errors, without private keys or viewer credentials. Review it before sharing. Removing the package stops only the V3 service and retains its own reports/identity for troubleshooting; it does not remove the original or V2 data.

## If something fails

- No app/service: export diagnostics if available and retain the package-manager installation error. Check that dependencies installed successfully.
- Preparation error: check the phone's internet connection, then retry Prepare. A failed or mismatched download cannot start a session.
- No video: stop other real CarPlay connections and the Mac research receiver, then Start again. V3 refuses to replace an existing native session.
- Stale stream: export diagnostics, press Stop, then Start again. Record whether the phone was locked or rotated and which app was selected.
- The browser's session-ended message after five minutes or after disconnect is expected.

See `TEST-RESULTS.md` for exact release validation and remaining device tests. Source/provenance is supplied with the beta under GPL-3.0-only.
