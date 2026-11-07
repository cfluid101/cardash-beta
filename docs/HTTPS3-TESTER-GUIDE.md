# CarDash V3 HTTPS3 — beta tester guide

Release: [v3.0.0-beta.5-https.3](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3). **Open-testing revision 1**, package version `3.0.0~beta.5+https.3.open.1`. The DEB and tester ZIP at this same URL were replaced on November 7, 2026. Download them again to obtain this revision. It changes installation eligibility; it is not a port verified on additional firmware.

## Compatibility

- **No installer phone-model or firmware-version allowlist.** The package firmware dependency and explicit installer/helper/backend model/build checks are removed. Other rootless arm64 devices may attempt installation and export diagnostics.
- The binaries target **iOS 16.0 or later**, matching the existing crypto link input. Rootless layout, Python 3.9+, libssl3, uikittools and a compatible tweak-injection provider remain actual runtime requirements. This DEB is not a stock-iOS/sideloadable app.
- Native operation has been verified only on **iPhone 8 Plus, iOS 16.6 build 20G75, Dopamine rootless**. Native framework identity, method-signature, instruction and memory-policy checks remain. If these do not match, the adapter reports unavailable and CarPlay cannot start. This revision does not implement new native adapters for iOS 17.6.1 or claim that version works.
- Car tested by the project owner: **2023 Tesla Model 3, AMD Ryzen**. On November 7, 2026, the owner reported that the latest car test was working nearly perfectly. This is a user report, not a measured latency result or a completed compatibility matrix.
- Native CarPlay-compatible interfaces come from the installed iOS runtime. Full interfaces for apps without native CarPlay support require **separately installed CarBridge** on the tested setup; CarBridge is not bundled.
- Personal Hotspot, initial internet access, and a browser with secure WebCodecs and Local Network Access support are needed. Microphone/Siri voice input is not implemented.

## Install and connect

1. Download the [DEB](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/com.cfluid.cardash.v3_3.0.0-beta.5-https.3_iphoneos-arm64.deb) or the [tester ZIP](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/CarDash-V3-HTTPS3-tester-pack.zip). Install the DEB with Sileo or another dependency-aware package manager. It requires Python 3, libssl3, uikittools and a compatible substrate provider such as ElleKit. Installation briefly restarts the media service.
2. Open **CarDash V3** on the unlocked iPhone. On first setup, tap **Prepare CarPlay** and let preparation finish. **Import downloaded DiPlay APK** is only a manual fallback if automatic preparation fails. It extracts setup data; it does not install an Android app. Existing setup is retained across upgrades; a setup-complete phone does not need preparation again. The first unlock after a reboot/respring is still required.
3. Enable Personal Hotspot and connect the Tesla to it. Open **[the HTTPS3 viewer](https://cfluid101.github.io/cardash-beta/option1/?v=https3)** in the Tesla browser.
4. In the viewer's iPhone address field, enter **`http://100.99.10.2:8890/`**. Keep the colon before `8890`. Allow Local Network Access if prompted, then press **Connect** and **Start**. No pairing/setup code is required. Close other CarDash viewer tabs during testing.
5. Leave Audio on **Device output**. Connect the iPhone to Tesla Bluetooth and select it as the car's audio source. iOS uses its selected speaker/Bluetooth route; CarDash does not select a named Bluetooth device. **Browser audio** remains optional, and changing the audio option restarts the native session.

GitHub supplies static viewer files only. Video, input, status and optional audio travel directly between the browser and iPhone on the local network. The initial viewer load needs internet access. Use a trusted hotspot, since connected devices can control the preview.

Controls hide after connection. **Controls** opens an overlay without resizing CarPlay; actual browser/full-screen size changes renegotiate native geometry. **Stop** ends the session. A prolonged browser disconnection ends the session after its heartbeat timeout; reconnect and press Start if necessary.

## What to test and report

Run a **20–30 minute navigation/audio test**. Do touch/setup checks while parked, or have a passenger perform them.

- Compare app-page swipes and Waze/YouTube Music switching at startup and after 10–20 minutes. Watch for delay that grows over time, freezes, or manual Reconnect being needed.
- Confirm audio remains on Tesla Bluetooth when starting CarPlay and switching apps. Test pause/resume and steering-wheel controls.
- Lock the phone, wake its Lock Screen without unlocking, and confirm the session remains usable.
- Show/hide the overlay controls and check that audio and the native session continue.

For a problem, record the approximate time, minutes since connection, phone model/iOS/jailbreak, Tesla model/year/browser version, selected app, phone lock state, and whether recovery was automatic. For audio issues, note the phone's actual output name before changing it. In CarDash V3, use **Export diagnostic report** and share it through the existing beta-testing channel; review it before sharing. There is no automatic diagnostic upload.

## Verification and rollback

This revision passed **244 local automated checks** (150 Python/native/package and 94 JavaScript), strict code-signature verification and package audits. No new physical-device tests were performed. Prior bandwidth/device/Tesla results refer to the original HTTPS3 build; see TEST-RESULTS.md for that historical evidence. Installation alone is not a successful CarPlay test. Other firmware may report an unavailable native adapter; export that report with the exact phone model, iOS build and jailbreak so a firmware-specific port can be assessed.

The [original tested HTTPS3 package and source](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/CarDash-V3-HTTPS3-before-open-testing.zip) are preserved together. To roll back on the originally supported device, stop CarPlay and install the old DEB from that archive, accepting a downgrade if prompted. Do not delete state directories. V3 uses separate settings from original CarDash/V2. The earlier [HTTPS2 release](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.2) also remains available.

Revised DEB SHA-256: `457bfd78326da6ee15c8268d2e87a3299f58f8e878d8fe23caf39dde628b10b3`.
Source commit: `c893510306d93a765f842a6b29156872a268865a`. The original release tag still identifies the earlier source; use this revision's accompanying source archive or the `v3.0.0-beta.5-https.3-open.1` source tag.
Corresponding source and license are available in the [release source archive](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/CarDash-V3-beta.5-https.3-source.zip).
