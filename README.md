# CarDash HTTPS transport prototype

https://cfluid101.github.io/cardash-beta/option1/?v=https2

HTTPS2 adds compact overlay controls, bounded touch handling, independent
heartbeats and stream recovery. Matching experimental phone backend required.
User testing confirmed the HTTPS1 canvas path displays native CarPlay in Drive;
HTTPS2 performance and endurance in the Tesla still require validation.

Only static interface files are hosted here. All native video, audio, input,
controller tokens and diagnostics stay on the browser-to-local-phone connection.
No cloud media relay, domain purchase or setup code is required. First loading
needs internet access. Bluetooth/phone output remains the default.

The readable JavaScript source is included directly. HTTPS1 scripts remain for
cached older pages; HTTPS2 scripts have immutable content-addressed filenames.
See LICENSE. No phone data, logs, credentials or packages are in this branch.
