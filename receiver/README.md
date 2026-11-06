# Native CarPlay receiver research

This is the isolated receiver prototype tested on an iPhone 8 Plus (`iPhone10,2`, iOS 16.6 `20G75`, Dopamine rootless). It starts a real CarKit session, authenticates the receiver, receives the phone's encrypted native H.264 screen, remuxes it to fragmented MP4, and sends encrypted HID touch reports back to the native session. There is no synthetic-video fallback in the live server.

The receiver currently runs on the Mac. SSH forwards the phone's loopback TCP control, events and video ports to it. A separate, bounded arm64 probe on the phone issues the native request and supplies the local UDP timing endpoint. This is **not a standalone iPhone DEB or Tesla release**. The existing CarDash product, packages and settings remain separate.

## Local run

Prerequisites: existing USB SSH forwarding, the enrolled SSH key, Node 20+, Python 3, Xcode, FFmpeg/FFprobe, and Chrome for the optional browser test. The driver currently uses this research session's SSH helper and its known-hosts file. It does not discover or trust new devices automatically.

From the `carplay-diagnostics` directory:

```sh
(cd receiver && npm ci --ignore-scripts --no-audit --no-fund)
node --test receiver/test/*.test.mjs
python3 receiver/device/build.py
python3 receiver/run_trial.py 90
```

The driver prints its evidence directory. While the bounded trial is running:

```sh
node receiver/scripts/browser-check.mjs evidence/receiver-live/<printed-run-directory>
```

The browser check starts and closes its own invisible Chrome with a temporary profile. It decodes live native frames, sends a real pointer click through the viewer/HID path, resizes the browser, and saves screenshots and measured frame counters. It does not use the person's signed-in browser profile.

For manual local viewing, open `http://127.0.0.1:46205/#<token>` using the token in the run directory's `control-token.txt`. This token is only for the local research viewer; it does not add pairing codes to the CarDash product. All host listeners and SSH forwarding addresses are loopback only.

## Identity provisioning

`evidence/receiver-identity/identity.json` holds the generated Ed25519 receiver identity and paired controller public keys. It is created with private filesystem permissions and is excluded from Git. The pairing code performs SRP-6a, mutual long-term signature verification, X25519 pair verification, and authenticated ChaCha20-Poly1305 control framing.

The separate accessory-authentication test loads `certificate.p7b`, `identity.pk8` and `certificate.pem` from `evidence/receiver-accessory-identity`. The local trial used the experimental identity bundled in the public DiPlay 0.2.22 APK, checked against that release's SHA-256 manifest. The source tree and any distributable source archive contain **no accessory private key, certificate bundle, APK or paired phone identity**. No Apple binary or authentication check was patched. Do not describe this experiment as authentication-free or as having a newly issued MFi identity.

## Bounds and cleanup

- Device calls are gated to the observed model/build and retained CarKit framework identity; the helper refuses a pre-existing native CarPlay session.
- The device probe has a hard deadline and notices parent loss. It cancels its own request on normal completion; the driver closes owned SSH tunnels, the receiver and its USB logger.
- One control connection, bounded RTSP/TLV/cipher frames, at most two viewers, bounded video capture and per-viewer backpressure.
- A new trial has a new viewer token. The prototype binds only loopback and supports one native session per trial.
- Raw logs, private runtime material and screenshots stay under ignored `evidence/`. `combined.ndjson` includes receiver, native-client and USB-service records. Treat these as private device reports.
- The phone is returned to the existing V2 companion to keep it awake. No respring, original project edit, beta package replacement, or original preference migration is performed.

## Remaining product work

Audio output is not implemented. iOS 16.6 needed the complete CarPlay capability declaration before it exposed a usable native session; the prototype advertises compatible audio formats but does not accept audio streams. This is a research limitation to resolve before a release.

The phone already has CarBridge installed. Waze and the wide YouTube Music surface observed here do **not** establish that our receiver independently replaces CarBridge's arbitrary-app integration. This run did not change those tweak settings.

Locked-phone app switching, Tesla browser playback/network behavior, long-duration thermal/battery behavior, microphone, keyboard, full gesture/multitouch handling, receiver-side resizing and an on-phone receiver port still need work/testing. The native source is iOS 16.6 CarPlay; this does not put the iOS 27 CarPlay runtime onto iOS 16.6.

See `RESULTS.md` for the measured trials and limitations, and `NOTICE.md` for provenance.
