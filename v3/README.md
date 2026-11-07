# CarDash V3 Beta 2

A separate, phone-resident **native CarPlay video, touch and audio-output beta** for an iPhone 8 Plus on iOS 16.6 build 20G75 with a rootless jailbreak. Sessions have no fixed time limit. No Mac, USB, SSH or browser setup code is needed after installation.

This receives the phone's real iOS 16.6 CarPlay interface. It does not install iOS 27 or emulate a newer CarPlay runtime. Original CarDash and V2 preferences remain separate.

## Install and connect

1. Install the DEB through Sileo or another dependency-aware package manager. Required bootstrap packages are `python3`, `libssl3` and `uikittools`. The installer rejects unverified phone models/builds; do not bypass that check.
2. Open **CarDash V3** on the unlocked phone. Tap **Prepare CarPlay** once. This downloads approximately 18 MB from the pinned [DiPlay 0.2.22 release](https://github.com/shihabal3amri/DiPlay/releases/tag/v0.2.22), verifies the APK checksum and accessory identity, and removes the download after import. If downloading fails, save the same APK in Files and use **Import downloaded DiPlay APK**. No private identity is bundled with the beta. Preparation persists across sessions and package upgrades.
3. Enable Personal Hotspot, connect the Tesla to it, and open the address displayed by the phone app, including port **8890**. Usually this is `http://172.20.10.1:8890/`.
4. Tap **Start** in the browser. That gesture also enables browser sound. If joining an already-running session, tap **Enable sound**. **Mute/Unmute** affects browser output; **Retry sound** reconnects audio after an error. The car may require its browser audio source/volume to be enabled.
5. Use the native icons and Home button. **Full screen** hides the web toolbar; its exit control restores it. **Stop** ends the session.

The session continues while browser heartbeats arrive. Closing/disconnecting the browser ends it after about 12 seconds; a session started from the phone waits up to 45 seconds for its first viewer. These disconnect checks are not a session-duration limit. Native protocol sockets listen only on loopback. The source display is fixed 1280×720 landscape, fitted without distortion; adaptive source resolution is not included.

## Audio and compatibility

- Music and navigation output are received through authenticated native audio streams. PCM is supported; AAC-LC decoding is included and tested with independent synthetic vectors on the device. See `TEST-RESULTS.md` for the actual negotiated formats and device trials.
- **No microphone capture or voice-call/Siri input in this beta.** iOS 16 requires duplex format declarations to construct its audio table. A requested input stream sends authenticated digital silence and reports `mutedInput`; it does not record the phone or car microphone. Use a separate supported route for calls.
- CarPlay-compatible app interfaces come from iOS. **CarBridge is required for the arbitrary/full-app interfaces tested on the development phone.** This package neither bundles nor replaces CarBridge. Apps without native CarPlay support are not promised to work on a phone without it. Other preexisting tweaks can affect compatibility.
- Experimental accessory authentication was accepted on the supported device. This is not MFi certification or a guarantee on other iOS versions.
- Tesla browser/audio routing, Personal Hotspot interruptions, long-duration temperature/battery behavior and other tester environments require vehicle testing. USB HTTP forwarding on the development Mac does not prove Tesla behavior.

## Access, diagnostics and removal

Use a trusted Personal Hotspot: connected local-network devices can open and control CarDash without a pairing code. The browser receives an automatic service token; cross-origin requests and stale session controls are rejected. There is no analytics or automatic report upload.

The service keeps bounded diagnostic logs and its own receiver identity under `/var/jb/var/lib/cardash-v3`. It does not record video or audio. **Export diagnostic report** combines installation, service and native-session events, counters and errors. Private keys and browser credentials are excluded; review the report before sharing.

Removing V3 stops its service and retains its identity/reports. It does not delete original CarDash or V2 preferences. Earlier diagnostics/V2 test packages are removed separately on the development phone after validation; this installer does not silently uninstall other packages on testers' phones.

If a session fails, export diagnostics and try Stop → Start. Stop any other real CarPlay connection first: V3 will not replace an existing native session. Record package version, phone/build, car/browser version, app and lock state. Initial identity preparation and the first unlock after a respring/reboot still require phone access.

See `TEST-RESULTS.md` for verified results and remaining checks. Corresponding source and provenance are included under GPL-3.0-only.
