# Transport diagnostic reasons

The compatibility beta exports the native transport adapter's specific refusal reason as optional `transport.reasonCode` and `transport.reason` fields. Export diagnostics after both a successful session and a failed attempt. A ready adapter confirms hook initialization; it does not establish that a CarPlay session started or that native video, audio, or the arm64e trampoline has been validated on the device.

The existing `com.cfluid.cardash.v3.loopback.ready` notification is unchanged: `(PID << 8) | readiness`, where readiness is 1 for ready and 2 for unavailable. The optional `com.cfluid.cardash.v3.loopback.ready_reason` notification carries `(PID << 32) | (readiness << 16) | reasonCode`.

The backend accepts a reason only when its PID belongs to the live primary publisher, its readiness agrees with the primary state, and a second primary read is unchanged. Reason 0 must accompany readiness 1; other reasons must accompany readiness 2. Missing, stale, contradictory, or unreadable details are ignored without changing readiness. Unknown future reason codes remain numeric. Old adapters and readers retain the primary readiness behavior.

| Code | Meaning |
| --- | --- |
| 0 | Transport adapter ready: both transport hooks returned original entry points. |
| 1 | Adapter loading; initialization has not completed. |
| 2 | No supported APTransport firmware UUID/CPU profile was selected. |
| 3 | The exact 20A357 profile was selected in an adapter slice that is not arm64e. |
| 4 | The native hook provider is unavailable. |
| 5 | `CMBaseObjectGetDerivedStorage` is unavailable. |
| 6 | A transport entry is outside the expected image bounds or lacks the required executable mapping. |
| 7 | A transport entry's instruction fingerprint does not match the selected profile. |
| 8 | The transport update hook did not return an original entry point. |
| 9 | The transport disconnect hook did not return an original entry point. |
| 10 | Live transport state failed mapping or type checks; the rejected call made no loopback writes. |

Known failure reasons also appear in the existing `error` string, so exports retaining only that field still contain useful detail. Code 10 records a rejected call and leaves readiness unavailable; it does not assert that all earlier calls were rejected. An exact firmware match alone does not bypass runtime checks.

Native publication occurs in initialization, hook-result, and rejected-layout reporting paths. Both notification tokens are registered once. A mutex serializes publication and suppresses repeated identical PID/readiness/reason reports, including their logs. Successful update/event paths add no diagnostic notification work. Notifications remain best-effort: registration or publication failure can leave the optional reason absent, and the backend falls back to the existing primary status.
