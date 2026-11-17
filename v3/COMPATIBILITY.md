# Broad-compatibility work

The intended experience is one appropriate package per jailbreak layout with automatic architecture and runtime selection, without users choosing firmware-specific builds. Successful installation alone does not establish that native CarPlay can start.

## Implemented in the local candidate

- The injected media-service adapter contains arm64 and arm64e code; iOS selects the compatible slice. The app, Python backend and standalone helpers remain arm64.
- Installation has no phone-model or firmware allowlist. Actual runtime dependencies and the iOS 15.4.1 binary deployment floor remain.
- Beta 8 adds exact 19E258/iOS 15.4.1 profiles for the iPhone 13 Pro firmware to the same tweak. The existing 20G75/iOS 16.6 and 20A357/iOS 16.0 profiles remain. Known implementations are selected automatically; see BETA-8.md.
- Exported diagnostics automatically include model, iOS version, build, package version, relevant local paths and native-adapter status. Export also works when the V3 service cannot be reached.
- Existing framework checks reject unmatched private implementations before the hooks are installed. Their addresses and signatures have not been changed speculatively.

## Not yet implemented or verified

- Physical verification of beta 8 on all three target phones, including the new iPhone 13 Pro/15.4.1 implementation profiles. Compatibility beta 1 adds matching APTransport, MediaExperience, AirPlaySender and CarKit paths based on the 20A357 report and static inspection; the earlier iPhone 8 Plus/iOS 16.6 profiles remain.
- Native operation on the tester's iPhone 14 Pro Max, other arm64e devices, or every Dopamine version. Host compilation and package tests cannot demonstrate device injection, pointer authentication or actual CarPlay behavior.
- RootHide-native runtime path/dependency/injection adaptation. Its different layout is a separate case from this tester's standard Dopamine report. Existing .jbroot inspection is diagnostic only.
- Rootful, 32-bit or deployment below iOS 15.4.1. Those require additional packaging/runtime work; removing a version label does not change binary or dependency requirements.

## How coverage should expand

1. Detect runtime capabilities, architecture and loaded framework identities automatically. The reporter supplies model/build context, observed media-framework identities inside mediaserverd, and independent CarKit/carkitd inspection without a manual build-number questionnaire.
2. Prefer stable exported APIs or runtime introspection where available. When a private hook remains necessary, use verified implementations selected by actual framework identity and validated instructions, not a broad model-name assumption.
3. Validate pointer authentication, structure layout and lifecycle behavior for each implementation family. An unknown framework must not receive a guessed offset.
4. Verify loader/constructor behavior, a fresh USB-free native session, locked app switching, navigation input, audio routing and recovery on representative devices/jailbreaks before expanding the tested coverage claim.
5. Keep the working published release and original project/state intact while this candidate is developed. The package builder does not install on a phone or publish a release. Diagnostic builds are published separately.

Beta 8 combines the full beta 7 receiver and diagnostic export with an additional verified firmware profile. Installation on a newer iOS release does not imply that its private implementations are supported. iOS 17.6.1 and RootHide-native operation remain outside this build. The path toward broader coverage is additive implementation-family profiles and packaging appropriate to each jailbreak layout, followed by representative device acceptance; a universal compatibility claim is not established. See BETA-8.md.

Sources: [Theos arm64e deployment](https://theos.dev/docs/arm64e-deployment), [Theos rootless packaging](https://theos.dev/docs/rootless), [RootHide developer documentation](https://github.com/roothide/Developer/blob/main/roothide.md).
