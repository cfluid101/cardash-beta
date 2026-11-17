# Beta 9: component-specific compatibility and failure reports

The user authorized choosing and implementing the best evidence-based method,
building the next beta, retaining existing functionality, and exporting useful
failure logs. Implementation choices below are engineering decisions under that
request; they are not physical-device acceptance claims.

Use independent exact-image adapters for CarKit requests, APTransport lifecycle,
AirPlaySender video ABI/layout and MediaExperience routing. The firmware sweep
on FluidDrive establishes their differences. OS-major switching cannot express
17.0's mixed component families. Unrestricted signature scanning cannot prove
private storage layouts. Retaining only beta 8 profiles would ignore verified
additional evidence. Independent exact profiles fit the existing architecture.

Preserve the original 8 Plus/16.6 path and existing 19E258/20A357 profiles. Add
verified identities and guarded adapters for 19G82, 20A362 arm64, 20G75 arm64e,
21A329 and shared 21G93/21G101 images. Validate new CarKit constructors through
secure archive round-trips and call the matching request ABI. Never claim or
forge mutual-authentication support. Report native rejection.

19A346 transport is identified but blocked before hooks: its unconditional
host release cannot use the middle-layout lifecycle adapter. Lower the native
deployment floor to 15.0 so diagnostics can run there; this is not session
coverage. Standard rootless packaging is retained. RootHide/rootful layouts and
availability of a compatible jailbreak remain independent requirements.

Export a bounded, read-only compatibility summary with observed UUIDs/CPUs,
runtime readiness, stable failure stages and next evidence to collect. Include
startup failures in the existing rotating log. Preserve offline export if the
service cannot start, and never log accessory keys or bearer/session tokens.

Deliver a signed local beta 9 DEB, matching source archive, checksums, profile
provenance and validation results. The user subsequently authorized publishing the beta 9 release and updated viewer URL. No flashing or phone execution is part of this implementation. All firmware stays on FluidDrive.
