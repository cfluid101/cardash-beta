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
