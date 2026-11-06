# CarDash V2 — 2.0.0 beta 25

This testing release removes setup codes and addresses dashboard loading, swiping, navigation selection, adaptive app grids and Now Playing artwork. It was built and tested locally while the owner's iPhone was disconnected. Beta25 has not yet been installed or measured in the Tesla or on a phone.

## Requirements and isolation

- Rootless jailbreak on A11 iPhone 8, 8 Plus or X, iOS 16.6.x. The installer rejects other models/versions. Earlier device trials used iPhone 8 Plus, iOS 16.6 and Dopamine; iPhone 8/X and 16.6.1 remain unverified.
- PreferenceLoader, uikittools and a compatible tweak loader (ElleKit on the test device).
- Personal Hotspot and a connected browser. Setup codes are gone: devices admitted to the trusted hotspot can obtain the single available controller. Local HTTP traffic is not encrypted.

The package is **CarDash V2 Beta** (`com.cfluid.cardash.v2`). It uses its own service, preferences, companion and port 8766. Updating it does not replace CarDash 1.x, migrate original preferences or delete original saved state. Existing V2 app switches, wallpaper and appearance choices are retained. Old pairing records are unused; no state cleanup/migration is performed.

## Install and connect

1. Download the DEB from the GitHub release and install it on the jailbroken iPhone using Filza or another DEB installer, with dependencies supplied by Sileo. The release URL is not a Sileo repository.
2. Respring after installation, unlock the phone, and reopen any apps used for testing. The V2 service starts automatically. There is no SSH or Canary requirement.
3. In **Settings → CarDash V2 Beta**, enable the desired apps. Complete their sign-in and permissions on the phone first.
4. Connect the Tesla to Personal Hotspot and open **http://100.99.10.2:8766/**. Other hotspot browsers may use **http://172.20.10.1:8766/**. The dashboard connects automatically, with no setup code, Remember checkbox or stored browser credential.
5. Select an app while the phone is unlocked. During preparation it may briefly appear on the phone, then the bundled **CarDash V2** companion takes the foreground. The selected native window stays landscape in the car browser. Once streaming, the phone can be locked for continuation testing.

The phone's **Connection Help in Safari** button is optional help; it does not acquire the car's controller. Only one browser controller can connect at a time. Close or End the other CarDash page if occupied. Reload or **Reconnect** reconnects without a code. **End** stops the session until Reconnect/reload. Hiding or closing the page ends its app session; returning reconnects but does not cold-launch an app. A lost browser expires through the existing six-second heartbeat lease.

Dashboard connection itself can occur while locked. **Choosing a different app or cold-launching one still requires unlock.** This is separate from keeping an already selected app rendering and accepting supported input while locked. The companion keeps the phone awake while visible; Side still locks it.

## Changes in beta25

- **No setup codes:** automatic hotspot connection, bounded retries and the existing single-controller, same-origin, peer and session-generation checks.
- **Stable icons and artwork:** unchanged state polls update images in place instead of rebuilding the grid/dock. Switching native apps no longer clears shared icons, wallpaper or artwork. At most two image requests run concurrently, and unchanged wallpapers are not decoded each second.
- **Frame scheduling:** removes the fixed 200 ms delay after every completed capture/decode; a frame cycle targets a minimum 100 ms total, with one request/decode in flight. It reuses the canvas backing buffer and pauses frame requests on hidden native views while retaining the app lease. This is a scheduling change, not a measured 10 fps guarantee on an iPhone/Tesla.
- **Dashboard swipe:** right from the first app page opens Dashboard; left returns. Gestures work from app icons and non-control dashboard card surfaces, including mouse-style pointer events. Media buttons and native app gestures retain their own input.
- **Last navigation app:** V2 remembers the last enabled Maps, Waze, Google Maps or recognized CarPlay navigation app. Dashboard shows that app's live native window preview; tapping expands the same selection. Selecting music does not overwrite the saved navigation choice.
- **Adaptive grid:** the recovered 4–5-column and 2–4-row geometry now uses the available viewport instead of always reducing its logical height to 320 points. Local 1280×720 and 1920×1080 layouts use 5×4; 800×480 uses 5×2. Browser zoom and viewport size affect the count.
- **Now Playing artwork:** a track/app change no longer leaves the previous item's cover behind when the new metadata lacks artwork. The browser retains loaded images during same-item refresh and app switching. Artwork actually delivered by YouTube Music still requires device verification.

The approved wallpapers, Home/Now Playing assets, fonts and native phone icon source are retained. The landscape-window capture, orientation lease, native input, keyboard and background lifecycle implementation are unchanged from the preceding release. Canary is excluded; the clean companion remains necessary for phone foreground handoff.

The navigation preview is the selected app's window, **not Apple's separate CarPlay Dashboard scene**. It can include the app's own controls and letterboxing. CarDash has one native capture selection: entering Dashboard may switch that selection to the last navigation app while unlocked. If another app is selected while locked, a new map selection must wait for unlock. This does not reproduce simultaneous CarPlay template scenes or guarantee pixel-identical glass/animations.

## Validation and remaining device checks

Local tests cover code-free connect, conflict/retry/End, stale requests, lease expiry, geometry/input/text queues, media artwork transitions, navigation classification, icon caching, swipe behavior, adaptive geometry and package isolation. Chrome integration with 4× CPU throttling and a delayed loopback fixture verified automatic connection, loaded icons, stable DOM nodes, bounded image requests, no repeated image downloads on app switching, a visible native navigation preview, expansion without reselecting, and zero frame requests while the native view is hidden. Native frames/metadata in this integration fixture are synthetic; it does not emulate jailbroken UIKit or measure a Tesla.

Earlier finite device trials remain historical evidence: beta23 Canary ran locked for 90.58 seconds, Waze 5.21.0 for 75.49 seconds and YouTube Music 6.34.1 for 90.43 seconds, with landscape capture and the recorded native controls. A beta24 companion candidate passed a further 65.02-second locked Waze trial. These are not beta25 device acceptance.

Please test while parked first:

- Real Tesla hotspot connection/reload without a setup code; another browser holding the controller.
- Icons and wallpaper on cold load, rapid app switching, and swipe both ways across Dashboard and app pages.
- Grid sizing at the actual Tesla viewport/zoom and touch near every edge.
- Waze/Maps selection, Dashboard preview, expansion, and persistence of the last navigation app after a service restart.
- YouTube Music artwork across track changes, native Now Playing layout, playback and pause/resume.
- Select while unlocked, then lock, lift/wake and rotate; verify landscape frames, native touch and keyboard. Different-app selection still requires unlock.
- Hotspot off/on, browser hide/reload, heartbeat cleanup, long sessions, heat, battery, latency, calls and memory pressure.

**YouTube video remains unresolved:** earlier YouTube 21.30.5 trials showed moving video on the phone while the browser's video region stayed black. Controls/audio could work; direct video-layer export was empty in a separate diagnostic build. DRM was not established as the cause. That diagnostic code is not shipped, and this release does not claim to fix video capture.

Wide layout does not supply an iPad binary or iPad-only resources. Some apps, protected surfaces and text responders are unsupported. The keyboard is CarDash's dashboard keyboard. All-app compatibility, moving navigation, exact CarPlay visual parity and sustained device performance remain unverified.

## Recovery and removal

If unavailable, End, unlock, Reconnect and choose the app again. Reopening the app may be necessary. Confirm the jailbreak and dependencies are active if the page does not load.

Remove only **CarDash V2 Beta** using the package manager, then respring. Removal stops only the V2 service and unregisters its companion, preserving original CarDash and both preference stores. The V2 network alias may remain until reboot. Re-jailbreak after reboot.

The download contains no SSH password, controller credential, device logs, personal theme captures, Canary binary, Immortalizer code or unrelated firmware files. Selected apps and fallback map/search providers use their normal network services.

## Download verification

DEB SHA-256: `72cc51617d9544e0f36b4a369c5f65819e60c5717a62c551e235cba99f548161`. Size: 27,758,266 bytes. The extracted package contains 52 files and 28 directories, passed byte/mode and V2-path audits, and has numeric root ownership throughout. The native app adapter and lifecycle dylibs are byte-for-byte identical to beta24.
