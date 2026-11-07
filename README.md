# CarDash V3 beta

Native CarPlay from a jailbroken iPhone to the Tesla browser over Personal Hotspot.

## Current tester release: V3 Beta 5 — HTTPS3

**[Download the experimental DEB](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/com.cfluid.cardash.v3_3.0.0-beta.5-https.3_iphoneos-arm64.deb) · [Tester ZIP](https://github.com/cfluid101/cardash-beta/releases/download/v3.0.0-beta.5-https.3/CarDash-V3-HTTPS3-tester-pack.zip) · [Release and checksums](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3)**

**Open-testing revision 1:** installer model/firmware restrictions are removed. Other rootless arm64 devices can attempt installation; bundled binaries target iOS 16.0+. Actual runtime dependencies and native framework/instruction checks remain. Unmatched native adapters prevent a session from starting. iOS 17.6.1 is unverified, not newly ported. Full interfaces for non-CarPlay apps require separately installed CarBridge on the tested setup.

The project owner reported the November 7, 2026 trial in a 2023 Tesla Model 3 (AMD Ryzen) was working nearly perfectly. That trial used the prior build on iPhone 8 Plus / iOS 16.6 / 20G75. The current download is the revised experimental package, version `3.0.0~beta.5+https.3.open.1`; the original tested package remains available in the release rollback archive.

## Quick start

1. Install the DEB using Sileo or another dependency-aware package manager.
2. Open **CarDash V3** and complete **Prepare CarPlay** once if setup is not already complete.
3. Connect the Tesla to the iPhone Personal Hotspot and open the **[HTTPS3 viewer](https://cfluid101.github.io/cardash-beta/option1/?v=https3)**.
4. Enter **`http://100.99.10.2:8890/`**, allow Local Network Access, then **Connect → Start**.
5. Keep Audio on **Device output** for the phone's selected Tesla Bluetooth route. Browser audio is optional.

Read the **[tester guide](docs/HTTPS3-TESTER-GUIDE.md)** for requirements, the 20–30 minute test checklist, diagnostics and rollback. Microphone/Siri voice input is not implemented. There is no setup code; the first unlock after reboot is still required.

GitHub serves static viewer files. Video and controls travel directly to the local iPhone, without a cloud media relay.

[Source and validation](https://github.com/cfluid101/cardash-beta/releases/tag/v3.0.0-beta.5-https.3) · [Historical V1 instructions](docs/LEGACY-V1.md) · [All releases](https://github.com/cfluid101/cardash-beta/releases)
