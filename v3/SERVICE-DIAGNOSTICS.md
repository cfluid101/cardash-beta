> Historical diagnostics 3 collection guide. The current full compatibility package is described in [COMPATIBILITY-BETA.md](COMPATIBILITY-BETA.md); install that package and test normally, then export. The bounded report behavior described below is retained.

# HTTPS3 compatibility diagnostics 3

Package: `3.0.0~beta.5+https.3.open.1.diag.3`.

**This is a diagnostic prerelease, not a completed iPhone 14 Pro Max/iOS 16.0 CarPlay fix.** It collects missing evidence in one export. Standard rootless Dopamine is the immediate target; RootHide paths and injection remain unported. The ordinary [HTTPS3 beta](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3) stays available separately.

## Install and collect once

1. Stop CarPlay and close its browser viewers. Avoid calls/music during installation: the installer restarts V3 and Apple's media service.
2. Install this diagnostic DEB **over the existing CarDash V3** through Sileo or another dependency-aware package manager. It uses the same package ID, replacing V3 rather than creating a second app. Do not uninstall/reset setup or delete saved state.
3. Open CarDash V3 on the unlocked phone. Confirm the subtitle says **compatibility diagnostics 3**, then tap **Export diagnostic report**. Allow up to 10 seconds for inspection.
4. Send the new `.ndjson` report and the Dopamine app's version. The phone model, iOS version and build number are collected automatically. Review the report before sharing; export does not upload it.

No Tesla trip, USB connection, APK import, Prepare CarPlay, or repeated Start attempts are needed for collection. The V3 service starts automatically on installation, but installation/export do not request a native CarPlay session. If installation fails or the companion cannot open, send the package manager's installation output instead.

## Evidence added

- The injected adapter contains both arm64 and arm64e slices. Standalone executables remain arm64. This fixes the previous architecture packaging gap; it does not port private framework implementations.
- A bounded, versioned notification inventory reports the adapter CPU type/subtype and **observed** APTransport, MediaExperience and AirPlaySender UUIDs inside `mediaserverd`. PID/sequence validation rejects missing, stale, partial or changing publications. Missing frameworks and publication errors are explicit; a missing inventory does not prove why injection failed.
- Export independently runs the session helper's read-only `--inspect` mode, even when the media adapter prevents Start. It reports CarKit/carkitd identities, supported-identity comparisons and required method ABIs. It does not construct a CarKit client/host/status object, contact an accessory, or request/cancel a session. Internal/external timeouts and output limits bound collection.
- Readiness failures retain their observed PID and status code. Reports no longer substitute a supported framework UUID for an observed one.
- The companion records model/build/package, socket errors and metadata for service, injection dylib/filter and hook-provider paths. Live reports preserve complete bounded NDJSON records.
- If the service is unavailable, offline export records context and readable tails of V3's two startup logs. The `.jbroot` link beside this app is inspected only as evidence; no paths are migrated. Missing/denied logs remain useful evidence.

The exporter does not read saved accessory keys. The package has no saved identity/preferences payload. Installation preserves existing V3 identity/settings and original CarDash/V2 files. Offline log reads reject symlinks/nonregular files and are capped at 64 KiB per log. Helper output is capped at 64 KiB per pipe; final exports are bounded.

## What remains for native operation

Verify and adapt all four integrations for the tester's actual framework family: APTransport transport, MediaExperience device-audio routing, AirPlaySender bandwidth control, and CarKit/carkitd request/completion handling. Unknown images retain their protective identity/instruction/ABI checks. A compile or accepted installation cannot establish arm64e injection, pointer authentication, native video or locked switching.

The new report tells us which checks were reached and provides exact identities for targeted analysis. A subsequent compatibility build still needs physical-phone validation. See [COMPATIBILITY.md](COMPATIBILITY.md) and [TEST-RESULTS.md](TEST-RESULTS.md).

## Rollback without resetting setup

Stop CarPlay, then use the package manager to install/downgrade to the [previous open-testing DEB](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/com.cfluid.cardash.v3_3.0.0-beta.5-https.3_iphoneos-arm64.deb). Retain `/var/jb/var/lib/cardash-v3`; do not delete/reinitialize it. This restores previous software, not a proven working session on the tester's phone.

Previous DEB SHA-256: `457bfd78326da6ee15c8268d2e87a3299f58f8e878d8fe23caf39dde628b10b3`.

RootHide remains a separate adaptation: launcher, launchd, Python/native dependencies, companion IPC and injection must agree on its layout. Its [developer documentation](https://github.com/roothide/Developer/blob/main/roothide.md) distinguishes those environments; inspecting `.jbroot` alone does not implement support.
