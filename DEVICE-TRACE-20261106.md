# Connected iOS16.6 CarKit trace — 2026-11-06

Diagnostics0.1.2 was installed through the existing USB SSH connection. All9 installed payload hashes matched the published artifact. The iPhone10,2 reported20G75 and remained unlocked. Original CarDash/V2 binaries and preferences were not installation targets; all23 pre-trial file hashes still match after the run. The original CarDash daemon was already stopped before this trial and was left in that pre-existing state.

The suite completed12 workers in128.17seconds, with no worker failures, cancellation or remaining CarPlay session. A USB syslog capture ran concurrently; a combined report preserves both sources. Nothing was uploaded automatically.

Confirmed findings:

1. The device launchd plist assigns `com.apple.carkit.sessionRequestHandler` to mediaserverd, PID378 in this run. The loaded CarKit UUID and retained carkitd SHA/UUID exactly matched the guarded identity tuple.
2. Actual remote protocol metadata says `service_startSessionWithHost:reply:` receives a CARSessionRequestHost and `void (^)(BOOL,NSError *)` reply. The main-queue liveness marker ran.
3. All five unentitled before/after/control requests produced NSCocoaErrorDomain4097. Matching mediaserverd records explicitly reject each PID for missing `com.apple.private.carkit.sessionRequest`.
4. The separately entitled worker PID27986 was accepted. It then failed secure decoding because the diagnostic publicKey was NSData. The exception explicitly lists NSString as the allowed class. This proves a diagnostic payload defect beyond the permission gate.
5. No profile reached the loopback receiver or produced a native completion/new session. Cancellation returned and mediaserverd/carkitd remained running.

Correction under test: NSString hexadecimal encoding of the32-byte public test key, a full observed host initializer with synthetic display/device identity, a strict type guard and secure-coding/readback preflight. Default profiles now compare unentitled baseline, entitled string-key, entitled nil-key and baseline repeat. No authentication, video receiver or global authorization modification is introduced.

Local regression: the Mac secure decoder tolerated the malformed NSData field, unlike device XPC. The explicit field-type guard now rejects it before archiving; string and nil fixtures pass. This avoids treating a permissive host archive test as proof of iOS wire compatibility.
