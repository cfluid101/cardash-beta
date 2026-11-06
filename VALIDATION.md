# Diagnostic 0.1.1 validation

This package targets the recorded iPhone 8 Plus (`iPhone10,2`) on iOS 16.6 (`20G75`) with Dopamine rootless. It has not been installed or tested on a physical phone during this development pass.

## Completed locally

- 19 automated Python integration/package tests: repeat runs and one-controller behavior; cancellation; hangs; crashes; bounded noisy output; hardlink rejection; installation preparation; directory replacement; parent-death cleanup of workers and descendants; cancellation before native startup; total timeout for incomplete control input; a real sandbox-enforced socket denial; missing-socket diagnosis; signed app confinement settings; status-only installer preflight; rootless payload isolation; manifest/signature checks; shell/package metadata.
- 11 ABI, implementation-owner and result-classification checks.
- UIKit simulator Run and Share handlers produce one combined diagnostic log with a terminal record. A failed second run exports current supporting logs and excludes the previous worker report. These use synthetic workers, not native iOS CarPlay.
- Warnings-as-errors builds and strict ad-hoc signature checks for ARM64 iOS 16.6 targets. Package archives independently extracted with macOS ar/tar. Host/simulator-only switches are absent from the device binaries.
- The 0.1.0 base received independent source review; four Important findings were fixed with failing-then-passing regressions. No unresolved Critical or Important findings from that review. The 0.1.1 IPC correction adds four regressions and was checked locally; it has not received a fresh independent reviewer pass.
- Original project (585 entries), original DEB, update-product baseline (203 files), and beta.25 release DEB hashes preserved.

The release manifest records the exact source commit and final payload/DEB hashes. REA evidence and a release-validation report accompany the final local artifacts. Rebuilding can change signatures/archive bytes; verify the downloaded file against its matching SHA-256 file.

## First device trial

Fully close an older diagnostic app before upgrading, disconnect real CarPlay receivers, open CarPlay Diagnostics, and tap Run diagnostics while unlocked. Wait for completion (normally around two minutes; three-minute budget plus bounded cleanup), then Share diagnostic log. If helper startup fails, use Share anyway. Repeat runs use new report files without reinstalling.

The phone must establish: signature trust, app registration/read access, on-demand helper launch, peer authorization, target/ABI compatibility, four request-profile outcomes where permitted, system-log availability, and cleanup. Existing sessions or failed checks withhold further active calls and explain why in the same report.

This is a session-start diagnostic. It does not implement accessory authentication, a full CarPlay receiver, video decoding, native app switching, or Tesla display output. Callback/loopback/session observations are not a claim of working CarPlay. Local testing cannot guarantee a successful first device run or eliminate the possibility of a device-specific correction.
