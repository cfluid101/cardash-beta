# Beta 9 profile additions

Beta 9 retains the three existing framework sets and adds exact identities for the five FluidDrive samples plus the shared 17.6.1 images. The early 19A346 transport is recognized but blocked before transport hooks. See [BETA-9.md](BETA-9.md) for coverage. Source tables are `native/HostProfile.mm`, `native/LoopbackProfile.h`, `native/VideoBudgetProfiles.h` and `native/AudioRouteProfile.h`; independent firmware metadata/entry fixtures are under `tests/fixtures/`. Host constructor/schema evidence is in `../docs/beta9-host-evidence.md` in the source archive. These are static/host checks, not phone success.

The sections below document the retained earlier profiles.

# Native implementation profiles — compatibility beta 1

Selection uses observed binary identity, architecture, method ownership/types and instruction fingerprints. Installation has no model or firmware allowlist. Beta 8 adds the 19E258 implementations below alongside the existing 20G75 and 20A357 paths. Device/build strings are context, not substitute checks for implementation identity.

## Beta 8: iPhone 13 Pro / iOS 15.4.1 / 19E258

The Apple restore archive `iPhone14,2_15.4.1_19E258_Restore.ipsw` was downloaded and checked against its expected size and SHA256: 6,518,149,573 bytes, `26018ab582046bf9e5cc05e84a9a41fd2d653bce0bde809478678b6e90245937`. BuildManifest and the system version identify iPhone14,2 / 15.4.1 / 19E258. The system image was mounted read-only for cache inspection. These are static firmware observations, not device execution.

| Framework | UUID | Added behavior |
|---|---|---|
| CarKit | `8B932A1D-AFE6-32C1-A93E-FDB58CC05AE4` | Existing dictionary-host schema and typed BOOL/error completion |
| APTransport | `5A565981-1C87-3934-97CC-5F5541BC438F` | Guarded update/event hooks at image offsets `0x5a05c` / `0x5d1f0` |
| MediaExperience | `578E182E-810F-39CE-A068-C026D4288122` | Verified setter decoding and existing owned audio lease |
| AirPlaySender | `1BFCC263-E0E7-3B4D-B4DA-39C0D46D3594` | Four-argument CopyProperty hook at image offset `0x1260e4` |

All four images are arm64e, CPU type `0x0100000c`, subtype `0x80000002`. The injected paths require the arm64e slice. The standalone arm64 session helper validates actual CarKit method owners, types and implementation UUIDs.

CarKit retains `startSessionWithHost:completion:` with encoding `v32@0:8@16@?24`. Its reply block invoke `0x198134580`, descriptor `0x1dc8d2dd0` and signature `0x198166676` establish `v20@?0B8@"NSError"12`, independently of the method's generic block encoding. The dictionary constructor reads the same nine wire keys as the 20A357 branch; all 16 checked method contracts match. The long legacy initializer is absent. Selection and construction require one consistent known framework UUID across their required methods, and preserve ownership checks and secure-archive readback. CarKit's reconstructed artifact SHA256 is `9bd3b17e7292a8839a49678fdc47eab22724b0e7f191633e7126b07c24f7a0fb` (extraction output, not an original standalone IPSW file).

APTransport base is `0x1b65ec000`. Full 20-byte entry fingerprints are `7f2303d5e923b96dfc6f01a9fa6702a9f85f03a9` and `7f2303d5ff0302d1e923036df85f04a9f65705a9`, including PACIBSP. The fields used by the shared wrapper were traced at host `+0xa8`, time `+0xb0`, transport `+0xb8`, interface `+0xc8`, map `+0x98`, state `+0xa0`, and USB fields `+0x40/+0x48/+0x50/+0x58`. The native USB-removal path releases/clears the host; the event block releases its captured helper. Existing ownership, final-reference protection and restoration remain required. This does not assert an identical full structure layout.

MediaExperience text base is `0x19ae4f000`, setter `0x19aefc58c`, flag `0x1d7636ad0`. Exact setter bytes `c8391ed008e1219100610939c0035fd6` decode the flag from ADRP/ADD/STRB. Runtime executable/writable mappings, instruction identity, slide handling and lease restoration remain checked.

AirPlaySender's CopyProperty entry has bytes `7f2303d5ff8304d1e9230c6dfc6f0da9`. Direct data flow and the signature string establish `(CMBaseObjectRef, CFStringRef, CFAllocatorRef, void *) -> OSStatus`; NetworkInfo is implemented inside that call. Display `+0x38` and CarPlay/USB flags `+0x150/+0x152` are independently corroborated by stream creation. The existing wrapper preserves original status/output ownership, allocator and other properties, and limits the override to the owned display and live budget lease. Its reconstructed artifact SHA256 is `deb44b08667cdf66d310520faaf0c0c3498d305d621c8bfaac6498621ed372c0`.

The added tables retain the original 20G75/20A357 constants and guards. Host fixtures test new/old selection, altered instructions and architecture, mixed/foreign/unknown method identities, actual fixture host construction and archive readback, and the shared wrapper lifecycle. They do not run Apple's frameworks. Physical injection/PAC behavior, service startup, native handshake/video, input, phone/Bluetooth audio, locking, recovery and cleanup remain acceptance tests for all three phones on beta 8. Unknown identities remain unavailable; no guessed-offset fallback is added.

## Earlier 20A357 profile evidence

## Target artifacts and evidence provenance

Four standalone reconstructed framework images were obtained from the public [iOS System Symbols Supplement](https://github.com/CXTretar/iOS-System-Symbols-Supplement), archive `16.0 (20A357) arm64e.7z`, SHA-256 `ead867353701f7122301e036dec2534639a8f8f5415d768250590a3c838c27d0`. Each UUID exactly matches the tester's in-process report. These are third-party extracted artifacts, not an Apple-authenticated restore image. They contain nonzero executable code; only static inspection was performed. Their file digests identify the research artifacts, not measured hashes of the tester's in-memory frameworks.

| Component | Matching UUID | Extracted artifact SHA-256 |
|---|---|---|
| APTransport | `5E0E473A-63EC-3293-A097-EEAD345A8244` | `ca61da7b084aa7e4150ed31f59ee0558314960b0a63dbf3d0858dc50fb63e463` |
| MediaExperience | `F944817F-4A89-31EE-A4F6-0DA7749D2DAC` | `571c4bac25b3fb2e6d90ca7a12aeb69d7847ef9407e901da7f6c43a668de4dd3` |
| AirPlaySender | `D4F52AAA-04C2-36A9-B0EF-3660C4A772F6` | `290548b42c46def57693454fd33d8a1237ef515750e65698e1295372befd7a07` |
| CarKit | `56E68CC1-FF26-3491-9ECA-D6974006E1A4` | `9f365d2c1981854de208960d6971699eb6692c13f632d78048c8dc8c43f62134` |

No Apple frameworks, cache files, tester log or accessory identity is included in the DEB/source archive. Matching metadata and necessary small instruction fingerprints are retained in source.

REA opened the APTransport artifact, but its deep provider was unavailable and its Mach-O inventory hit Apple's `dyld_info` rejection of the reconstructed `__AUTH` segment ordering. The implementation analysis therefore uses Xcode `dwarfdump`, `nm`, `otool`, LLVM disassembly and bounded Mach-O/Objective-C metadata decoding. It must not be represented as successful REA decompilation.

## APTransport

Image base `0x1c0290000`; update entry `0x1c02eaeec` (offset `0x5aeec`); disconnect/event block `0x1c02edec0` (offset `0x5dec0`). Full 20-byte entry fingerprints include PACIBSP. The new guard requires arm64e, mapped executable entries, readable/writable state and plausible typed state values before scoped writes. The former arm64 profile retains its offsets and fingerprints.

The update/callback/create disassemblies establish the state fields and captured helper/event offsets used by the adapter. Loopback address selection retains the first wired address if no later link-local address replaces it. Some external calls still point to cache-wide optimized stubs outside the extracted image. Their names are derived from a consistent `0x24742a8` relocation, preserved indirect-symbol order and compiler/argument-use patterns. Address coverage alone is not unique; original island bytes were not obtained. This remaining inference is part of the experimental device-test limit.

## MediaExperience

The target setter is `_CMSMUtility_SetDoNotMakeStarkAudioPortRoutableFlag` at `0x196516c50`, within `__TEXT` base `0x196468000`. Its four instructions are ADRP to `0x1da661000`, ADD `0xaa0`, STRB w0 at offset `0x218`, and RET. They directly establish writable flag address `0x1da661cb8`. The test independently decodes both profiles' instruction bytes and checks their declared flag addresses. Existing own-host lease, restoration and locking behavior is retained.

## AirPlaySender

The original 16.6 profile hooks a one-argument dictionary-returning helper. The target profile instead hooks `_screenstream_CopyProperty` at `0x1c04638c4`, offset `0x13f8c4` from `0x1c0324000`. Its entry/dataflow establish object, key, allocator and output-pointer arguments and OSStatus return. Native network-info calculation stays inside the original function.

The wrapper only changes a successful NetworkInfo CFDictionary for the owned display UUID and a valid budget lease. It validates runtime-exported property keys and dictionary value types, preserves the caller's allocator/status/output ownership, and does not modify native state. Display offset `0x38` and flags `0x150`/`0x152` are corroborated by separate creation/display-info functions. External derived-storage and CF calls have a consistent inferred stub relocation of `0x22ce3e0`; original island bytes remain unavailable. Runtime guards reject unmapped state or unexpected values.

## CarKit

The target initializer `initWithHostProperties:` is at `0x1a6a6bb44`. Its dictionary uses `displayName`, `wiredIPAddresses`, `wirelessIPAddresses`, `port`, `carplayWiFiUUID`, `deviceID`, `publicKey`, `sourceVersion` and `wiredCarPlaySimulator`. The wire keys differ from some property accessor names. The new builder validates method types/ownership and all host fields before and after secure coding, keeping publicKey a hex NSString.

Client `startSessionWithHost:completion:` is at `0x1a6a70384`. Its reply block invoke is `0x1a6a70534`, descriptor `0x1d6a525a8`, signature string `0x1a6a9d646`: `v20@?0B8@"NSError"12`. The reply invoke forwards the Boolean/error argument registers to the captured completion. This directly supports the framework-specific callback contract; it is stronger than inferring a block signature from the method's `@?` argument alone. The diagnostic export reads carkitd's identity/hash, but its implementation was not acquired or reverse engineered. The new profile explicitly reports that its callback gate uses framework evidence rather than claiming a daemon verification. The old 16.6 framework/daemon tuple is unchanged.

## Remaining physical verification

The new arm64e injection/trampolines, private object behavior, secure coding, actual native handshake/video, app input, device/Bluetooth routing, locked switching and cleanup are unverified on the tester's phone. Local fixtures and static identities cannot establish those outcomes. Unknown implementation families remain unsupported and diagnosable.
