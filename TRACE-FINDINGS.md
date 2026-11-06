# CarKit request trace — 2026-11-06

The uploaded 0.1.1 report confirms working helper IPC and four completed native request attempts. All observed sessions were nil; no completion or loopback connection was recorded. The log utility was absent and ASL returned no records. This establishes a silent startup boundary, not an MFi failure. The phone was disconnected during the following offline investigation.

## Retained iOS 16.6 caller

Inspected retained `carkitd`, SHA-256 `72ee56fbcd6716dd034f01c9a32f84222fdf48baae2170e0fe5d44ccdebe7064`, UUID `9517DC80-EC7F-38D1-BA2D-148CDE5FC24C`, minimum OS/SDK 16.6.

`CRCarKitServiceAgent::_mainQueue_startSessionForHost:reply:` at `0x10001805c` invokes imported `CARSessionRequestClient startSessionWithHost:completion:` at `0x100018138`. The client implementation lives in CarKit.framework, not this daemon. Its own listener, `com.apple.carkit.service`, checks the generic `com.apple.private.carkit` entitlement for a different, upstream API. Adding that generic entitlement would not be an evidence-based fix for the direct client call.

The start call passes a block invoking `0x100018164`, descriptor `0x100069328`, signature pointer `0x100069338` to `0x10005b82f`. The signature is `v20@?0B8@"NSError"12`: a BOOL success and NSError completion. The invoke retains x2 and forwards x1/x2. The previous diagnostic intentionally observed only callback occurrence, discarding arguments.

Typed observation in 0.1.2 requires the exact daemon file digest/UUID, class and IMP owners inside the expected CarKit image, existing method ABI checks, and loaded framework UUID `E7918412-DF06-3E57-9E4E-C031AD370605`, which was paired with that daemon in the retained image inventory. A historical process-level UUID differs from the same report's path-matched image UUID; that collector used dyld index zero for the process field. The inconsistency is preserved, and no current phone identity is assumed. The compatibility gate uses the file digest and path-matched framework identity; unknown identities keep occurrence-only callbacks. This is compatibility evidence from a retained caller and historical image pair, not decompilation of the exact target framework.

## Specific entitlement hypothesis

The retained iOS 16.6 daemon carries `com.apple.private.carkit.sessionRequest=true` in its embedded entitlements.

The separately retained **iOS 27.2 / 24B119** CarKit image (UUID `AFB351CF-17E1-3BD5-8AEB-AE7EB21BC00B`) supplies corroborating, version-distinct evidence:

- `CARSessionRequestClient serviceConnection` at `0x1c2d773dc` connects to `com.apple.carkit.sessionRequestHandler` with options `0x1000`.
- `CARSessionRequestAgent listener:shouldAcceptNewConnection:` at `0x1c2d75914` reads `com.apple.private.carkit.sessionRequest` via `valueForEntitlement:` and `boolValue` before the acceptance branch.
- Relevant CFStrings and shared-cache stubs were resolved against retained bytes, rather than inferred from decompiler output.
- Newer launchd plists conditionally assign the service to `audiomxd` or `airplayd`. No retained iOS 16.6 launchd ownership evidence was found. The next report inventories actual device ownership instead of assuming the newer process applies.
- The newer start API has an extra requestIdentifier parameter. Its ABI is not transplanted to iOS 16.6.

This supports a controlled experiment, not a proven current authorization failure. The package leaves the main helper's entitlements unchanged and adds one separate comparison executable with identical code and only the specific sessionRequest entitlement added. It records its effective value, runs after the original four profiles, then repeats the unchanged baseline. A stage failure or remaining session withholds further trials. Order/service-state effects remain a limitation. No authentication or policy bypass is installed globally.

## Missing errors now instrumented

The observer validates the owned client's serviceConnection method and returned NSXPCConnection class; retains exact identities; wraps only those connections' proxy error/lifecycle callbacks; preserves their original handlers and asynchronous/synchronous behavior; observes replacement connections; marks cleanup events separately; and bounds records/underlying errors. The getter is primed before startup and may create a lazy connection. It does not send a second request. Early errors, failed hooks, one-way messages and daemon-only messages remain explicit coverage limits.

Worker output is serialized across callback queues. A real concurrent-writer regression reproduced corrupt JSON before this fix and passes afterward. Completion interpretation and main-queue liveness are separately recorded. A package regression also exposed an unhashed README; the manifest now covers every payload file except itself.

## REA method and limits

REA 6.8.0 with a scoped Ghidra 12.1.4 / Temurin 21 backend analyzed original files read-only; no global REA settings were changed. Successful dossiers include:

| Function | REA evidence ID |
|---|---|
| Retained16 start caller | `ev_a7493d60c0f0c4d01a9ef3921f8b5203e635e44ee483abd0f6664db61d8960e2` |
| Retained16 completion | `ev_adbae182e6c31a279e2fbccdee6822d4bcee41200196fc4551c9bf8a8a48d9a8` |
| Newer27.2 serviceConnection | `ev_816e24b7cd8d191ba0ca9cd1f7b84c3d567dee6573a7577035ad97aadef9fd04` |
| Newer27.2 agent listener | `ev_dc1dda9eb00960ee1b3d55d3a608839369b19e5585295850ee2373482b7fbd1c` |

Ghidra's Objective-C/ARC pseudocode has receiver/parameter reconstruction artifacts; extracted framework stubs and PAC instructions also limit pseudocode. Conclusions above rely on matching instructions, selector/CFString resolution and block metadata, not reconstructed C declarations. Full local bundles, decoded facts and annotated disassembly are retained under the isolated research evidence directory and are not firmware payloads in this release.

The exact iOS 16.6 framework and current runtime errors remain unavailable until a phone trial. The diagnostic receiver implements OPTIONS only and cannot complete authentication, video negotiation, native app switching or Tesla display output. Session-start progress and a working CarPlay implementation remain separate milestones.
