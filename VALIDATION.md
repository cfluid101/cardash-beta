# Diagnostic 0.1.3 validation

Target: iPhone 8 Plus (`iPhone10,2`), iOS 16.6 (`20G75`), Dopamine rootless. The phone is connected over USB/SSH. Version 0.1.2 completed 12 workers on device and exposed the entitlement and publicKey-type failures. Corrected 0.1.3 completed ten workers in 88.48 seconds. Both entitled string-key and no-key profiles returned native success, reached the loopback receiver and sent POST /pair-setup. The intentional 501 response stopped pairing; no new session/display was observed.

## Local checks

- 35 automated integration/package tests passed. They exercise real NSXPC errors and successful replies; preservation of original error/interruption/invalidation handlers; asynchronous versus synchronous proxy semantics; plain and one-way requests; unrelated-client isolation; replacement connections and concurrent errors; bounded nested NSError/Unicode data; class/implementation-owner guards; partial instrumentation failure/retry; bounded inherited protocol metadata; and concurrent handler setup/lifecycle observation.
- A parallel-writer regression reproduces corrupt NDJSON without serialization and passes after the output mutex fix. A handler-getter failure regression reproduces falsely complete coverage before the observer fix. Package regressions exposed and corrected an unhashed README and a differing codesign identifier in the comparison worker.
- Existing integration tests cover repeat runs, single-controller behavior, cancellation, hangs, crashes, output bounds, hardlinks, directory replacement, parent-death cleanup of workers/descendants, pre-request cancellation, slow control clients, real sandbox socket denial, missing sockets, signed app confinement and STATUS-only installation preflight.
- Eleven ABI/ownership/result-classification checks plus bounded Mach-O parsing/identity-gate tests. The parser also decoded the actual retained caller UUID and verified its SHA-256.
- ARM64 iOS 16.6 builds use warnings as errors and strict ad-hoc signature verification. The app and both helper executables are checked. The comparison executable has identical `__TEXT` sections and signing Identifier, with exactly the additional sessionRequest entitlement. It has no independent launch job.
- Rootless archive inspection checks paths, permissions, signatures, scripts and integrity hashes for every payload file except the manifest itself. Host/simulator-only control strings are absent from device binaries.
- UIKit simulator Run/Share creates a combined report with a terminal record. A failed second run exports current supporting logs and excludes the old report. These checks use synthetic workers, not native CarPlay. Only the separately owned research simulator was booted; it was shut down afterward.
- Independent source reviews covered the observer and its integration, callback identity gates, stage budgets, isolated entitlement experiment and retained-binary conclusions. The reported handler-coverage issue was corrected and regression-tested. Objective-C decompiler limitations remain explicit in TRACE-FINDINGS.md.
- Original project: 585 baseline entries unchanged. Original DEB unchanged. Update-product baseline: 203 files unchanged. Existing beta.25 release DEB SHA-256 unchanged (`72cc51617d9544e0f36b4a369c5f65819e60c5717a62c551e235cba99f548161`).

The final release manifest records the committed source revision and exact payload/DEB hashes. The published DEB is downloaded again and compared to its local digest. Rebuilding can change signing/archive bytes; always use the checksum supplied with the corresponding download.

## Repeating the device trial

Fully close an older diagnostic app, install 0.1.3, disconnect real CarPlay receivers, then run CarPlay Diagnostics while unlocked. Allow two to three minutes and share the single log. No USB connection, SSH setup, respring or reinstallation between repeat trials is required by the diagnostic itself.

The recorded device established signature trust/activation, matching framework identities, actual service/protocol/error records, effective comparison entitlement, all four profile outcomes, and cleanup. It remained unlocked, with no session left active. The two unentitled before/after controls still produced explicit entitlement rejection; neither reached transport. All 23 original/V2 pre-trial file hashes matched afterward. Other devices must repeat those checks. A failed ABI/identity gate is reported; typed callback arguments remain disabled for an unknown image pair. An existing session or stage/cleanup failure withholds later attempts.

This is a session-start diagnostic. Authentication, a complete receiver, video decoding, native app switching and Tesla output are not implemented. A recorded callback, socket or session is not a verified working display. Missing transport cannot by itself identify MFi as the blocker. Local testing does not guarantee the first physical-device result or rule out a device-specific correction.

The manifest is generated before physical testing and conservatively records device_tested=false at build time. The separate release-validation.json and device-trace report describe post-build device results and tested executable digests. Full raw USB logs remain in the local research folder; public release notes use only selected nonpersonal findings.
