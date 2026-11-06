# CarDash CarPlay Diagnostics 0.1.3

Standalone rootless diagnostic for **iPhone 8 Plus (`iPhone10,2`), iOS 16.6 (`20G75`), Dopamine**. It attempts the known native session-start API and collects one shareable log. It is not a replacement CarDash beta or a complete CarPlay receiver.

## On the phone

1. Fully close an older **CarPlay Diagnostics** app. Install `com.cfluid.cardash.diagnostics_0.1.3_iphoneos-arm64.deb` with your rootless package installer. No respring is required. Installation performs a STATUS-only helper preflight and starts no CarPlay trial.
2. Disconnect real CarPlay receivers. Open **CarPlay Diagnostics**, keep it visible with the phone unlocked, and tap **Run diagnostics**. Allow two to three minutes; the overall budget is three minutes plus bounded cleanup.
3. Wait for **Report ready**, then **Share diagnostic log** and send the single `.log` file. If startup fails, Share still exports the app error and supporting logs.

Cancel stops the trial and retains its report. Every run gets a new report; no reinstall is needed to repeat it. The app prevents automatic screen sleep only while testing in the foreground. Target, ABI, existing-session, failure and cleanup guards can withhold later stages and record why.

## What runs

- Device/build, effective signed entitlements, app/helper IPC facts, process snapshots, payload manifest, CarKit method encodings, display/session inventory, configured CarKit launchd service owners and isolated AirPlayReceiver class inventory.
- Four serial profiles: an unentitled root/simulator/string-key baseline, the same request with the specific sessionRequest entitlement, an entitled no-key request, and an unentitled baseline repeat. The comparison executable retains identical code and signing Identifier with only `com.apple.private.carkit.sessionRequest` added; its effective entitlement must read true. Version0.1.2 device logs confirmed this entitlement is required by the receiver. Earlier attempts can still affect service state.
- Host construction uses the observed full initializer, a synthetic device identifier and a string public key. An explicit type check plus an actual CarKit secure-coding round trip must pass before any request. Version0.1.2 sent NSData; the iOS16 receiver rejected it during decoding.
- Each attempt owns an IPv6-loopback listener on an ephemeral port, validates host-property readback, invokes `startSessionWithHost:completion:` once, observes for 18 seconds, calls `cancelRequests`, closes its sockets and checks session state afterward.
- Worker-local instrumentation observes only the exact owned CarKit client and its NSXPC connections. It records connection/protocol metadata, bounded errors and underlying causes, interruption/invalidation events and coverage while preserving original callbacks. It sends no additional remote request. Priming the getter may create a lazy connection; errors before registration may be missed.
- Completion success/error is interpreted only when method checks and the exact retained daemon SHA/UUID, loaded CarKit UUID and implementation owners match recorded compatibility evidence. Unknown identities retain occurrence-only callbacks. The log records the identity and evidence basis; the exact iOS 16.6 CarKit implementation has not been recovered offline.
- Filtered system logs if a usable `log` utility exists, with bounded ASL fallback. Client-side XPC errors are recorded even when these daemon log facilities are unavailable. Unavailable logs never mean no error occurred.

Independent worker deadlines and parent-death guards terminate owned process groups. Reports preserve crash/timeout/cancel status, output truncation and a terminal record on managed completion; an abruptly killed helper can leave a partial report worth sharing.

## Interpreting results

| Record | Meaning |
|---|---|
| `request_withheld` | A guard prevented a request; inspect its reason. |
| `start_call_enter` / `start_call_returned` | The native request was invoked / returned. |
| `completion_identity` / `native_completion` | Identity gate and callback occurrence; typed success/error only if permitted. |
| `xpc_proxy_error` | An NSError from the owned connection's request path, with bounded causes. This is client-side evidence, not a daemon log. |
| `xpc_connection_interrupted` / `xpc_connection_invalidated` | Connection lifecycle event. `cleanup: true` means cancellation has begun; invalidation alone does not identify its cause. |
| `xpc_trace_summary` | Instrumentation coverage and counts. Zero recorded errors do not prove success. |
| `loopback_connected` / `receiver_request` | A client reached the listener. Correlate other evidence to identify it. |
| `native_success` / `new_session_observed` | Native callback/session observations, distinct from authentication or display verification. |
| `session_after_cleanup` | Whether CarKit still reports a session after cancellation. |
| `live_carplay_verified: false` | No live authenticated video/input session has been verified. |

**Authentication is not implemented.** The public test key is freshly generated, not an Apple-trusted accessory identity; its private key is discarded. The receiver answers OPTIONS, then returns explicit diagnostic-only 501 responses to other methods. Transport progress identifies the next implementation boundary; it does not prove working CarPlay. No transport alone cannot identify MFi/crypto as the failure.

## Isolation

Package `com.cfluid.cardash.diagnostics` owns only its app, two helper executables, one on-demand launch job and `/var/jb/var/lib/cardash-diagnostics/`. Original CarDash and V2 paths/preferences are not package targets. Reports survive uninstall. There is no HTTP control listener, SSH requirement, injection dylib, system-wide hook, network-setting change or explicit pairing-record edit. The comparison worker has no persistent service. The control socket is restricted to the installed app/root CLI. Logs are bounded and never uploaded automatically; review before sharing.

Root CLI: `/var/jb/usr/libexec/cardash-diagnostics --run`, `--status`, or `--cancel`.

## Build and validation

Build: `python3 build.py`. Tests: `python3 -m unittest discover -s tests -p 'test_*.py'`. The build also runs ABI/ownership checks and malformed-image/identity-gate checks. Simulator build: `python3 build.py --simulator`; `simulator-smoke.py` uses the separately owned research simulator with synthetic host workers. Builds never contact a phone.

Local tests exercise real NSXPC errors, callback preservation, synchronous/asynchronous semantics, successful replies, untracked-client isolation, replacement connections, concurrent JSON emission, bounded error data, package signatures/complete payload hashes, comparison entitlements/identical code, helper IPC, installation, cancellation, crashes, deadlines and process cleanup. Simulator checks exercise Run/Share and failure exports, not iOS private-service authorization.

**The corrected payload is undergoing physical-device validation.** Local tests cannot guarantee jailbreak signature trust, private-framework behavior, error availability or a successful native session. See [VALIDATION.md](VALIDATION.md) and [TRACE-FINDINGS.md](TRACE-FINDINGS.md).

## Evidence motivating this release

The supplied 0.1.0 report failed app/helper IPC with EPERM. Version 0.1.1 corrected device app confinement; its uploaded report confirms helper access and all ten stages, including four requests, but no callback, listener connection or new session. Daemon logs were unavailable. Version 0.1.2 captures the missing client-boundary evidence and tests a narrowly supported entitlement hypothesis. It does not claim the current failure is MFi. Historical IPC analysis remains in [IPC-FIX.md](IPC-FIX.md).

## 0.1.3 request correction

The connected phone confirmed that mediaserverd owns the request endpoint. Unentitled requests produce 4097 and an explicit missing-entitlement message. The entitled0.1.2 request was accepted, then rejected because publicKey was NSData instead of NSString. This version corrects the wire type, validates serialization before sending and compares string/no-key requests. This is not an authentication implementation. See DEVICE-TRACE-20261106.md for measured results.
