# Diagnostic package plan

Spec: DESIGN.md. Execution uses the existing executing-plans/TDD workflow; the user delegated judgment and requested completion without an additional approval loop.

## Constraints
- Isolated research source/package/runtime IDs; no product/original state changes.
- Start only from a user Run action, finite workers, exact ABI checks, one combined log.
- No synthetic/native-success conflation. No private identity copied. No device install.

## Review focus
- Disconnect/cancel/timeout/crash cannot leave workers or active request clients indefinitely.
- Partial IPC, unauthorized peers, log/path bounds, and package ownership must fail closed.
- A callback/socket/display alone cannot be reported as a live native CarPlay session.
- Export remains usable if the helper or a stage fails.

## Task 1 — Runner and native probe
- [x] Write failing real host integration tests and ABI/conclusion tests.
- [x] Implement bounded logging, peer-checked control service, worker supervision and guarded native probes.
- [x] Run the complete host suite and commit.

## Task 2 — App, rootless package, review
- [x] Add Run/Cancel/Share app with failure export; build device and simulator variants.
- [x] Build rootless DEB, inspect extracted payload, signatures, paths, scripts and plist; verify with REA.
- [x] Run simulator smoke where possible and full local checks.
- [x] Fresh independent review; fix important findings with regressions. Verify originals and deliver DEB/report/instructions.
