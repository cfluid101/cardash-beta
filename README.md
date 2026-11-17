# Viewer 5 — November 16, 2026

[Open Viewer 5](https://cfluid101.github.io/cardash-beta/option1/?v=https3&ui=5) · [Beta 9 release notes](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.9) · [Download the Beta 9 DEB](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.9/com.cfluid.cardash.v3_3.0.0~beta.9_iphoneos-arm64.deb)

The controls header says **Viewer 5**. The welcome panel links to the compatibility beta and explains how to export a failed-start report. Connection, video, touch, audio, remembered-phone and recovery behavior are unchanged from Viewer 4. Viewer 5 remains usable with existing Beta 7 and Beta 8 packages; updating the web page does not add firmware support to an installed package.

Beta 9 adds exact firmware profiles and more specific compatibility diagnostics. Firmware inspection and host tests do not establish physical-device success or blanket iOS 15–17 support. Read the release notes for the supported profiles, installation requirements and remaining limits. No physical phone or car trial is claimed for this viewer update.

**Earlier URLs are preserved:** `?v=https3&ui=4`, URLs without `ui=5`, and cached pages use the original immutable Viewer 4 client. Only `ui=5` selects Viewer 5. The shared transport, audio and canvas scripts are unchanged. All previous assets remain available. Script digests, routing and the unchanged behavior's source commit are recorded in [viewer-version.json](option1/viewer-version.json); the previous manifest is retained in [viewer4-version.json](option1/viewer4-version.json).

Validation: **110 existing viewer tests and 7 routing/integrity tests pass** against the candidate assets. The existing suite uses only the updated Viewer 5 label expectations. All 12 prior immutable assets remain byte-for-byte unchanged. Run `node --test tests/viewer-routing.test.mjs` for routing, asset hashes and CSP checks.

# Viewer 4 — November 16, 2026

**Beta 7 package:** https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.7 (pre-release; not yet run on a phone or in a car).

Refresh https://cfluid101.github.io/cardash-beta/option1/?v=https3&ui=4 to load it. The controls header says Viewer 4. It works with the packages already installed.

- The page remembers the address of the phone it last reached, in this browser only and never the token. When the Tesla reloads the page, which it does after the browser has been shrunk for a few minutes, the page reconnects by itself and rejoins a session that is still running, without Connect or Start. If the browser refuses a local request made without a tap, the page says to press Connect and the button works as before.
- Everything else is unchanged from Viewer 3.

The beta 7 package is what keeps the session running: a browser that has shown CarPlay may be silent for 15 minutes (was 90 seconds), because the Tesla suspends a shrunk browser completely. It also limits the phone's video send buffer to 64 KB, sends the newest frame 40 ms after it arrives instead of holding it for the next one, and cuts bitrate from the rate actually being sent while remembering the rate that congested. Pressing Start while music is already playing can still move that music to the CarPlay output; that is not fixed. Details and the log evidence behind each change: [BETA-7.md](https://github.com/cfluid101/cardash-beta/blob/6853363594803a3c4c62ae69e226ea82bbf86cd2/v3/BETA-7.md).

131 JavaScript tests pass (110 viewer, 21 reference receiver). **Neither Viewer 4 nor the beta 7 package has been run on a phone or in a car yet.** Script digests and the source commit are in option1/viewer-version.json. Earlier immutable script versions remain available for cached pages and rollback.

# Viewer 3 — November 15, 2026

**Beta 6 package:** https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.6 (pre-release; not yet run on a phone or in a car).

Refresh https://cfluid101.github.io/cardash-beta/option1/?v=https3&ui=3 to load it. The controls header says Viewer 3; enter the same iPhone address as before. It works with the packages already installed.

- A phone whose iOS build is not supported now says so on the page before Start is pressed, with what can and cannot help, instead of failing after Start.
- With package `3.0.0~beta.6` or later, a session that ended on its own (the phone lost contact with the browser, or its native connection dropped) restarts itself when the phone is reachable again: at most twice in five minutes, never after Stop, never while the page is hidden. Earlier packages do not report why a session ended, so nothing changes for them.

The beta 6 package keeps a session alive through 90 seconds of browser silence (was 12), keeps the encoder inside its bandwidth budget while the phone service is stalled, cuts bitrate on late pictures or unsent video rather than on one slow request, and resumes an overflowing stream at the next keyframe without reconnecting. It changes nothing about which iOS builds are supported. Details and the log evidence behind each change: [BETA-6.md](https://github.com/cfluid101/cardash-beta/blob/fee4a90bebcda36a432346764759b6cf6aee1148/v3/BETA-6.md).

125 JavaScript tests pass (104 viewer, 21 reference receiver). **Neither Viewer 3 nor the beta 6 package has been run on a phone or in a car yet.** Script digests and the source commit are in option1/viewer-version.json. Earlier immutable script versions remain available for cached pages and rollback.

# Viewer 2 — November 14, 2026

Refresh https://cfluid101.github.io/cardash-beta/option1/?v=https3&ui=2 to load the updated controls. No DEB reinstall is required for this hosted-page update. The controls header says Viewer 2; enter the same iPhone address as before.

- The small left-edge arrow sits below the native time/signal area and opens the overlay controls.
- Start negotiates native geometry once. Shrinking or expanding the browser only scales the existing image proportionally and sends no native resize/restart.
- Use **Resize display** to apply a different native layout explicitly. This operation briefly restarts the native display/audio. Changing audio output preserves accepted native dimensions.

117 JavaScript tests pass. Desktop Chrome fixture checks cover small connection panels, four browser sizes, uninterrupted simulated session/stream identity, touch alignment, overlay behavior, and explicit resize. These are not a fresh physical Tesla/iPhone trial. A browser unload or actual network failure still uses the existing session timeout/recovery rules.

Source and detailed test scope: [viewer update](https://github.com/cfluid101/cardash-beta/blob/d679adfca830ea87d09fa8ad733bfcea2b4abc17/v3/VIEWER-UPDATE-2026-11-14.md). Script digests and source commit are in option1/viewer-version.json. Existing immutable script versions remain available for cached pages and rollback.

# CarDash HTTPS3 tester frontend

https://cfluid101.github.io/cardash-beta/option1/?v=https3

Use with the matching 3.0.0~beta.5+https.3 package. This candidate reduces native
encoder bandwidth on congested links, keeps canvas sessions from restarting
the encoder periodically, and resumes display recovery after its cooldown.
Device output leaves speaker/Bluetooth routing to the iPhone. Browser audio
remains optional. The project owner reported the November 7, 2026 trial in a 2023 Model 3 (AMD Ryzen) was working nearly perfectly. Broader tester coverage and long-drive endurance remain ongoing.

Only static interface files are hosted here. All video, input, optional audio,
controller credentials and diagnostics travel directly between the browser and
local iPhone. There is no cloud media relay or diagnostic upload. Previous
immutable scripts are retained for cached pages. See LICENSE.

Previous package and setup: https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3
