# HTTPS3 compatibility beta 1

Package version: `3.0.0~beta.5+https.3.open.2`.

This is the full CarDash V3 package, including native display/input, device or browser audio, the HTTPS3 congestion controls, and diagnostic export. It adds an experimental compatibility path for the framework identities reported by the iPhone 14 Pro Max running iOS 16.0 build 20A357. The original iPhone 8 Plus/iOS 16.6 path remains. **The new path has not yet been run on the tester's physical device.**

## Install and test

1. Stop CarPlay and close its browser viewers. Install this DEB over existing V3 using Sileo or another dependency-aware package manager. Installation restarts V3 and Apple's media service; avoid an active call/music session during installation. Do not uninstall, reset setup or delete saved state.
2. Open CarDash V3 on the unlocked phone. Its subtitle should say **compatibility beta 1**. If setup is complete, keep it; no APK re-import is required. A genuinely new installation still needs Prepare CarPlay once.
3. With the Tesla parked and connected to Personal Hotspot, use the same [HTTPS3 viewer](https://cfluid101.github.io/cardash-beta/option1/?v=https3), entering the address displayed by the app (normally `http://100.99.10.2:8890/`). Connect and Start as usual. Keep **Device output** selected for phone/Bluetooth audio.
4. First verify native frames increase and Home/app pages respond. Then check Waze and YouTube Music switching, sound on the selected device route, and continued input/display while locked. Actual app availability depends on iOS and any installed CarBridge integration.
5. Tap **Export diagnostic report** whether the connection works or fails. Exporting while connected preserves a useful active status snapshot; exporting after stopping still includes session history. Share the new `.ndjson` and describe the observed result. Reports are not automatically uploaded. If installation/app launch fails, share the package manager's installation output.

There is no fixed session-duration limit. Existing startup and disconnected-viewer deadlines remain. There is no new browser setup code. Model/build and framework identities are collected automatically; users do not select a firmware profile.

## What changed after diagnostics 3

The tester's report established that the arm64e library loaded, but each old media profile was rejected and the newer CarKit host initializer was absent. Code was obtained whose four framework UUIDs match that report. The new paths select by actual implementation identity, architecture, method types and instruction fingerprints. OS/build strings are diagnostic context rather than an installer/model allowlist.

- **Transport:** a separate arm64e profile uses the observed APTransport update/disconnect entries, PAC prologues, and verified state/capture layouts. Additional mapped-state/value checks precede the new profile's writes. Changes remain scoped to CarDash's own loopback host.
- **Audio:** the new MediaExperience profile locates the verified four-instruction device-routing setter and the exact byte it writes. Existing ownership, lease expiry and restoration logic remains.
- **Video budget:** this version inlines network-info creation inside a four-argument CopyProperty function. A separately typed adapter calls the native function first and only caps the successful NetworkInfo dictionary for CarDash's display. It retains native congestion calculations, status, caller allocator and output ownership. The original one-argument 16.6 helper remains separate.
- **CarKit:** the old `initWithHostProperties:` dictionary path uses its verified keys. Host fields and secure coding are checked before requesting a session. The callback contract is supported by the matching framework's actual block descriptor and argument forwarding; the report does not claim that carkitd was inspected.
- **Diagnostics:** the previous bounded inventory/export remains available and now includes the selected host profile and its evidence. Optional PID-bound transport/video reason fields distinguish identity, mapping, symbol and hook failures. Both successful and failed results survive the app's export filtering. Unknown implementations still report unavailable. See [transport reasons](TRANSPORT-DIAGNOSTICS.md) and [video reasons](VIDEO-BUDGET-DIAGNOSTICS.md).

## Validation limits

Host tests and static code analysis support a targeted beta trial, not a compatibility guarantee. Some cross-image call names in the reconstructed symbol images are derived from consistent import-stub relocation and calling patterns; original cache-island bytes are unavailable. Device injection/trampolines, native handshake/video, actual Bluetooth output, locked switching, cleanup and long-run behavior must be confirmed on the tester's phone. See TEST-RESULTS.md and NATIVE-PROFILES.md.

This is not a completed RootHide runtime port or universal support for every jailbroken device/iOS version. The original project and saved state were not modified. No firmware images, saved identities or accessory private keys are bundled.

## Rollback

Stop CarPlay and use the package manager to install/downgrade to the [previous HTTPS3 open-testing DEB](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/com.cfluid.cardash.v3_3.0.0-beta.5-https.3_iphoneos-arm64.deb), or [diagnostics 3](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3-diag.3). Keep `/var/jb/var/lib/cardash-v3` intact. Downgrading restores earlier software, not a proven working session on the iOS 16.0 tester's phone.
