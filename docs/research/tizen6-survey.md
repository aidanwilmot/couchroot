# Tizen 6 startup research: ranked points of interest

2026-09-21. Target: QN90A, firmware `T-NKM2AKUC-2301.1`, Tizen 6,
Linux 4.1.10. Three subagents reviewed upstream boot/security code, package
trust, and author-maintained TV projects. The primary agent compared their
findings with existing device captures. The initial survey made no TV connections.
A subsequent guarded applicability pass inspected live namespaces, installed and
removed an isolated diagnostic package, and captured broker binaries. Neither TV
was rebooted. Native boot acceptance remains open.

**SharedRO exists on QN90A, but ordinary .NET applications do not retain its
read-only view.** Both a UI app and service app confirmed this on hardware.
It therefore does not remove the bootstrap requirement for the current managed
launch path. The broker audit also excludes direct use from that .NET identity;
its constrained Node/WSA image rules are a narrower remaining internal-storage lead.
See the [existing hardware results](native-service-research.md)
and [package-image exclusions](../devices/qn90a/package-images.md).

## 1. Launcher-managed SharedRO view — .NET applicability checked

Upstream Tizen 6 `security_manager_prepare_app` configures a package namespace
before dropping application privileges. Its `setupSharedRO` routine mounts
the user's `.shared` tree read-only and can restore the owning package's subtree
to writable access. Paths derive from the effective user's platform configuration.
This is different from asking an ordinary application to mount something itself.
[Tizen 6 M2 release-pinned client source](https://git.tizen.org/cgit/platform/core/security/security-manager/tree/src/client/client-security-manager.cpp?id=6e1aefe80bce0fd794a1bdd33f5f4f17d2fb96d0#n822)

The mount helper uses a bind followed by a read-only bind remount. It does not
explicitly add `MS_NOEXEC`, but the actual inherited mount flags must still be
checked. [Pinned mount helper](https://git.tizen.org/cgit/platform/core/security/security-manager/tree/src/common/mount-namespace.cpp?id=71efeb277c1d9e2d61d84941dce44c5f2f4173e7)

The exact QN90A commons library subsequently confirmed those flags:
`bindMountRO` passes `0x1001` (`MS_BIND|MS_RDONLY`), then `0x1021`
(`MS_BIND|MS_REMOUNT|MS_RDONLY`); `bindMountRW` passes `0x1000` (`MS_BIND`).
Capture SHA-256 is
`f054ab7f8115e224060d18f34ff2170d7420c7d581241ef3a5012dc6cf446cee`.
This confirms the helper implementation, not that every app calls or retains it.

The exact QN90A client library was already captured in completed run
`20260921T201456Z-cad5946f`: 112,764 bytes, SHA-256
`37e9d6ba1b63d2807720cedc9f90aa026d736fe70cdcd3a92d4712594a340a2b`.
An exact control-flow follow-up recovered its previously uncreated Thumb callback
at `0x44cbbbf0`: application/group preparation precedes SharedRO setup, and the
label/capability drop follows it. The routine saves the package's own subtree,
binds the shared root read-only, then restores the owning subtree writable when
enabled. Its shortcut tests `access(W_OK) == -1` without checking errno; a
permission denial can therefore skip preparation even on a writable mount.

The live applicability results are:

| Context | Actual executable-path view | Consequence |
| --- | --- | --- |
| Existing Web Hub | `.shared` is a read-only bind on VDFS, with no `noexec`; backing superblock remains writable | The platform mechanism is real in this context |
| Existing managed telemetry service | Appzone masks; `.shared` has no separate mount and is covered by writable `/opt` VDFS | Current service does not receive the needed view |
| Isolated normally signed .NET UI app | UID 5001, its package label, all capability sets empty; probe path on writable `/opt` VDFS | Probe skipped execution as designed |
| Isolated normally signed .NET service app | Same security state and writable probe-path view | Probe skipped execution as designed |

The exact .NET startup code explains this difference. Its ordinary `dotnet` branch
enters Samsung's `appzone` before managed entry and clears capabilities. The
inspected startup bodies do not prepare SharedRO afterward. The plugin's only
internal `isServiceApp` caller affects hybrid-AOT notification; it does not select
a different mount namespace. Changing the manifest component type alone is not a
solution. This does not rule out every alternative Web/native launch design.

The diagnostic used a separate `MiniSharedRO` package and a unique, root-owned
shared-tree directory containing only the previously reviewed native marker.
It performed no mounts and had no credentials or network behavior. Both managed
entry points reported their own mountinfo before the execution gate. **No native
execution was attempted**, so this result is a missing-view finding, not a new
UEP rejection. No production-grade immutable storage/update design was established.
The package, package data, staged marker and remote trial backups were removed.
Neither production collector was stopped, and no vendor namespace was modified.

Run `20260921T220529Z-77def36d` finished `rolled-back` with verified cleanup.
Both receivers advanced 36 samples with unchanged boot/session identities; final
ages were 1.44 seconds (QN90A) and 0.71 seconds (S90D). QN90A's SDK and zone-manager
PIDs/restart counts were unchanged. Read-only observations are in completed runs
`20260921T215559Z-a07c6234`, `20260921T215654Z-e48e1659` and
`20260921T220101Z-6c48bf8f`. Full diagnostic output is retained privately under
`sessions/20260921T221123.004813Z-setup-root-operation/output.txt`; the console
preview was truncated and is not the complete evidence.

The owner systemd manager does not automatically inherit an application's private
mount namespace. Success through the application launcher would therefore require
revisiting supervision, rather than assuming the previous unit works unchanged.

Stop this lead if QN90A omits the relevant preparation, the usable view is writable
or `noexec`, package policy denies access, or native execution still fails UEP.
Calling `security_manager_prepare_app` directly from an ordinary app is not the
proposal; the service's internal authorization and capability boundaries remain.

### Host SDK interruption during the diagnostic

The first install command timed out before package registration or files appeared.
The Mac's existing SDK server had accumulated 1,401 `CLOSE_WAIT` sockets and also
timed out on reconnect. Restarting that local server restored SDK access without
restarting a TV service. Readback verified package absence, installer inactivity,
unchanged vendor PIDs and healthy telemetry before one fresh install attempt.
That install completed, both diagnostic launches ran, and cleanup passed.

This is evidence for a host SDK problem during this run. It does **not** explain
the earlier post-reboot immediate-EOF admission failure or establish host-bootstrap
reboot acceptance.

## 2. Samsung privileged-service broker — caller and operation rules recovered

The CRC-checked QN90A firmware catalog contains `ps_agent`, its system unit and
startup symlinks, `libprivileged-service-client.so`, and a vendor `systemctl.sh`
helper. The previously captured TMK installer calls `PS_Mount` in its non-root
mount branch. These establish a concrete broker/component relationship to inspect.
They do not establish a public mount API, permission for our package, or a way to
register arbitrary services. [Existing TMK findings](../devices/qn90a/package-images.md)

The applicability pass captured all five requested broker files through SDK reads
with matching hashes before/after capture (completed run
`20260921T221208Z-4d127027`). The QN90A unit is a real D-Bus daemon named
`com.safe.ps_agent`, with failure restart; its helper script controls `ps_*`
binaries in the firmware directory. The empty placeholder unit found in an older
local dump belongs to S90D and must not be used as QN90A evidence.
The broker SHA-256 is
`45d1ad06bd626069c0ea44262ec89bb59f3413eaab80d048f710ba681c073a2d`;
the client SHA-256 is
`a86bb55dcab8951ac34abfca75c7bf32c6e5827948fd856f149b3ffa9c954d5b`.

The exact server derives the caller PID from the D-Bus sender, reads its actual
`/proc/PID/exe` and SMACK label, matches both against a credential rule, then checks
the requested command's pattern before dispatch. The captured client wrapper was
independently traced to `dbus_message_get_sender`; this identity is not a request
body field. Static construction of all 227 credential entries was recovered,
covering 51 distinct label/executable pairs. The large constructor exceeded the
decompiler's limits, so its argument associations were reconstructed from exact
disassembly and literal/register/stack propagation instead.

| Caller or operation | Exact restriction | Applicability |
| --- | --- | --- |
| Ordinary .NET app | No credential entry admits its `dotnet` executable identity | Importing `PS_Mount` does not supply mount authority |
| WRT / WRT service | Some labels are broad, but mount rules require packaged-resource paths and `loop,nosuid,nodev,noexec` | Caller identity alone would not yield an executable mount or a read-only bind |
| Node / WSA | Two broad-label `/usr/bin/node` mount rules accept internal packaged `res/tmg.link` or `res/<name>.tmg` to `res/wsa`, with `loop,nosuid` | A remaining package-image lead; these rules omit `noexec` but also do not request `ro` |
| System service control | Eight rules require `System::Privileged` and one of four named tagpro helpers; only start/stop of the tagpro service is allowed | No custom collector service registration or recreation route |

The Node distinction should be preserved rather than treating every Web/runtime
caller as excluded. Further applicability work must establish a legitimate ordinary
package/launcher path to that Node context, its existing TMG mount interface,
accepted filesystem and trust format, actual read-only VDFS behavior, and lifecycle
after reboot. A broker mount from another namespace also does not automatically
give the worker the needed view. Omitting `noexec` is not proof of unsigned native
admission. No broker mount or service-control request was sent during this pass.
The private `ps-agent/credentials-recovered.json` retains every recovered row and
its constructor/literal addresses.

## 3. Partner-conditioned service boot — useful lifecycle lead, separate authority

TizenTube's Tizen 6+ variant requests Web-service `on-boot` and `auto-restart`.
Its author guide calls for partner signing and describes a startup delay after
cold boot. This is concrete project evidence for a certificate-conditioned
app-startup path, not hardware proof on QN90A 2301.1.
[Pinned manifest](https://github.com/reisxd/TizenTube/blob/893b663d35efa558d8bdf9f54f0c4f9a31ab6a07/standalone/config.xml),
[pinned guide](https://github.com/reisxd/TizenTube/blob/893b663d35efa558d8bdf9f54f0c4f9a31ab6a07/docs/README.md)

Upstream Tizen 6 AMD enumerates boot-enabled installed service applications and
launches them with their application UID. It supplies lifecycle, not root or
mount capability.
[Pinned boot manager](https://git.tizen.org/cgit/platform/core/appfw/amd/tree/src/lib/amd_boot_manager.c?id=fa816bee5f1b703aff6d4f0f7dd41e306f6a966a)

Next: compare exact firmware handling of Web-service startup flags and recognized
certificate privilege levels with our public TPK trial, whose `on-boot` flag was
rewritten false. A tool option named Partner Signing is not proof of recognized
privilege. This may provide an ordinary boot observer or become useful alongside
SharedRO; it does not independently solve the privileged bootstrap.

## 4. TMK filesystem and native-file trust — narrow the questions

The public Tizen 6 installer includes normal package signature validation in its
mount-install transaction. Security registration associates application policy;
`RegisterTrustAnchor` handles application certificate trust. Neither establishes
kernel UEP signing of a native executable.
[Pinned installer](https://git.tizen.org/cgit/platform/core/appfw/app-installers/tree/src/common/installer/app_installer.cc?id=30df3bb81d9c1e08c1d3e5aa7d4ed7977749842b),
[signature step](https://git.tizen.org/cgit/platform/core/appfw/app-installers/tree/src/common/step/security/step_signature.cc?id=30df3bb81d9c1e08c1d3e5aa7d4ed7977749842b),
[certificate trust step](https://git.tizen.org/cgit/platform/core/appfw/app-installers/tree/src/common/step/security/step_register_trust_anchor.cc?id=30df3bb81d9c1e08c1d3e5aa7d4ed7977749842b)

The exact vendor TMK mount uses filesystem autodetection. A legitimate specimen's
filesystem, image authentication and postboot mount restoration remain unknown.
The existing ext4/SquashFS failures therefore rule out a mount-only explanation
for those formats, not every possible TMK format. The firmware catalog includes
`mkfs.vdfs`; that alone does not prove developer-generated VDFS images are accepted.
Obtain format/authentication evidence before another image-installation trial.

`libkUEPUser.so` also exists in the captured root catalog. First determine whether
its exports and callers provide reporting, verification or trust registration.
Its name is insufficient evidence of a signing facility. UEP text in the captured
installer executables was their own signature trailer, not an admission API.

Samsung separately documents a Seller Office partner process for signing bundled
native `.so` libraries. This is a real vendor-supported inquiry if a hybrid
architecture is acceptable, but does not establish standalone ELF signing or
eliminate the managed runtime.
[Samsung .NET TV FAQ, Q3](https://developer.samsung.com/smarttv/develop/faq/tizen-net-tv.html)

## 5. Host bootstrap — diagnose SDK admission, not just TV presence

The public `samsung-tv-root` project explicitly uses host-reacquired privileges
and installs no TV-side boot service. Its QN90B/Tizen 6.5 compatibility is not
QN90A/Tizen 6 evidence. Its passive SSDP generation tracking is a useful observation
pattern, not a fix for our SDK handshake failure.
[Pinned project limits](https://github.com/chris-ritsen/samsung-tv-root/blob/da63fffd75413290adf26eb226748f199804b8bc/README.md),
[controller lifecycle](https://github.com/chris-ritsen/samsung-tv-root/blob/da63fffd75413290adf26eb226748f199804b8bc/docs/user/CONTROLLER.md)

Samsung distinguishes Instant On from a reboot/power-cycle during developer-mode
setup. Our next useful evidence is still daemon launch/admission state during
a failing boot; a reachable TCP port and fresh telemetry do not establish SDK
readiness. No published exact-firmware fix was found.
[Samsung testing FAQ](https://developer.samsung.com/smarttv/develop/faq/application-testing.html),
[failed local pilot](native-autostart.md#host-bootstrap-pilot-and-sdk-recovery)

## Exclusions and provenance

Flutter's TV support is not evidence of a standalone native entrypoint: its
maintained tooling specifies a C# host for TVs.
[Pinned tooling documentation](https://github.com/flutter-tizen/flutter-tizen/blob/08014cb5b952850fdbf9c72d24540dfaa68eb807/doc/commands.md)
USB/app2sd alone remains insufficient after the ext4 test. TEP here means an
expansion resource package, not the later signage/hospitality Enterprise Platform.
Existing negative results for owner-manager mounts, memfd, user namespaces,
writable native TPK execution and read-only unit search paths remain valid.

Upstream branch names identify reference implementations, not matching TV builds.
The security-manager, AMD and app-installers sources are pinned in the links above;
vendor behavior takes precedence wherever the captured QN90A code differs.
Private reports, source snapshots, capture references, catalog selections and
offline analysis are under `native-service-probe/tizen6-survey-20260921/`.
Firmware bodies, raw evidence and signing material remain outside Git.
