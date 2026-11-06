# CarDash CarPlay Diagnostics 0.1.0

Standalone rootless diagnostic for the recorded **iPhone 8 Plus (`iPhone10,2`), iOS 16.6 (`20G75`), Dopamine**. It collects one shareable log and attempts the known native CarPlay session-start API. It is not a replacement CarDash beta or a complete CarPlay receiver.

## On the phone

1. Install `com.cfluid.cardash.diagnostics_0.1.0_iphoneos-arm64.deb` using your normal rootless package installer. No respring is required and installation does not start a session attempt.
2. Disconnect any real CarPlay receiver. Open **CarPlay Diagnostics**, keep the phone unlocked, and tap **Run diagnostics**. The suite normally takes about two minutes, with a three-minute overall budget plus bounded cleanup.
3. Wait for **Report ready**, then tap **Share diagnostic log**. Send the single `.log` file. You can run the suite again without reinstalling; each run gets a new report.

Cancel stops the current test and still produces a report. If the helper cannot start, Share exports the app error plus the available installation/helper logs. If an ABI check, process, deadline, or cleanup fails, remaining active stages are withheld and the reason is recorded. A report can therefore be complete as a diagnostic while its native attempt did not succeed.

The app disables automatic screen sleep only while a test is running in the foreground. Locking or backgrounding does not grant additional runtime privileges; keep it visible for the initial trial.

## What runs

- Device/build and process snapshots, build manifest, CarKit method encodings and implementation owners.
- CarKit/session inventory, display inventory, and an isolated AirPlayReceiver class inventory.
- Up to four serial native attempts: root + simulator + public test key; root + simulator without public key; root + non-simulator + public test key; mobile identity + simulator + public test key.
- Each attempt creates its own IPv6-loopback listener on an available port, validates host-property readback, calls `startSessionWithHost:completion:` once, observes for 18 seconds, calls `cancelRequests`, closes its sockets, and checks session state afterward.
- Filtered unified service logs when the phone supplies a usable `log` utility; bounded ASL fallback otherwise. Missing/unavailable logs are explicitly recorded rather than treated as absence of errors.
- Per-worker deadlines, independent parent-death guards, owned-process-group cleanup, crash/timeout/cancel status, output limits and a terminal `run_end` record on managed completion. An abruptly killed helper can leave a partial report; share it too.

Workers are separate processes. The helper is on-demand, never kept alive or run at boot, and its control endpoint is a local Unix socket restricted to the installed app/root CLI. There is no HTTP listener, SSH requirement, injection dylib, global hook, Wi-Fi/Bluetooth setting change, or explicit pairing-record edit.

## Interpreting the result

Read `native_summary` inside `captured_output.text`, along with the corresponding system messages and final `run_end`. These are distinct observations:

| Observation | Meaning |
|---|---|
| `request_withheld` | A target/ABI/ownership/existing-session guard prevented the call. |
| `start_call_enter` / `start_call_returned` | The known native request was invoked / returned. |
| `callback_observed` | The completion block ran. Its undocumented arguments are not interpreted. |
| `loopback_connected` / `receiver_request` | A loopback client reached the owned listener; the method/path/protocol is recorded. Correlate service logs to identify the caller. |
| `new_session_observed` | CarKit reported a session after a baseline with none. This is not proof of ownership, authentication or a working display. |
| `request_cancel_returned` | The client cancellation call returned; post-cleanup session presence is recorded separately. |
| `live_carplay_verified: false` | This diagnostic has not verified a live authenticated video/input session. |

**Authentication is not implemented.** The public key is a fresh public test value, not an Apple-trusted accessory identity; its private key is discarded during the build. The listener answers OPTIONS and records subsequent requests, returning an explicit diagnostic-only 501 for other methods. It cannot complete MFi/pairing/video negotiation. If transport arrives, that identifies the next implementation boundary. If it does not, the collected evidence helps investigate the earlier startup boundary. Neither outcome alone proves a full phone-only CarPlay receiver possible or impossible.

## Isolation and data

Package `com.cfluid.cardash.diagnostics` uses only its own app, helper, launch job and `/var/jb/var/lib/cardash-diagnostics/` report directory. Original CarDash and V2 files/preferences are not package targets. Reports survive uninstall. Runtime output is capped; truncation is marked, and terminal worker/cleanup records remain available. Logs can include CarKit service messages; review them before sharing. Nothing is uploaded automatically.

Root CLI, if needed: `/var/jb/usr/libexec/cardash-diagnostics --run`, `--status`, or `--cancel`. Normal use is through the app.

## Local validation and limits

Build: `python3 build.py`. Tests: `python3 -m unittest discover -s tests -p 'test_*.py'`, plus `build/host/gate-tests`. Simulator build: `python3 build.py --simulator`; the optional smoke script uses the separately owned research simulator and a synthetic host worker. Xcode, macOS codesign and Node (build-time generation of a public test key) are required; no phone is contacted by the build.

The rootless archive is independently extracted and checked for ownership, paths, signatures, manifests and scripts. Local process tests cover repeat runs, concurrency, cancellation before a native request, hangs, crashes, orphaned workers and descendants, output bounds, trickled control messages, and installation path protection. Simulator checks exercise Run, report generation, Share-file export and a failed rerun that must export fresh supporting logs instead of the old report. REA inspects the actual arm64 binaries' platform, minimum OS and dependencies.

These checks provide local build/package confidence. **The exact device's signature trust, launchd registration, peer authorization, private API behavior and native session result still require its first installation/test.** No 100% runtime guarantee is claimed. The report is designed to expose those failures in the same install rather than require a different DEB for each test stage.
