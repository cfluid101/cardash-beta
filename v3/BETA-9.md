# CarDash V3 Beta 9 — automatic framework profiles and failure reports

Package `3.0.0~beta.9`, November 16, 2026. One standard-rootless V3 package
selects the inspected session, transport, video and audio implementations
independently. It retains beta 7's viewer recovery, timing and audio policy and
includes beta 8's iOS 15.4.1 work.

**This beta has not run on a physical phone.** The original iPhone 8 Plus /
iOS 16.6 path is retained and regression-tested on the host. New profiles are
experimental firmware-derived candidates, not confirmed working devices.
Keep your currently working DEB for rollback.

## Exact firmware coverage

These rows identify the inspected framework sets. Other devices may use an
identical set and select it automatically; their model or iOS version alone
does not grant support. Unknown identities remain blocked with diagnostics.

| Firmware reference | Status in beta 9 |
|---|---|
| iPhone 8 Plus, 16.6 / 20G75, arm64 | Original historically working path retained; beta 9 device retest pending |
| iPhone 14 Pro Max, 16.0 / 20A357, arm64e | Existing experimental profile retained |
| iPhone 13 Pro, 15.4.1 / 19E258, arm64e | Beta 8 experimental profile retained |
| iPhone 13 Pro, 15.6.1 / 19G82, arm64e | New experimental candidate |
| iPhone 8 Plus, 16.0 / 20A362, arm64 | New experimental candidate; archive covers iPhone10,2 and iPhone10,5 |
| iPhone 13 Pro, 16.6 / 20G75, arm64e | New experimental candidate; distinct from the arm64 framework set |
| iPhone 13 Pro, 17.0 / 21A329, arm64e | New experimental request/schema and media profiles; native authentication acceptance pending |
| iPhone 13, 17.6.1 / 21G93 or 21G101, arm64e | Firmware profiles implemented; compatible jailbreak/injection and native authentication acceptance required |
| iPhone 13 Pro, 15.0 / 19A346, arm64e | Diagnostics only: transport rejects the unresolved early USB-release lifecycle before installing transport hooks |

The deployment minimum is now **15.0**, so early systems can run diagnostics.
It is not a claim that every version from 15.0 upward can start a session.
An installed application or bootstrap alone does not establish system-process
tweak injection. This package does not install or extend a jailbreak.

As checked November 16, 2026, the official [Dopamine 3.x README](https://github.com/opa334/Dopamine/blob/3.x/README.md)
lists general arm64e support through 17.3.1, with a wider range for A12/A13.
The iPhone 13's A15 on 17.6.1 is outside that stated range. Its firmware profile
does not make that device jailbreakable with Dopamine. RootHide-native and
rootful packaging remain unimplemented; their layouts require separate work.

## What changed

- Session requests choose the old host/completion interface or the inspected
  iOS 17 interface with an NSUUID request identifier. New hosts must pass field,
  method-owner and secure-archive checks before a request is sent.
- The receiver truthfully advertises no newer mutual-authentication capability.
  It does not fabricate credentials or bypass authentication. An iOS rejection
  reports its stage, error domain and code.
- Transport selects the verified middle or shifted layout for its own image.
  The 17.6.1 request-identifier field is preserved. Unknown or unsafe layouts
  do not receive guessed offsets.
- Video selects its call signature independently of CPU type. This supports
  the inspected arm64 CopyProperty and arm64e NetworkInfo cases, with explicit
  iOS 17 storage offsets and checks before the adapter's additional state reads.
- Audio adds exact setter/flag profiles and decodes the native failure reasons.
- Export includes a `compatibility_summary` with UUIDs, CPUs, readiness and
  per-component failures. Startup failures survive in the rotating logs; native
  rejection details survive helper exit. Offline app export still works if the
  receiver service is unavailable. Reports remain on the phone until shared.

## Install and test

1. Stop CarPlay and keep the previous DEB. Install beta 9 over existing V3 using
   Sileo or another dependency-aware package manager. Installation restarts the
   media service. Keep the existing setup; do not reset or re-import credentials.
2. Open CarDash V3. Export diagnostics once before starting. It should identify
   beta 9 and the actual model/build. A recognized profile is a preflight result,
   not successful device acceptance.
3. Use [Viewer 5](https://cfluid101.github.io/cardash-beta/option1/?v=https3&ui=5).
   Viewer 4 remains compatible. On Wi-Fi/hotspot with USB disconnected, check
   Start, first video, navigation/touch, Device audio and Browser audio.
4. Check lock/unlock, shrink/restore, reconnect, Stop and another fresh Start.
   Repeat after a userspace reboot. Test the retained 8 Plus path first and
   perform vehicle trials while parked.
5. After success or failure, tap **Export diagnostic report**. For a crash,
   include the matching mediaserverd/carkitd/helper crash report too. No log can
   guarantee capture of the final instruction before a native process crashes.

The existing music-at-Start routing issue is not fixed: start CarPlay before
playing music, or pause before Start. A viewer that has shown CarPlay may be
silent for up to 15 minutes before the session ends; Stop ends it immediately.

Build instructions and results: [BUILD.md](BUILD.md), [TEST-RESULTS.md](TEST-RESULTS.md).
No Apple firmware or private accessory identity is bundled in the release.
