# CarDash V3 Beta 6 — stall and link-blip recovery

Package `3.0.0~beta.6`, November 15, 2026. Built from the owner's diagnostic export covering November 7–14, 2026 (15 sessions on iPhone 8 Plus / iOS 16.6 / 20G75).

**Not yet run on a phone or in a car.** Every change below is covered by host tests; none has been exercised on a device. Keep the previous DEB for rollback. Installing restarts the media service, as every V3 package does.

## What the log showed

Steady-state streaming was good (median frame age 31 ms, about 29 fps). The problems were episodes:

- 13 of 15 sessions ended with `browser_timeout`, which then needed a manual Start. The limit was 12 seconds without a heartbeat.
- The service itself stopped running for 13–46 seconds at a time. The session helper kept emitting one line a second while the backend logged them up to 46 seconds late. During those stalls no heartbeat was processed (so the browser looked silent), the helper's parent lease expired (three sessions), and the 8-second encoder lease lapsed.
- When the encoder lease lapsed the encoder left its budget: 13.1 Mbps measured against a 750 kbps budget. That overflowed the viewer queue, the viewer was dropped, and its rejoin restarted the encoder again.
- 45 of 51 bitrate cuts happened with nothing waiting to be sent, and 40 while the stream used under 80% of its budget. 43% of samples ran below 1.5 Mbps at 1088×846.
- Each of 7 viewer drops cost 2–2.5 seconds to reconnect, and the browser's limit of three reconnects a minute then froze the display.

**The cause of the stalls is not identified.** The helper slowed at the same times, pair-setup took seconds instead of a fraction of one, and on November 9 the media service restarted, which points at the whole phone being starved of CPU or memory rather than at one blocking call. Beta 6 tolerates the stalls and records what is needed to find the cause.

## Changes

**Sessions survive silence and stalls**

- A browser that has shown CarPlay may be silent for 90 seconds (was 12) before its native session ends. The session, pairing and audio continue; the browser reattaches to the same session.
- Any authenticated request for the session counts as presence: heartbeat, touch, status poll and video the browser accepted.
- Time the service did not run is measured and is not counted as browser silence or against native startup. Each stall is logged as `service_stall` with its duration, the CPU time this process used during it, and peak memory. CPU time near the duration means this process was busy; near zero means it was not scheduled or was blocked in the kernel.
- Lease renewal and the helper heartbeat run every second in a task that never awaits a command or teardown.
- Native leases last 30 seconds (were 8) and the helper's parent lease 60 seconds (was 15). A backend that exits is still detected immediately by PID and by the closed pipe; the longer leases only cover a backend that is alive but not running.
- Viewer 3 restarts a session that ended on its own (lost contact or a native disconnect) once the phone is reachable again: at most twice in five minutes, never after Stop, never while the page is hidden.

**Bitrate follows congestion, not request latency**

- The budget is cut 35% when pictures are late (stream lag over 700 ms) or more than 192 KB of video is waiting to be sent.
- A slow heartbeat alone cuts 15%, and only after two in a row while the stream is using at least 60% of its budget.
- One cut per congestion event (four seconds apart) instead of one per report.
- Recovery returns to 70% of the pre-event rate in 20% steps after six healthy seconds, then probes at 150 kbps per 12 seconds. Beta 5 took about five minutes to return from the floor.
- Every change is logged as `video_budget` with its reason and inputs.

**A full viewer queue no longer closes the stream**

- For the canvas renderer the unsent video is discarded and the same response resumes at the next keyframe (`video_viewer_resync`). The initialization segment is not repeated, which the browser parser would reject.
- The keyframe is requested when the socket can carry it, at most every 5 seconds; a fifth overflow within a minute falls back to closing.
- A viewer that joins while a requested keyframe is still pending shares it instead of restarting the encoder again.
- The video write deadline is 10 seconds (was 3), so a short blip no longer ends the response.

**Other phones**

- The transport error now says what can help. For an unsupported iOS build it names the build and says reinstalling will not change it; a missing hook library, an adapter that never loaded, and a failed safety check each get their own instruction. The phone app and the browser page show it before Start is pressed.
- The hook library is looked up in four rootless locations and among already-loaded images, not one hard-coded path.
- The installer no longer fails when `launchctl` rejects the media-service target, and it verifies by PID that the media service actually restarted, ending the old process when it did not.

**Not changed: which iOS builds work.** The adapter still patches only the two exact builds it has profiles for (20G75; 20A357 arm64e, unverified on a device). Hooking private functions located by pattern on firmware nobody has analysed could crash the media service on testers' phones, so no identity, instruction or layout check was relaxed. Adding a build still needs that build's diagnostic export.

## Not addressed

- Heartbeat, status and touch still use one HTTP request each; a persistent connection would cut latency further.
- Pair-setup still runs on every start.
- Teardown that reports the CarPlay session still present was not changed; the sample was too small to justify a delay.
- The November 9 media-service restart: check that crash report on the phone.

## Verification

241 V3 Python, native-harness and package tests and 104 V3 JavaScript tests pass on the build host, including 27 new stall/resync/keepalive cases, 8 new viewer auto-resume cases, the rewritten bitrate cases and the hook-provider harness. The package audit ran against the built DEB (both adapter slices, signatures, rootless paths). Backend sources compile under Python 3.9, the version on the phone.

Still needed on a device: a drive with Viewer 3, a deliberate hotspot dropout of 20–60 seconds, and an export afterwards to read `service_stall`, `video_budget` and `video_viewer_resync`.
