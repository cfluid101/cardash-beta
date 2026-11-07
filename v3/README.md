# CarDash V3 Beta 4

A separate, phone-resident **native CarPlay video, touch and audio-output beta** for an iPhone 8 Plus on iOS 16.6 build 20G75 with a rootless jailbreak. Sessions have no fixed time limit. The receiver runs entirely on the phone; a running session needs no Mac, USB cable, SSH connection or browser setup code.

This receives the phone's real iOS 16.6 CarPlay interface. It does not install iOS 27 or emulate a newer CarPlay runtime. Original CarDash and V2 preferences remain separate.

## Install and connect

1. Install the DEB through Sileo or another dependency-aware package manager. Required bootstrap packages are `python3`, `libssl3`, `uikittools` and a compatible `mobilesubstrate` provider such as ElleKit. Installation briefly restarts the media service to load the USB-free adapter. The installer rejects unverified phone models/builds; do not bypass that check.
2. Open **CarDash V3** on the unlocked phone. Tap **Prepare CarPlay** once. This downloads approximately 18 MB from the pinned [DiPlay 0.2.22 release](https://github.com/shihabal3amri/DiPlay/releases/tag/v0.2.22), verifies the APK checksum and accessory identity, and removes the download after import. If downloading fails, save the same APK in Files and use **Import downloaded DiPlay APK**. No private identity is bundled with the beta. Preparation persists across sessions and package upgrades. The background service started automatically after the tested userspace reboot with CarDash V3 closed; the first unlock after a reboot is still required. **Setup complete** means no further preparation is needed; start the session from the browser.
3. Enable Personal Hotspot, connect the Tesla to it, and open **http://100.99.10.2:8890/** when the phone app shows that Tesla address as ready. Keep the colon before `8890`. The app lists other local addresses separately for ordinary Wi-Fi browsers. Beta 4 creates and verifies its own loopback address; it does not replace the original CarDash address.
4. Leave **Audio: Phone / Bluetooth** selected to keep music on the phone’s normal output. Connect the iPhone to the Tesla by Bluetooth and select that audio source in the car. Tap **Start** in the browser. For streamed sound instead, choose **Browser audio**; changing the selection restarts CarPlay and the choice is remembered. Tap **Enable sound** if needed. **Mute/Unmute** and **Retry sound** apply only to Browser audio.
5. Use the native icons and Home button. Waze/YouTube Music switching and music pause/resume have been verified while the phone stays locked over Wi-Fi without USB. **Full screen** hides the web toolbar; its exit control restores it. **Stop** ends the session.

The session continues while browser heartbeats arrive. Closing/disconnecting the browser ends it after about 12 seconds; a session started from the phone waits up to 45 seconds for its first viewer. If iOS supplies no native video within 45 seconds, startup stops with an error. This startup deadline and the disconnect checks do not limit a streaming session. Native protocol sockets listen only on loopback. The source display is fixed 1280×720 landscape and stretches independently in both dimensions to fill the available browser area. This can alter proportions on a differently shaped screen; it is not an increase in native rendering resolution. **Full screen** fills the available browser viewport, not Tesla’s surrounding system controls.

## Audio and compatibility

- **Phone / Bluetooth is the default.** A firmware-specific, session-scoped adapter keeps CarPlay from claiming the phone’s audio output. It does not pair Bluetooth devices or send steering-wheel commands; those use the existing phone/car Bluetooth connection.
- Optional **Browser audio** receives music and navigation output through authenticated native audio streams. PCM is supported; AAC-LC decoding is included and tested with independent synthetic vectors on the device. This release does not bypass Tesla’s video restrictions in Drive. A vehicle-imposed browser restriction cannot be verified or removed by a parked desktop test. Test setup and media while parked.

See `TEST-RESULTS.md` for the actual negotiated formats and device trials.
- **No microphone capture or voice-call/Siri input in this beta.** iOS 16 requires duplex format declarations to construct its audio table. A requested input stream sends authenticated digital silence and reports `mutedInput`; it does not record the phone or car microphone. Use a separate supported route for calls.
- CarPlay-compatible app interfaces come from iOS. **CarBridge is required for the arbitrary/full-app interfaces tested on the development phone.** This package neither bundles nor replaces CarBridge. Apps without native CarPlay support are not promised to work on a phone without it. Other preexisting tweaks can affect compatibility.
- Experimental accessory authentication was accepted on the supported device. This is not MFi certification or a guarantee on other iOS versions.
- Tesla browser/audio routing, Personal Hotspot interruptions, long-duration temperature/battery behavior and other tester environments require vehicle testing. USB-free operation has been exercised over home Wi-Fi, but that does not establish behavior in Tesla’s actual browser or through its speaker routing.

## Access, diagnostics and removal

Use a trusted Personal Hotspot: connected local-network devices can open and control CarDash without a pairing code. The browser receives an automatic service token; cross-origin requests and stale session controls are rejected. There is no analytics or automatic report upload.

The service records bounded browser viewport/playback counters, pause/visibility state and decoder errors roughly every 15 seconds during a session. It does not read the car’s gear state. The service rotates its receiver event log and stores its own receiver identity under `/var/jb/var/lib/cardash-v3`. It does not record video or audio. **Export diagnostic report** combines bounded tails of installation, service and native-session logs, counters and errors. Installation and startup log files themselves are retained. Private keys and browser credentials are excluded; review the report before sharing.

Removing V3 stops its service, unloads its adapter by restarting the media service, and retains its identity/reports. It does not delete original CarDash or V2 preferences. Earlier diagnostics/V2 test packages are removed separately on the development phone after validation; this installer does not silently uninstall other packages on testers' phones.

If a session fails, export diagnostics and try Stop → Start. The status distinguishes native startup, waiting for video, and browser playback; exported status and startup errors also identify whether the USB-free transport adapter loaded. Diagnostics include service startup stages and native input responses to distinguish a launch failure from an inactive interface. Stop any other real CarPlay connection first: V3 will not replace an existing native session. Record package version, phone/build, car/browser version, app and lock state. Initial identity preparation and the first unlock after a respring/reboot still require phone access.

This release does not bypass Tesla’s video restrictions in Drive. A vehicle-imposed browser restriction cannot be verified or removed by a parked desktop test. Test setup and media while parked.

See `TEST-RESULTS.md` for verified results and remaining checks. Corresponding source and provenance are included under GPL-3.0-only.
