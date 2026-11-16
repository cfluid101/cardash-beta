# CarDash V3 Beta 7 — shrunk browser, hidden delay, steadier bitrate

Package `3.0.0~beta.7`, November 16, 2026. Built from the owner's first beta 6 drive (November 15, 2026: 46 minutes, three sessions, iPhone 8 Plus / iOS 16.6 / 20G75).

**Not yet run on a phone or in a car.** Every change is covered by host tests only. Keep the beta 6 DEB for rollback. Installing restarts the media service.

## What the beta 6 drive showed

- **No service stalls.** The helper's lines were read at most 1.3 seconds late (99% within 0.3 s); the 13–46 second stalls of the earlier log did not occur, so their cause is still unknown. The phone had been rebooted about an hour earlier.
- **A healthy link carries the stream.** The first session ran 12.5 minutes at 29.5–30 fps, 15–20 ms frame age and 25–110 ms round trips with no real congestion.
- **Both long disconnects were the Tesla suspending a shrunk browser.** At 02:36:47 and 02:47:42 UTC the page stopped reading video and sending anything at the same instant. When it returned its error counters had not moved, which a network outage would have advanced: no script ran. The phone ended CarPlay after 90 seconds of silence both times. The second time Viewer 3 restarted it within a second of returning (picture back after 10 s); the first time the Tesla had reloaded the page, which needed Connect and Start by hand.
- **The restart is what moves audio to CarPlay.** In 12 of the 18 sessions across both logs that got as far as negotiating audio, iOS took the audio channel about 2 seconds after the session started and sent media to the CarPlay output, where Device output mode discards it. In the other 6 it never did. The log cannot show whether music was playing at those starts; that it was is the reading that fits both the pattern and the owner's account. Both restarts on this drive did it, and it lasted until the route was changed by hand on the phone (10 and 19 seconds).
- **Pictures arrived seconds late with nothing queued.** 4.5 and 8.6 seconds of delay were reported while this service had an empty queue, after the browser had painted nothing for 4.9 seconds. The video was waiting where this service cannot see it: the phone's TCP send buffer (which iOS grows to megabytes), the Tesla's receive buffers, or the browser itself. The log cannot say how much was in each.
- **Bitrate cuts did not bind.** In the third session the link congested at about 1.3–1.6 Mbps of real throughput while the budget was 2.1–3.0 Mbps. A 35% budget cut left the encoder where it was, so the congestion returned: 18 cuts in 20 minutes. Two more cuts, in the first seconds of two sessions, were false: the "lag" was a viewer waiting for its first keyframe on a still screen.
- **The newest frame was always held back.** A frame was sent only when the next one arrived, and iOS sends nothing while the screen is still (up to 17 s in this log), so the last frame of every change waited for the next change.
- One earlier session (beta 5, November 15) ended after 8 seconds with `video_error: next timestamp`.

## Changes

**Shrinking the browser no longer ends CarPlay**

- A browser that has shown CarPlay may be silent for 15 minutes (was 90 seconds). The native session, pairing and phone audio route stay as they are, so there is no restart and nothing for iOS to re-route. Enlarging the browser reattaches video to the same session.
- Viewer 4 remembers the address of the phone it last reached (never the token). A page the Tesla reloaded reconnects by itself and rejoins the running session without Connect or Start. If the browser refuses a local request without a tap, the Connect button works as before.
- The phone app says when no browser is attached and how long CarPlay will wait; Stop ends it at once.

**Less delay**

- The video connection's send buffer on the phone is 64 KB instead of megabytes. A slow link or a stalled browser now backs up into this service's queue within a fraction of a second, where it is measured and can be skipped, instead of becoming seconds of delay that must all be played through. Buffers on the Tesla's side are outside its reach.
- The newest frame is sent 40 ms after it arrives if no other frame follows (canvas viewers only; a MediaSource viewer keeps exact durations). On a still screen the last frame of a change is no longer held.
- The viewer queue is 60 frames (was 90), so a stream that cannot catch up skips to the next keyframe after about 2 seconds instead of 3.

**Bitrate that settles**

- A cut is 20% below what is actually being sent, not 35% below the budget.
- The rate that congested is remembered: the budget returns to 90% of it, holds for 2 minutes, then probes. A probe that fails within 90 seconds doubles the next hold (up to 10 minutes). A simulated link that congests above 1.6 Mbps produces 6 cuts in 30 minutes; the drive averaged 18 in 20.
- Late pictures are not counted for a still stream, for 8 seconds after a viewer joins or resynchronizes, or while no viewer is attached. A queue of 20 or more frames counts as unsent video even when the frames are small.

**Other**

- A native frame whose time does not advance shifts the timeline instead of ending the session.
- `video_budget` records the remembered rate and hold; status reports viewers and browser silence.

## Not fixed: audio at Start while music is playing

Keeping the session alive removes the restart that triggered it on this drive. Pressing Start while music is already playing will still send that music to the CarPlay output until the route is changed on the phone. The media-service adapter reports that it is holding the phone route when this happens, so the fix is inside iOS audio routing or the CarPlay audio negotiation, and neither can be changed responsibly without the phone attached to test it. Until then: start CarPlay before starting music, or pause before pressing Start.

## Also not addressed

- The stalls from the first log (cause unknown; `service_stall` will record the next one).
- Heartbeat, status and touch still use one HTTP request each; pair-setup still runs on every start.
- The stream is 1088×846 for a 773×601 browser window. If the Tesla draws one screen pixel per page pixel, about half the encoded pixels are discarded on arrival; a smaller native size would be sharper per bit. This changes the CarPlay layout negotiation and needs a device.

## Verification

256 V3 Python, native-harness and package tests and 110 viewer JavaScript tests pass on the build host, including new cases for the 15-minute wait, last-frame flush, timestamp shift, send-buffer size on a real socket, the reworked bitrate rules and viewer auto-reconnect. Backend sources compile under Python 3.9. No device test.
