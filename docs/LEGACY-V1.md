# CarDash beta

CarDash is a CarPlay-style dashboard for your car's web browser. Your jailbroken iPhone serves it over its own
Personal Hotspot. It was built for the Tesla browser, and any device on the hotspot can open it.

## Download CarDash 1.0.2 beta

- **[Install on the iPhone (.deb, 164 KB)](https://github.com/cfluid101/cardash-beta/releases/download/v1.0.2-beta/com.cfluid.cardash_1.0.2_iphoneos-arm64.deb):**
  open this link in Safari on the iPhone, then open the download in Sileo, Zebra or Filza.
- **[Tester pack (.zip, 167 KB)](https://github.com/cfluid101/cardash-beta/releases/download/v1.0.2-beta/CarDash-1.0.2-beta.zip):**
  the same `.deb` plus `README.txt`, which has the full instructions and the checklist of what to report.

**Requirements:**
- A rootless jailbreak on iOS 15 or later, such as Dopamine or palera1n rootless.
- PreferenceLoader.
- Personal Hotspot.

**Quick start:**
1. Install the `.deb`, then turn on Personal Hotspot and connect your car or device to it.
2. Open CarDash in the browser:
   - **Tesla:** `http://100.99.10.1:8765/` (Tesla's browser blocks private addresses such as 172.20.10.1)
   - **Phones and tablets:** `http://172.20.10.1:8765/` (the Tesla address works too)
3. Choose apps in **Settings → CarDash**.
4. If something doesn't work, open `http://127.0.0.1:8765/status` in Safari on the CarDash iPhone and send a
   screenshot.

> **Security:** anyone connected to your hotspot can see and control your iPhone through CarDash. Use a strong
> hotspot password.

This is a beta and not real CarPlay. Use it at your own risk. Older versions are on the
[Releases](https://github.com/cfluid101/cardash-beta/releases) page.
