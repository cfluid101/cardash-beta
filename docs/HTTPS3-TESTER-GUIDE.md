# CarDash V3 HTTPS3 — beta tester guide

Release: [v3.0.0-beta.5-https.3](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3). This is the same DEB used in the latest owner-reported Tesla trial. It remains a beta.

## Compatibility

- Supported test target: **iPhone 8 Plus, iOS 16.6 build 20G75, Dopamine rootless**. The installer and native adapters check the device/firmware. Do not bypass these checks for another model or build.
- Car tested by the project owner: **2023 Tesla Model 3, AMD Ryzen**. On November 7, 2026, the owner reported that the latest car test was working nearly perfectly. This is a user report, not a measured latency result or a completed compatibility matrix.
- Native CarPlay-compatible interfaces come from iOS 16.6. Full interfaces for apps without native CarPlay support require **separately installed CarBridge** on the tested setup; CarBridge is not bundled.
- Personal Hotspot, initial internet access, and a browser with secure WebCodecs and Local Network Access support are needed. Microphone/Siri voice input is not implemented.

## Install and connect

1. Download the [DEB](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/com.cfluid.cardash.v3_3.0.0-beta.5-https.3_iphoneos-arm64.deb) or the [tester ZIP](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/CarDash-V3-HTTPS3-tester-pack.zip). Install the DEB with Sileo or another dependency-aware package manager. It requires Python 3, libssl3, uikittools and a compatible substrate provider such as ElleKit. Installation briefly restarts the media service.
2. Open **CarDash V3** on the unlocked iPhone. On first setup, tap **Prepare CarPlay** and let preparation finish. Existing setup is retained across upgrades; a setup-complete phone does not need preparation again. The first unlock after a reboot/respring is still required.
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

The release includes 242 automated checks, an eleven-minute controlled 1–4 Mbps bandwidth trial, stream-break recovery and a final idle-screen/resume check. The owner has since reported a successful Tesla trial. Additional devices, long drives, navigation prompts mixed with music, steering-wheel controls and thermal/battery behavior still need tester coverage. See the release's TEST-RESULTS.md and RELEASE-VERIFICATION.md for the measured evidence and limits.

If this beta regresses, stop CarPlay and reinstall [HTTPS2](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.2). Do not delete state directories. V3 uses separate settings from original CarDash/V2; it does not replace their project files. The exact tested package is unchanged for this tester handoff.

DEB SHA-256: `2e22e0b13da6df82e9a33f24546f65db177201d9aae641ae4e6e78c5badab164`.
Corresponding source and license are available in the [release source archive](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/CarDash-V3-beta.5-https.3-source.zip).
