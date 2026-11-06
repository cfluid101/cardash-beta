# 0.1.1: app-to-helper connection diagnosis

## Observed on the phone (user-supplied 0.1.0 log)

- Installer registered the on-demand helper successfully.
- The app could read installation.log; helper-bootstrap.log was empty.
- Every STATUS/RUN connection failed with errno 1 (EPERM). No report or CarPlay request was produced.
- This establishes failure at Unix-socket connect, before the helper command handler or native CarKit code. It does not establish that all helper startup stages worked.

## Investigation

The shipped app signature contained `container-required=true` and `no-sandbox=true`. This had been copied from the HTTP-opening companion rather than the earlier Unix-socket diagnostic app, which did not request a container. Dopamine 2.x grants read/execute extensions for its root and a write extension for its var/mobile directory; readable files under var/jb therefore do not demonstrate unsandboxed IPC. The diagnostic runtime directory is root-controlled under var/jb/var/lib.

Primary references: [Dopamine process check-in](https://github.com/opa334/Dopamine/blob/2.x/BaseBin/launchdhook/src/jbserver/jbdomain_systemwide.c), [TrollStore root-helper entitlements](https://github.com/opa334/TrollStore/blob/main/RootHelper/entitlements.plist), and [Apple XNU socket policy checks](https://github.com/apple-oss-distributions/xnu/blob/main/security/mac_socket.c). These support the permission hypothesis; they do not substitute for this phone's sandbox denial trace.

A controlled macOS sandbox denying network-outbound reproduced the exact 0.1.0 response (`errno:1`) against an existing Unix socket. This reproduces the failure class, not the phone's exact sandbox profile.

## Change

- Device app explicitly signs `container-required=false`; no other device entitlements or native CarPlay profiles changed. Simulator keeps its test data container.
- Connection-error exports now include errno name/description, failing stage, UID/GID, sandbox presence, selected signed entitlements, and socket/directory stat results. These are read-only facts; no general filesystem scan or remote upload is performed.
- Installation requests STATUS once after launch-job registration and records its actual reply. This activates/checks the helper without starting a CarPlay attempt. Failure includes the state of this package's own launch job.
- Helper startup is logged separately from native-request startup. The existing local socket, peer checks, file protections and bounded workers remain in place.

## Verification and remaining boundary

Three IPC regressions failed against the prior implementation/signature, then passed: genuine sandbox EPERM diagnosis, missing-socket diagnosis, and the packaged native entitlement contract. An installer regression fails against the 0.1.0 script and passes with the real host helper, demonstrating STATUS output and no diagnostic report creation. Launchctl/uicache are substituted in that host test; actual device launchd is not emulated. Full local suite: 19 tests plus 11 ABI checks.

The runtime cause on the iPhone is strongly consistent with policy confinement, but the new entitlement's effect is not yet observed on that phone. Keep that distinction in release notes. Fully close the older diagnostic app, upgrade to 0.1.1, reopen and run once, then export the single log even on failure. No original CarDash source/preferences, beta package or connected-device state were modified by this correction.
