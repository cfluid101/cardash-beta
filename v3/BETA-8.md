# CarDash V3 Beta 8 — iOS 15.4.1 compatibility

Package `3.0.0~beta.8`, November 16, 2026. Based on the released beta 7 source. This adds an experimental native profile for **iPhone 13 Pro / iOS 15.4.1 / 19E258 / standard Dopamine** in the same V3 package.

**This build has not run on a physical phone.** Firmware inspection, native fixtures and package tests support sending it to the tester; they do not establish successful injection or a working native CarPlay session. Keep the previous working DEB for rollback. Installation restarts the media service.

## Changes

- Added exact CarKit, APTransport, MediaExperience and AirPlaySender profiles from the matching Apple IPSW. Selection checks the loaded implementation, architecture, method ownership/types and instruction bytes. Unknown implementations remain rejected.
- Reused the inspected dictionary-host and four-argument video CopyProperty interfaces for 15.4.1. Existing storage, ownership, mapping, lease and cleanup checks remain.
- Lowered every bundled native binary and the companion's deployment minimum to 15.4.1. The external crypto link input is an authentic Procursus iOS 15 library, verified against signed repository metadata; its minimum is 15.0. The build checks its exact SHA256. No Apple framework or OpenSSL library is bundled.
- Retained the iPhone 8 Plus / 16.6 / 20G75 and iPhone 14 Pro Max / 16.0 / 20A357 profiles. The latter remains experimental pending physical acceptance. Beta 7's browser recovery, video timing, bitrate control and audio policy are retained.

The package ID and data locations are unchanged, so this is an upgrade of CarDash V3. It uses the same [Viewer 4 page](https://cfluid101.github.io/cardash-beta/option1/?v=https3&ui=4); no viewer update is required.

## Tester procedure

1. Keep the previous DEB and use a dependency-aware package manager such as Sileo to install this beta on standard Dopamine. Let the device's matching rootless repository resolve `python3`, `libssl3`, `uikittools` and the Substrate-compatible injection provider. Do not install an iOS 16 OpenSSL package onto iOS 15.
2. Open CarDash V3 and export a diagnostic report before starting. Confirm it identifies beta 8, iPhone14,2 and 19E258. Confirm the reported framework UUIDs match the four identities in NATIVE-PROFILES.md and the adapters report ready; do not bypass an unavailable-adapter error.
3. Start a fresh session over Wi-Fi/hotspot with USB disconnected. Check first video, navigation/touch, locked app switching, Device audio and Browser audio. Start CarPlay before playing music: beta 7's known audio-at-Start routing issue is unchanged.
4. Check viewer shrink/restore and reconnect, then Stop. Verify audio returns to the intended route and the next session starts normally. Repeat after a userspace reboot to check service startup and injection.
5. Export diagnostics after either success or failure and include any relevant crash report. Repeat this acceptance sequence on the existing iPhone 8 Plus and iPhone 14 Pro Max before treating beta 8 as a replacement for their working release.

## Coverage limits

This is a standard-rootless package with arm64 helpers and an arm64/arm64e adapter. It does not add RootHide-native or rootful packaging, iOS 17.6.1 support, or support for every firmware above 15.4.1. The deployment minimum is not a compatibility range. Additional firmware families require verified profiles and device acceptance; see [COMPATIBILITY.md](COMPATIBILITY.md) and [NATIVE-PROFILES.md](NATIVE-PROFILES.md).

Validation results are recorded in [TEST-RESULTS.md](TEST-RESULTS.md). The source archive includes the tests and exact build-input requirements in [BUILD.md](BUILD.md).
