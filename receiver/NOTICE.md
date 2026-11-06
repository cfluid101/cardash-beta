# Provenance

GPL-3.0-only; see LICENSE.

Protocol declarations and algorithms were adapted from [DiPlay](https://github.com/shihabal3amri/DiPlay), pinned source commit `615b32ce0b40cd0b99ce94ba23a512001553684f` and the verified 0.2.22 source release. Relevant upstream files are PairSetup, PairVerify, Srp6a, AirPlayCrypto, MfiSapAuthSetup, AirPlayInfoPlist, AirPlayHid, NtpClock, ScreenStream, AirPlaySession and CarPlayMediaEngine. DiPlay derives from shilapi/xcertplay. No DiPlay/DiAuto UI implementation is included.

Framing, input, the original MP4 muxer, and synthetic test-only peer were copied from the separately preserved CarDash native-carplay-lab, then adapted for native timestamps, repeated codec configuration, unsigned stream identifiers, event replies and heartbeat packets. `lib/synthetic-peer.mjs` is imported only by automated host tests, never by the live server.

Accessory credentials from the public DiPlay APK are private local research inputs, excluded from this source and distribution. Apple's frameworks remain on the user's device; retained binary evidence is excluded. Public experimental identity availability is not a certification or a guarantee of acceptance on other iOS versions.
