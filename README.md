# CarDash HTTPS transport experiment

Static frontend for the isolated option 1 prototype. Not a production release.

https://cfluid101.github.io/cardash-beta/option1/

The browser downloads these interface files over HTTPS, then connects directly
to a local iPhone service after local-network permission. GitHub does not relay
CarPlay frames, touch events, audio, controller tokens, or device diagnostics.

Requires the matching experimental phone backend. Tesla browser compatibility
and navigation display updates in Drive are not yet verified. Bluetooth audio
remains the default phone output. No offline startup guarantee is made.

JavaScript source is included directly in this branch. See LICENSE.
