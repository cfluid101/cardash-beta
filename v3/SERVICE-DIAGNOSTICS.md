# HTTPS3 compatibility diagnostics candidate 2

Package version: `3.0.0~beta.5+https.3.open.1.diag.2`.

This revision adds the missing arm64e slice to the injected media-service adapter while retaining arm64. iOS selects the process-compatible slice automatically. The report already collects the device model, iOS version/build and package version automatically. Framework hooks remain specific to the originally verified images; adding a slice is not an iOS 16.0 framework port. Do not present this local candidate as a universal working beta. See COMPATIBILITY.md.

This candidate addresses the missing evidence behind **V3 service is unavailable** when both the companion connection and local Safari preview fail. It does not claim to repair RootHide startup or port the native CarPlay adapters to another firmware.

## What changed

- The companion preserves the actual socket error and stage, distinguishes absent/refused connections and rejects overlong socket paths rather than truncating them.
- **Export diagnostic report** works without the service: it always creates a report with device/build/package information, configured socket path, file metadata and any readable startup logs.
- The exporter inspects the documented `.jbroot` symbolic link beside its own executable as an additional diagnostic candidate. It does not scan containers, change the active socket path, launch another service or migrate state.
- Offline log reads are limited to the final 64 KiB of V3's `installation.log` and `service-bootstrap.log`; unreadable/missing files are recorded explicitly. Symlink/nonregular log files are rejected. Identity/key/preferences files are never opened by the offline exporter.
- The installer preserves and sets only those two startup logs to `root:mobile`, mode `0640`; identity and other receiver files remain private. The companion includes RootHide's documented storage access entitlements for this read-only inspection. Their effect still requires verification in the tester's environment.
- Live exports now include a sanitized status snapshot and only complete bounded NDJSON records.

## Tester collection

Use this only as a diagnostic candidate. It retains the current **standard rootless package layout** and actual runtime requirements; it is not a dedicated RootHide build. Record the exact jailbreak name/version and whether/how the prior DEB was converted before choosing the installation method. Installation still restarts V3 and the media service; it does not start CarPlay or delete saved identity/settings.

Once the candidate companion can open, tap **Export diagnostic report** while the service error is visible, save/share the resulting `.ndjson`, and include the exact jailbreak version and any conversion method. No Tesla drive, USB connection, APK re-import or repeated Start attempts are required to collect this report. Missing/denied logs are themselves useful diagnostic evidence.

The app export is not an automatic upload. Review it before sending. This candidate is built and tested locally; no tester phone or RootHide runtime has been tested. The current published release has not been replaced.

## RootHide startup investigation

Official documentation distinguishes native paths resolved through `jbroot()` from RootHide bootstrap Python/shell paths. A correct port must adapt the launcher, launchd job, companion IPC, Python paths and native dependency paths together. Replacing `/var/jb` everywhere with one physical prefix can double-translate paths. This candidate only records evidence; it does not make that speculative startup change.

Sources:
- https://github.com/roothide/Developer/blob/main/roothide.md
- https://github.com/roothide/Developer/blob/main/interface.md
- https://github.com/roothide/Developer/blob/main/entitlements.md
- https://github.com/roothide/Developer/blob/main/vroot.md

Native transport, audio, bandwidth and CarKit ABI checks remain separate later requirements. An unavailable service does not establish that any of those checks were reached.
