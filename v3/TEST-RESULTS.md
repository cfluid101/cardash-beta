# CarDash V3 beta 2 — validation

Test device: iPhone 8 Plus (`iPhone10,2`), iOS 16.6 build 20G75, Dopamine rootless. The receiver runs on the phone. The Mac forwards HTTP only; it does not receive/decrypt native CarPlay or host the native session.

## Physical-device results

- Native authentication, activation, H.264 video, HID input and actual music audio work together. Audio negotiated `type100/media`, 44.1 kHz stereo PCM, with nonzero decoded samples and no authenticated-packet rejects in the measured trials. The browser AudioContext ran and produced nonzero analyser output. The user independently confirmed clear music from the Mac speakers.
- After removing V2/Canary, CarPlay Diagnostics and CarPlay Loopback, restarting the affected processes and respringing, a **105.68-second continuously locked trial passed**. Immortalizer's injection files were temporarily isolated for this test. Waze → YouTube Music → pause → resume → Waze → YouTube Music all worked through native input. Screenshots confirmed the app and control changes; independent MediaRemote observations confirmed playing=1, then 0, then 1 on the CarAudio route. The browser finished with 4,086 decoded frames, one video connection, zero video errors and one audio connection. It recorded no audio sequence gaps, one scheduling drop and three underruns across the deliberate pause/resume sequence.
- A separate wake test observed the display turn on while lock state remained locked, then verified another 30.09 seconds of continuous audio/video. It ended with 5,424 decoded frames, one video connection, no video errors and no audio sequence gaps.
- The final corrected session reached **420 seconds (seven minutes)** with 11,841 decoded browser frames, one video connection, zero video errors and one audio connection. Browser audio processed 17,038,230 sample frames, with no sequence gaps. Its one scheduling drop and three underruns came from the earlier deliberate pause/resume sequence; neither count grew during continued playback. The phone remained locked through the final endurance observation.
- A prior 106.11-second locked trial also passed before old test-hook removal. That result alone was not used to claim independence from those hooks.
- Closing the browser without pressing Stop ended the native session in 16.46 seconds, including cancellation. A fresh browser then authenticated and activated a new native session, displayed YouTube Music and played audio while the phone remained locked. The old session's input was rejected. Separate stale-session video/audio/touch/stop/heartbeat requests also returned errors without disrupting the active session. Playback was explicitly paused before cleanup.
- Independent synthetic AAC-LC 44.1/48 kHz stereo vectors decoded on the physical phone to 12,288/13,312 frames, RMS 1933.26/1930.58 respectively. Native AAC negotiation has not been observed; actual music trials used PCM.
- The kernel readback confirmed the receiver's own active/inactive memory limits at 128 MB. This is a configured limit, not a measured guarantee of long-term memory use.

## Fixes verified during acceptance

The five-minute product deadline is removed. Browser-disconnect cleanup, parent-death/EOF handling, a renewable native-process lease and bounded queues remain. Sessions are not kept alive after an abandoned browser indefinitely.

The original audio failure was iOS rejecting the incomplete duplex format table with `APCarPlayAudioFormatsCreate kParamErr(-6705)` for 100/telephony. Supplying the required 16/24 kHz mono input declarations enabled media audio. No microphone capture is implemented; requested input transport sends authenticated silence and is explicitly labelled unsupported for voice input.

An earlier endurance run reached 409 seconds without a video error but later exposed an asynchronous SourceBuffer trim race. The busy-buffer guard now has a regression test. Clean-runtime testing then exposed a buffered-native-frame burst overflowing a healthy HTTP viewer queue. The parser now processes bounded batches and lets the writer drain. A 220-frame encrypted burst regression fails against the prior implementation and passes with the correction. These earlier failed runs are not presented as final acceptance passes.

Audio overflow discards oldest records within a 64-record/256 KiB bound, preserving per-lane reset markers. It does not force a reconnect for a transient burst. Blocked network writers still time out. Browser scheduling is bounded to 0.5 seconds. Reconnect tests cover quiet EOF, failed headers, stale generations, old callbacks and queued touches. Real-device browser Mute/Unmute checks preserve the native session.

## Local checks and preservation

- **47 Python tests, 13 focused browser tests, 21 reference receiver JavaScript tests and one cross-process launcher test pass (82 total).** They cover authentication/framing, malformed audio, replay rejection, AAC decoding, queue bounds, decoder lifecycle, asynchronous viewer cleanup and package isolation. The real Chrome gesture check also passed without an autoplay-policy bypass using synthetic audio; physical audio trials used the browser Start gesture.
- The original project has 585 unchanged entries and its original DEB is unchanged. The 203-file update-product baseline is unchanged. All 22 original installed payload/preference hashes match.
- Current V2 preferences are preserved byte-for-byte across its uninstall. They differed from a much earlier baseline before this cleanup, so that older file was not restored over the user's current settings.
- Raw device logs, screenshots, identity material and audio fixtures remain private. The package and corresponding source contain no Apple binaries, upstream APK, accessory private key, paired identity, SSH key or captured media.

## Remaining vehicle and compatibility checks

Tesla's actual browser and speaker routing, Personal Hotspot interruption/recovery, USB-free operation, navigation voice prompts mixed with music, and long-duration thermal/battery behavior require testing in the car. A minutes-long Mac-browser trial does not establish those results. Source resolution is fixed 1280×720 landscape; adaptive source resolution is not implemented. Microphone/Siri/call input is unsupported. Other phone models/iOS builds are unverified and rejected by the installer.

CarBridge and Immortalizer were preexisting third-party packages. Full-app interfaces shown during these trials use CarBridge; this release does not replace or bundle it. Results without CarBridge must not be inferred. The clean locked trial ran without Immortalizer injection; its files are restored after testing. YouTube Music's installed old version shows an unsupported-version message, while its existing Now Playing playback remains usable on this device.

## Release artifacts

The downloadable DEB is built from the tagged source commit. Its manifest records that commit and hashes every payload file. The matching source archive includes `SOURCE-COMMIT.txt`; the published checksum file names the actual GitHub assets. Release assembly compares executable/backend/web payload hashes against the physical-device candidate so documentation/provenance changes cannot silently replace tested runtime code.
