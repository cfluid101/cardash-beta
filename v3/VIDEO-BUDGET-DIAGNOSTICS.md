# Native video readiness reasons

The existing `com.cfluid.cardash.v3.video.ready` channel is unchanged: `(PID << 8) | readiness`, with readiness 1 for ready and 2 for refusal. Startup decisions continue to use that channel.

The optional `com.cfluid.cardash.v3.video.ready_reason` channel carries `(PID << 32) | (readiness << 16) | reasonCode`. The native adapter publishes it from `BudgetReport`, immediately before the corresponding readiness value. Neither the encoder callback nor the periodic lease tick publishes this sideband.

`budget_status()` adds `reasonCode` and `reason` only if the sideband's PID and readiness match the existing channel, the readiness/reason pair is consistent, and a second readiness read is unchanged. Missing, unreadable, stale or transitional sideband data adds no reason fields and does not change readiness or introduce an error. Older adapters remain compatible. These optional scalar fields flow through `videoBudget` status into diagnostic exports; they do not change the encoder budget.

| Code | Exported reason | Meaning |
| --- | --- | --- |
| 0 | `ready` | Hook installed successfully. |
| 1 | `entry_address_overflow` | Computed hook entry overflowed the address range. |
| 2 | `hook_provider_unavailable` | Function-hook provider was unavailable. |
| 3 | `required_symbols_unavailable` | Required display or bandwidth symbols were unavailable. |
| 4 | `entry_mapping_mismatch` | Hook entry was not mapped readable and executable. |
| 5 | `entry_prologue_mismatch` | Entry bytes differed from the selected firmware profile. |
| 6 | `property_key_type_mismatch` | Exported display UUID or bandwidth key had the wrong type. |
| 7 | `copy_property_symbols_or_key_mismatch` | Derived-storage API or NetworkInfo key was missing or invalid. |
| 8 | `hook_installation_failed` | Hook installation did not provide an original function. |
| 9 | `unsupported_image_identity_or_header` | No supported AirPlaySender identity with a valid header was selected. |
| 10 | `arm64e_adapter_slice_required` | The 20A357 profile requires an arm64e adapter slice. |

An unrecognized nonzero reason from a coherent refusal record is retained numerically with `reason: "unknown_reason"` for forward compatibility. A matching reason describes the selected native process's reported state; it is not a claim that an on-device session or encoder run succeeded.

Focused tests: `python3 -m unittest test_video_budget.BudgetStatusTest test_video_budget.BudgetTest` from `v3/tests`. The four status tests cover valid failure/success reasons, legacy/missing readers, stale PID/readiness, inconsistent reason status, and readiness transitions. The five budget tests retain the native clamp/ownership coverage.
