# Renderer research

Source review dated November 7, 2026. These findings describe implementations and limitations; they do not establish behavior while a vehicle is moving.

## Original CarDash and native CarPlay

Original CarDash displayed its home screen with HTML and CSS. Its `layoutHome()` calculated columns from available width and allowed up to three rows (`www/app.js:146–163`). That responsive grid was separate from Apple's native CarPlay interface.

For app display, the original daemon captured the iPhone display, encoded individual JPEG images, and sent them as binary WebSocket messages (`src/daemon/CDMirror.m:107–133`, `CDServer.m:396–405`). The browser used `createImageBitmap()` and a 2D canvas with uniform scaling (`www/app.js:424–463,574–588`). This was an image sequence over WebSocket, not multipart MJPEG.

V3 receives the native CarPlay H.264 display stream. Its video-element renderer uses MediaSource and fragmented MP4. Native display layout must therefore be negotiated with the iPhone; stretching the finished video changes proportions without rearranging icons. The adaptive-layout work advertises the viewport aspect ratio and preserves source proportions in the browser.

## Tesla Android source findings

The reviewed [frontend revision](https://github.com/tesla-android/frontend/tree/34763a62819a1dedad9d3eb62f1e175f2659091f) contains separate WebCodecs and legacy Broadway rendering paths. Browser API availability, codec support and renderer choice are distinct requirements; using H.264 alone does not establish compatibility or performance.

The examined WebCodecs path sends decoded frames to a WebGL canvas (WebGL2 with a WebGL fallback). The article's WebGPU description is not evidence that this particular source revision uses WebGPU. The original image/canvas transport explains why its IP-address workflow did not require WebCodecs.

The [WebCodecs specification](https://www.w3.org/TR/webcodecs/#videodecoder-interface) marks `VideoDecoder` as a secure-context interface. A Chrome localhost test is not evidence that a remote HTTP IP address has the same API access. Browser capability, decoder support, and device-specific behavior must be checked separately. These findings do not make purchasing a domain a prerequisite for CarDash's retained H.264/MediaSource renderer.

The legacy Broadway `Decoder.js` and `avc.wasm` match [upstream Broadway](https://github.com/mbebenita/Broadway/tree/b8f055f5ad709db3c5042cff5938237ac0e1b5d5) byte for byte. Its documented and source-level limitations include CABAC and weighted prediction, and its SPS parser lacks High-profile extension parsing. It is therefore not a compatible drop-in decoder for the observed native CarPlay codec `avc1.64001f` (High profile). Changing a codec label does not change the encoded stream. See the [decoder documentation](https://github.com/mbebenita/Broadway/blob/b8f055f5ad709db3c5042cff5938237ac0e1b5d5/README.markdown#encoding-video) and [SPS parser](https://github.com/mbebenita/Broadway/blob/b8f055f5ad709db3c5042cff5938237ac0e1b5d5/Decoder/src/h264bsd_seq_param_set.c).

## Verification limits

The reviewed car-session logs showed browser frame drops while native frames continued arriving. They contained no gear-state telemetry and did not establish the precise cause of the reported freeze. No Tesla Drive test was performed for this research. Desktop and parked-device tests do not verify moving-vehicle behavior, and this note provides no method for bypassing vehicle restrictions. Bluetooth playback was separately confirmed by the user.
