# CarDash V2 — 2.0.0 beta 24

CarDash V2 serves a landscape CarPlay-style dashboard to your car's browser over the iPhone's Personal Hotspot. This beta includes native app-window capture, targeted touch, an on-screen dashboard keyboard, and automatic background lifecycle support for the selected app. A small CarDash V2 companion app is included to take the phone’s foreground while the chosen app streams in the background. Immortalizer, CarBridge and the Canary debugging app are not required.

## Requirements

- iPhone 8, iPhone 8 Plus or iPhone X (A11), rootless jailbreak, iOS 16.6.x. The package rejects other hardware and iOS versions.
- Verified device: iPhone 8 Plus, iOS 16.6, Dopamine. iPhone 8/X and 16.6.1 remain unverified.
- PreferenceLoader, uikittools and a compatible tweak loader (the test device uses ElleKit).
- Personal Hotspot and a browser connected to it. Use a strong hotspot password and only trusted connected devices; dashboard traffic uses local HTTP.

This package installs separately as **CarDash V2 Beta** (`com.cfluid.cardash.v2`). It does not replace CarDash 1.x, migrate its preferences, or delete saved state. V2 has its own app switches and wallpaper selection. The original service, if installed, remains separate on its old port; V2 uses port 8766.

## Install and connect

1. Download the release `.deb` on the jailbroken iPhone. Open it in a local DEB installer such as Filza and install with dependencies satisfied in Sileo. This is a DEB download, not a Sileo repository URL.
2. On the first V2 installation, respring using your jailbreak's normal control, then unlock the phone. This loads V2's native hooks. V2's service starts automatically; no SSH or Canary is needed. After future updates that change native hooks, respring again.
3. Open **Settings → CarDash V2 Beta**. Enable the apps you want to show. Open each chosen app once on the phone to finish its sign-in, permissions and initial setup.
4. Enable Personal Hotspot. Connect the Tesla to it. Keep the phone unlocked during pairing and app selection.
5. In iPhone Settings → CarDash V2 Beta, tap **Open Setup in Safari**. Alternatively, open `http://127.0.0.1:8766/setup.html` directly in Safari on that iPhone. Choose **Create setup code on phone**.
6. In the Tesla browser open **http://100.99.10.2:8766/**. Enter the eight-digit code under Native connection, leave **Remember this browser** checked, then press **Connect**. Codes expire after two minutes, work once, and are invalidated after ten wrong guesses. Other hotspot devices can also use `http://172.20.10.1:8766/`.
7. Choose an app while the phone is unlocked. The selected app may briefly appear on the phone during preparation, then the included CarDash V2 companion takes the foreground. Once its landscape window is streaming, the phone may be locked. Keep the car browser visible. The existing selected app can continue rendering and accepting supported touch/keyboard input while locked.

Pairing is remembered by this browser at this address until you choose **Forget this browser** or clear its site data. Reopening the page reconnects without another code when the phone is unlocked. A different browser or address needs its own initial pairing. Use **Reconnect** after an explicit **End**; End retains the saved pairing. Only one browser controller connects at a time. Closing or hiding the browser ends its app session; reconnection never automatically launches an app. The companion keeps the phone awake while its setup screen is visible; the Side button still locks it. New app selection, cold launch and setup while locked are not supported in this beta. Keeping an already selected app active while locked is the behavior verified so far.

## What changed

- Every real installed-app icon uses the same native landscape/background session path, including Maps and the currently playing app. The built-in Now Playing and Settings tiles remain dashboard views. Apps whose native session cannot be prepared report unavailable; individual surfaces such as video can still fail within a connected session. There is no screen-mirroring fallback.
- Landscape-only native app windows, independent of the phone's orientation; no Phone fit mode.
- Swipe right from the first app page to Dashboard/Now Playing, and left to return. Swipes may begin on app icons; ordinary taps still launch them.
- Remembered browser pairing, explicit Reconnect and Forget controls. Canary and the companion are excluded from the dashboard app catalog. Canary is not shipped; the companion is a small phone setup screen with no debug server.
- Selected-window touch mapping and a dashboard keyboard for supported text fields.
- Built-in, finite lifecycle leases; no external backgrounding tweak dependency.
- Wake/rotation handling for the tested app/window configurations and cleanup when the session ends or heartbeats stop.
- Actual phone app icons, including supported system icon themes, with the approved test theme’s Home/Now Playing assets and wallpapers.
- Preserves the tested CarPlay fonts, geometry, wallpapers, Home button, glass styling and animations. Browser glass/shader rendering remains an approximation; exact parity on every real CarPlay display is unverified.
- Beta24 adds automatic isolated service startup, remembered browser pairing, a dedicated phone setup page, dashboard swipe navigation and an A11/iOS 16.6.x install gate.
- App switching waits for the previous selection to close. Remembered reconnection detaches unfinished work from the retired controller so delayed responses cannot block or overwrite the new session. App titles refresh when the current catalog arrives.

**YouTube video image is not supported in this beta:** on YouTube 21.30.5, the app controls and audio worked but the video region stayed black in Chrome, including while the video was visibly playing on the phone. A fresh process and returning from Picture in Picture to inline playback did not resolve it. Temporary diagnostics found an attached video layer with both reported capture-protection flags false; direct exports of that video layer and its immediate content child were empty. This is an unresolved selected-window video-capture limitation; DRM was not established as the cause. The diagnostic code is not shipped. YouTube Music audio controls are a separate verified behavior.

The wide layout does not turn an iPhone app into its iPad binary or force iPad-only resources. Some apps may not adapt, may block capture, or may use unsupported windows/text responders. The keyboard is CarDash's dashboard keyboard, not a captured Apple/iPad keyboard.

## Verified so far

On iPhone 8 Plus/iOS 16.6/Dopamine, independent beta23 tests ran without Immortalizer loaded in the trial SpringBoard:

| App | Recorded result |
| --- | --- |
| Canary test app | 90.58 seconds locked with wake/rotation, continuous wide capture, actual button responses, keyboard insertion/delete/Done, then normal-window restoration and reconnect |
| Waze 5.21.0 | 75.49 seconds locked with wake/rotation, wide map/menu input and search keyboard; text was cleared and no route was started |
| YouTube Music 6.34.1 | 90.43 seconds locked with wake/rotation and native pause/resume; final playback paused; stopping browser heartbeats expired the lifecycle lease and rejected old credentials after 8.21 seconds |

Each selected window was 1024×600, captured as 3072×1800 on this 3× device. No portrait frames or browser loss were observed in these finite trials. All three windows subsequently returned to their recorded normal dimensions after session cleanup. These are short device trials, not all-app or endurance guarantees.

Beta24 was installed and upgraded on the same iPhone. Its package started the V2 service automatically as root, launchd restarted it after a scoped termination test, eight-digit pairing succeeded, actual themed icons loaded, and the restored Home/wallpaper/fonts were checked in the live browser. Waze again produced 1024×600 native landscape content with actual menu input. The approved theme assets and core lifecycle-hook behavior are retained from beta23. The app adapter excludes the companion; shared process-identity helpers change native binary bytes, and CSS adds the gesture touch-action rule. Binary identity with beta23 is not claimed. The owner confirmed the Preferences button opens Safari; a dedicated phone pairing page now avoids presenting the empty unpaired dashboard. Actual Tesla connection still needs vehicle testing.

An earlier beta24 companion candidate passed a new Waze trial: automatic handoff to the companion, 65.02 seconds locked with the screen off, actual native menu open/close, and 166.14 seconds of browser observation with zero losses or portrait frames. Remembered reload reconnected without a code; reconnection while locked retained the credential and waited for unlock.

The final candidate passed two unlocked rapid-switch trials (leaving Calculator during selection, then selecting Waze): 58.00 and 72.69 seconds of Waze observation, with 231 and 290 samples respectively, no connection losses or portrait frames, and native menu input. Holding an old deselect reply, ending the controller, reconnecting with remembered pairing and selecting Calculator also passed: releasing the old reply left the new landscape session intact. Live-browser synthetic touch events navigated Home to Dashboard and back without launching the swiped icon; physical Tesla touch remains to be tested. These finite checks do not establish endurance or eliminate every intermittent app handoff failure; an earlier candidate's warm-switch failure is retained in the development evidence.

The preceding candidate also recovered from an intentionally terminated selected Calculator process into Waze without restarting the daemon. Recovery requires positive kernel evidence that the selected process ended, plus acknowledgment that its lifecycle lease ended; uncertain cleanup still reports unavailable. The final artifact retains this behavior and adds bounded handoff diagnostics. Host native/controller/browser regressions and package audits passed. Preservation checks found all 585 original host entries, the original DEB and 22 original device files unchanged.

Beta release artifact: `com.cfluid.cardash.v2_2.0.0~beta.24_iphoneos-arm64.deb` (27,763,716 bytes). SHA-256: `b9ae908f8caed432a93a74307bd5c50bdbea140e2fd4da23c59b0ab31a1e827a`. The extracted 52 files and 28 directories passed byte/mode, numeric root ownership, signature, dependency and V2-path isolation checks. This is a testing prerelease with the YouTube video and acceptance limits described above.

## Tesla test checklist

Test while parked first. Report phone model/iOS/jailbreak, app/version, Tesla software/browser version and exact action that failed. Do not share pairing codes or private app contents in a public issue.

- Initial page access over the real hotspot, eight-digit pairing and app selection.
- Landscape sizing and touch at each screen edge in the Tesla viewport.
- Waze search, navigation prompts and moving-location behavior when appropriate; stationary map/menu operation is the only recorded navigation evidence.
- YouTube Music Now Playing/playback and keyboard behavior in chosen apps. The tested older YouTube Music version shows an unsupported-version banner but its Now Playing playback worked.
- Lock, lift/wake and physical rotation after selecting an app; keep the dashboard landscape.
- Hotspot off/on, browser hide/reload, session expiry and remembered reconnection after unlock; verify Forget requires a new setup code.
- Longer sessions, battery use, heat, latency, memory pressure, calls and other interruptions.

Actual Tesla/hotspot end-to-end behavior, long-duration thermal/battery performance, all-app compatibility, DRM/secure surfaces, complex IME input and exact iOS 27 visual parity remain unverified.

## Recovery and removal

If setup does not open, confirm the jailbreak is active, dependencies are installed, then reinstall this V2 DEB and respring/unlock. If a session becomes unavailable, End it, unlock, and use Reconnect (or pair if this browser was not remembered); reopening the selected app may be necessary. A fresh app process is required after its injected library changes.

Remove **CarDash V2 Beta** only through the package manager, then respring to unload its hooks from existing processes. Removal stops only the V2 service and unregisters only its companion app. It preserves both original CarDash state and V2 preferences; it does not uninstall CarDash 1.x. The V2 network alias may remain until reboot. Re-jailbreak after a reboot before using V2 again.

The release contains no SSH password, controller credential, device log, Canary binary, Immortalizer code or unrelated firmware files. Map/search providers may receive map/search requests when those dashboard features are used; selected-app activity follows each app's own network behavior.
