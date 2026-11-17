# Beta 9 CarKit request and host evidence

The existing iPhone 8 Plus / iOS 16.6 legacy initializer, request selector, daemon identity and callback identity remain. New profiles use exact CarKit UUIDs and require each method's type and owner to match that same framework before constructing a host. Selection is independent of reported iOS version. Unknown images remain unavailable.

Eight dictionary profiles are implemented: retained 19E258/20A357; new 19A346, 19G82, arm64 20A362, arm64e 20G75, 21A329 and the shared 21G93/21G101 CarKit image. A CarKit profile alone does not establish transport, media, jailbreak or complete session support. In particular, the new 19A346 CarKit profile does not remove that target's separate transport limitation.

## iOS 17 request adapter

The two inspected iOS 17 images expose `startSessionWithHost:requestIdentifier:completion:`. Their service protocol explicitly identifies the request identifier as NSUUID. The linked reply descriptor and argument-forwarder evidence establish the BOOL/NSError completion ABI. Beta 9 creates a real NSUUID for that selector, retains the old two-argument selector for earlier profiles, and rechecks method ownership/type/UUID immediately before dispatch.

The receiver does not implement mutual authentication. Its expanded host dictionary therefore explicitly supplies `supportsMutualAuth: false` and omits the nil certificate-serial and paired-vehicle identifiers. This is a capability declaration, not an authentication bypass. The service may reject this request. The resulting native error domain/code and request stage are logged; no service-side acceptance is claimed.

## Additional static constructor and archive review

The five-sample sweep and the previous 17.6.1 investigation retain all image hashes, constructor-key mappings and callback evidence. Additional bounded LLVM disassembly is stored at:

`/Volumes/FluidDrive/CarDash-Firmware-Research/compatibility-sweep-2026-11-16/analysis/carkit/beta9-audit/`

`commands.json` records the exact image, SHA256, command, output hash and status for eight dumps. No image was loaded or executed. The complete long initializer, bool/class verifiers, secure decoder and secure encoder were inspected in both 21A329 and 21G101. The extracted-file disassembler assigns misleading nearest-symbol labels to some out-of-image branch destinations; those speculative labels were not used as semantic evidence.

| Operation | 21A329 | 21G101 |
|---|---|---|
| Expanded long initializer | 0x1ac30f130 | 0x1ad8c7f54 |
| Dictionary initializer | 0x1ac30f2e0 | 0x1ad8c8104 |
| CARVerifyClass | 0x1ac30f784 | 0x1ad8c85a8 |
| CARVerifyBool | 0x1ac30f818 | 0x1ad8c863c |
| Secure decoder | 0x1ac30f8a4 | 0x1ad8c86c8 |
| Secure encoder | 0x1ac30fcc8 | 0x1ad8c8aec |

Both dictionaries pass the authentication boolean through CARVerifyBool; the verifier contains a false-return path and the NSNumber boolValue path. Both long initializers store the supplied boolean and object parameters without adding a nonnil certificate/vehicle requirement in that bounded method. The dictionary's paired-vehicle parameter has an explicit nil branch. CARVerifyClass returns nil for a nonmatching value rather than substituting an identity. The secure encoders serialize the mutual-authentication getter as NSNumber and omit nil certificate/vehicle getters. The secure decoders conditionally read those keys and skip absent/nil optional object fields.

Concrete 21G101 anchors: dictionary paired-ID nil branch 0x1ad8c8334 to 0x1ad8c8364; long-initializer boolean store 0x1ad8c8088; encoder boolean serialization 0x1ad8c8cf8–0x1ad8c8d20; encoder nil skips 0x1ad8c8d3c and 0x1ad8c8d7c; decoder optional-object nil skips 0x1ad8c8a1c and 0x1ad8c8a6c. Corresponding 21A329 encoder nil skips are 0x1ac30ff18 and 0x1ac30ff58.

This supports trying the exact constructor schema. It does not establish downstream authentication semantics or a successful iOS session. Beta 9 additionally checks every host field after actual construction and after a real secure archive/decode on the target phone, including false mutual authentication and nil optional identifiers. A mismatch reports the field name and stops before dispatch. The 16.6 arm64e read-only mutual-authentication getter is also checked before and after archiving; its value is never assumed from an OS version.

## Host verification

`python3 -m unittest v3.tests.test_host_profile v3.tests.test_session_inspection` exercises profile selection and real Foundation secure archives using host fixtures. The fixtures substitute image ownership/identity only; they do not emulate Apple private implementations or establish on-device compatibility. They check exact/mixed/unknown/foreign identities, wrong method ABI, invalid input, live/archive field corruption, new auth-field corruption, actual old/new request dispatch, NSUUID type, both callback arguments, stale dispatch identities and the retained legacy dispatch path. Inspection fixtures abort if class initialization or a session operation occurs, verifying metadata-only inspection for both request families.

The native diagnostics recognize both the original CarKit support directory and `/usr/libexec/carkitd`, while retaining the original daemon guard for the legacy profile. Logs include selected profile, request family, schema, firmware evidence level and explicit device-validation/daemon-acceptance uncertainty. Arbitrary NSError userInfo/description is excluded from session logs; domain/code and bounded field-specific errors remain.
