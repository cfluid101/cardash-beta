# Connected iOS 16.6 CarKit trace — 2026-11-06

Diagnostics 0.1.2 was installed through the existing USB SSH connection. All 9 installed payload hashes matched the published artifact. The iPhone10,2 reported 20G75 and remained unlocked. Original CarDash/V2 binaries and preferences were not installation targets; all 23 pre-trial file hashes still match after the run. The original CarDash daemon was already stopped before this trial and was left in that pre-existing state.

The suite completed 12 workers in 128.17 seconds, with no worker failures, cancellation or remaining CarPlay session. A USB syslog capture ran concurrently; a combined report preserves both sources. Nothing was uploaded automatically.

Confirmed findings:

1. The device launchd plist assigns `com.apple.carkit.sessionRequestHandler` to mediaserverd, PID 378 in this run. The loaded CarKit UUID and retained carkitd SHA/UUID exactly matched the guarded identity tuple.
2. Actual remote protocol metadata says `service_startSessionWithHost:reply:` receives a CARSessionRequestHost and `void (^)(BOOL,NSError *)` reply. The main-queue liveness marker ran.
3. All five unentitled before/after/control requests produced NSCocoaErrorDomain 4097. Matching mediaserverd records explicitly reject each PID for missing `com.apple.private.carkit.sessionRequest`.
4. The separately entitled worker PID 27986 was accepted. It then failed secure decoding because the diagnostic publicKey was NSData. The exception explicitly lists NSString as the allowed class. This proves a diagnostic payload defect beyond the permission gate.
5. No profile reached the loopback receiver or produced a native completion/new session. Cancellation returned and mediaserverd/carkitd remained running.

Correction tested: NSString hexadecimal encoding of the 32-byte public test key, a full observed host initializer with synthetic display/device identity, a strict type guard and secure-coding/readback preflight. Default profiles now compare unentitled baseline, entitled string-key, entitled nil-key and baseline repeat. No authentication, video receiver or global authorization modification is introduced.

Local regression: the Mac secure decoder tolerated the malformed NSData field, unlike device XPC. The explicit field-type guard now rejects it before archiving; string and nil fixtures pass. This avoids treating a permissive host archive test as proof of iOS wire compatibility.

## Corrected 0.1.3 result

The published-code candidate at commit `f9e6989` was installed and all nine payload hashes verified. Its suite completed ten workers in 88.48 seconds with no worker failure or cancellation. Actual CarKit secure archive/unarchive readback passed in every request profile.

| Profile | Native callback | Loopback transport | Result |
|---|---|---|---|
| Unentitled baseline | none | no | 4097 plus explicit entitlement rejection |
| Entitled string key | success=true, no NSError | yes | POST /pair-setup; diagnostic answered 501 |
| Entitled nil key | success=true, no NSError | yes | POST /pair-setup; diagnostic answered 501 |
| Unentitled repeat | none | no | same entitlement rejection |

For the two entitled attempts, the XPC observer recorded zero proxy errors or interruptions. Corresponding mediaserverd/CoreUtils logs report `Control pair-setup CU failed` with error `200501 / Not Implemented`, matching the receiver's deliberate response. The permission and serialization barriers are resolved for native request acceptance. Pairing/authentication is the next unimplemented boundary; this result does not prove a complete CarPlay receiver, video stream, MFi independence or locked-app switching.

All post-cleanup session observations were absent. mediaserverd PID 378 and carkitd PID 482 stayed running. The phone was unlocked with its display on after testing, and the existing V2 companion was foreground to keep it awake. All 23 pre-trial original/V2 file hashes matched afterward; the pre-existing stopped original daemon state was preserved.

Raw combined logs (native diagnostic plus USB service log) remain under `evidence/device-0.1.2-20261106-ssh/run-223045/` and `run-223653/`. They are intentionally not uploaded as release assets because system logs may contain unrelated private metadata. Public findings here contain only scoped technical results.
