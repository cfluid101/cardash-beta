# Viewer 3 — November 15, 2026

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

Download and setup: https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3
