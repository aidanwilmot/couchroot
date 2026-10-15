# Agent .NET dependency inventory

Inspected 2026-10-15 after signed 0.7.28 qualification on QN90A and S90D.
This is a source/caller inventory and removal plan, not a native-only qualification.
The deployed managed payloads, SDK rescue utility and runtime remain available.
See [migration status](MIGRATION.md) and [public contract](../CAPABILITIES.md).

Follow-up: the [native SDK recovery utility](../recovery/native/README.md) now
implements the conditional setting contract and has independent-rescue acceptance
on both TVs. The .NET recovery bytes remain unchanged; older private deployment
kits still use them until their callers explicitly adopt the native unit launch.

The [native acquisition pilot](../../native-root-acquisition/README.md) now ports
the bounded setup probe and command runner to C behind an explicit
`root.execute(..., native_bundle=...)` selection. Its small `NativeEntry.dll`
still uses the trusted host to create a private read-only code bind and load the
library. Native acquisition is therefore not yet a .NET removal. Default setup,
allowlisted cleanup, service acquisition and held bootstrap keep their managed
implementations; uncertain native operations never trigger a fallback replay.

## Dependency paths

| Entry point | Required managed path today | Why native selection does not remove it |
| --- | --- | --- |
| Fresh install, SDK maintenance, setup rollback | `Transport.root` → `tvsetup.worker` → `root.execute` → `NamespaceRootProbe.dll` → `RootIdentity.dll` | Setup must acquire root even when no enrolled worker is available. |
| Service start, worker loss, selected-native reacquisition | `agent.js` SDK launch → `SamsungTvArchiveRoot.dll` → `SamsungTvRootAgent.dll` → authenticated held bootstrap | Native is launched only after the bootstrap verifies the existing selection, process absence and retained state. |
| Normal return to managed | `managed-launch.js` → pinned `/usr/bin/dotnet` → `SamsungTvRootAgent.dll` | This is the deliberately retained fallback. |
| Interrupted active return | `agent.js` acquisition → managed bootstrap → `restart-return.js` | Recovery adopts the fresh managed executor under the original return transaction. |
| SDK rescue / maintenance host restoration | Private deployment and acceptance scripts → `/usr/bin/dotnet Recovery.dll set/watch …` → `libvconf` | The independent rescue must work when Couchroot admission is closed or unavailable. |
| Explicit native setup pilot | `root.execute(native_bundle=…)` → `NativeEntry.dll` → `libacquire.so` | The trusted managed host supplies capability entry and the private read-only native-code mount; namespace/archive and command execution run in C. |

The host SDK is separately required by `Builder.build_managed`, generated setup
probes, managed parity fixtures, `scripts/build-native.py` and
`scripts/check-dependencies.py`. `global.json` pins SDK 10.0.301. Device targets
remain `netcoreapp3.1` / runtime 3.1.3 on QN90A and `net6.0` / runtime 6.0.9 on S90D;
these are distinct from the host SDK. Framework, firmware, host and optional
`dotnet-launcher` hashes come from the tracked profiles and private enrollment.

## NamespaceRootProbe and the generated operation

**Callers and build.** [`tvsetup/root.py`](../../../tvsetup/root.py) builds both
`NamespaceRootProbe` and `RootIdentity` for each bounded root request.
[`Transport.root`](../../../tvsetup/transport.py) runs that module through
[`tvsetup.worker`](../../../tvsetup/worker.py) in a private subprocess and saves
its output. Setup `Driver` operations, inspection/backup, rollback, autonomous-root
package installation/readback and research trial transports inherit this path.
`namespace=True` wraps the requested operation in a PID-1 mount-namespace entry
for the specifically supported S90D cache operations. The probe itself always
uses private mounts. QN90A optional-app cleanup substitutes the build-time
allowlisted cleanup source for `RootIdentity`; it is not the generic shell path.

**Responsibilities.** The current probe source is
[`research/namespace-root-probe/Program.cs`](../../namespace-root-probe/Program.cs),
compiled with `QN90A` for that model. It requires the fixed staging path and a
32-bit process, creates a passwd view with exactly one owner UID/GID adjustment,
creates a private mount namespace, makes propagation recursively private and
rejects remaining shared mounts. It binds a disposable verification key, proves
baseline UID 5001, then binds the passwd view and proves UID 0 through the stock
archive launcher. Its child deadline is 30 seconds. Generated `RootIdentity`
prints UID and runs the encoded command only at UID 0, with a 25-second deadline.
The wrapper signs/verifies the disposable archive locally, hashes original system
files and staged artifacts, refuses dirty staging, and cleans only known files.
An uncertain operation is never retried automatically.

**Dependencies and replacement.** Host: Python, selected .NET SDK, OpenSSL and the
pinned SDK transport. Device: Samsung's trusted dotnet host, matching framework,
libc namespace/mount calls, `/proc`, stock `sdbd-tarlauncher`, tar and shell.
Crucially, the trusted runtime makes inherited mount/group capabilities effective;
an arbitrary unsigned C executable is not automatically an equivalent acquisition
entry point. The historical [chain evidence](../../../docs/research/exploit-chain.md)
explains this dependency. A native port needs both equivalent orchestration and a
separately qualified way to enter the required capability context on each firmware.
Do not solve that by relaxing SMACK, changing system passwd/key files or granting
new persistent capabilities as an incidental part of the port.

An enrolled [`AgentTransport`](../../../tvsetup/agent_transport.py) already avoids
this probe for supported operations while a ready worker exists. It cannot replace
first install or recovery when the worker is unavailable, and it refuses namespace
and allowlisted cleanup operations. A small native probe/command runner can replace
the managed logic once the capability entry is established. Preserve the two
identity checks, bounded children, exact cleanup, original hashes and no-replay
semantics; retain the existing path until both-model acceptance passes.

## Recovery.dll

**Callers and build.** [`recovery/Program.cs`](../recovery/Program.cs) and
[`Recovery.csproj`](../recovery/Recovery.csproj) provide the two-framework utility.
The current per-TV installed copies are used by private deployment/acceptance kits,
including the 300-second SDK rescue timers and explicit loopback/external-host
switches. There is no tracked service or tvsetup invocation of `Recovery.dll`,
and `autonomous_root.prepare` does not package it. Its deployment and caller
receipts remain in private state; public documentation should not invent a
tracked installer or expose their paths, addresses or digests.

**Responsibilities.** Root-only `set EXPECTED TARGET 0` or
`watch EXPECTED TARGET SECONDS` changes only `db/sdk/develop/ip` through
`libvconf.so.0`. Both addresses must be canonical nonzero IPv4. `watch` requires
30–600 seconds; `set` requires zero. Already at target is success; a third value
is drift and refuses overwrite. It checks the setter and verifies readback.
Argument/identity failures return 2, operational failures 1, success 0. It frees
the value returned by `vconf_get_str`. The library call is a read/check/write,
not an atomic compare-and-swap. The caller, not this utility, owns systemd timer
identity, boot/firmware/hash checks, SDB restart, journaling and disarm verification.

**Dependencies and replacement.** It needs the dotnet host/framework, libc and
libvconf, plus root with the appropriate device label. It needs no managed worker
or HTTPS service. A small native utility is the lowest-risk first replacement:
use the existing native cross-build conventions, link/load the device libvconf,
strictly parse arguments, preserve bounded delay and result semantics, and test
against a fake library before per-device readback/drift/timer trials. `vconftool`
with shell guards is a possible temporary adapter, but reproducing parsing,
readback and error semantics in shell adds ambiguity. Keep both utilities until
the native rescue independently restores access with the service unavailable.

## SamsungTvArchiveRoot and service bootstrap

**Callers and build.** [`tvsetup/autonomous_root.py`](../../../tvsetup/autonomous_root.py)
always builds and packages `SamsungTvArchiveRoot` and `SamsungTvRootAgent` DLLs,
deps and runtimeconfig files, including when `native_candidate=True`.
[`agent.js`](../service/agent.js) copies their manifest-verified bytes into unique
SDK staging, writes a one-use secret and passwd view, and signs an archive whose
shell payload starts the managed worker on loopback. SDK launch uses a staged
script and a create-once gate; [`policy.js`](../service/policy.js) checks the pinned
runtime/launcher hashes in SDK context before execution. This placement matters
on S90D, whose app label cannot stat all guarded binaries.

**Responsibilities.** [`SamsungTvArchiveRoot.cs`](../payload/SamsungTvArchiveRoot.cs)
accepts only the `archive-root-` package name with 16 lowercase hex digits,
requires effective CAP_SYS_ADMIN and CAP_SETGID, unshares mounts, makes propagation
private, binds the staged key and passwd view, then runs stock `sdbd-tarlauncher`
with the signed archive and `/bin/sh` command. It captures both streams, records
launcher completion, and detaches private mounts on exit. Unlike the setup probe,
it does not perform a baseline identity launch or impose its own child deadline.
Root authentication and readiness are subsequently checked by the service.

**Dependencies and replacement.** It depends on the same firmware-specific trusted
runtime/capability entry as the setup probe, libc mount calls, the stock archive
launcher and shell. Merely translating this class into C does not establish those
capabilities. Even after an acquisition adapter is replaced, `agent.js.prepare`
still starts `SamsungTvRootAgent.dll`; selected-native startup uses that executor
for process/retained-state checks and native launch. A native authenticated bootstrap
must replace that role too, preserving held admission, token ownership, boot/PID
start-time binding, exact staging checks and current transaction recovery. Reuse
protocol and native-launch primitives without turning the bootstrap into an
unrestricted persistent second worker. The managed branch must stay independently
verifiable during the fallback window.

## Removal order and concrete next step

1. Completed: the native Recovery equivalent, fake-vconf/error/delay tests,
   reproducible ARM build and independent rescue on both TVs. Keep the managed
   utility available and migrate individual private rescue callers only through
   their journaled workflows and verified read-only code mounts.
2. The intermediate managed capability-entry bridge and C setup probe/runner
   are implemented in the native acquisition pilot. Preserve the independent
   managed path and explicit opt-in. A fully native capability entry remains
   open; the read-only code bind and trusted runtime cannot simply be omitted.
3. Replace the service archive adapter and held managed bootstrap with the qualified
   native acquisition path. Exercise selected-native service start, disable/enable,
   transport loss and pending-return reconciliation using the existing receipt
   model; broaden interruption boundaries before default selection changes.
4. Audit remaining agent-required setup controls. `Driver.prepare_control` and
   `control_call` still build/invoke `tvsetup/native/Control.dll` for settings,
   home operations and reloads, even over an enrolled agent transport. Separate
   necessary agent installation/recovery calls from unrelated Hub/telemetry work.
   The telemetry `native_bootstrap` pilot is not a root-acquisition replacement.
5. After native-default lifecycle, endurance, reboot and standby qualification,
   retire the managed worker payload and agent-specific build requirements.
   Preserve a verified offline managed recovery release. Do not remove Samsung's
   system runtime or unrelated applications' managed components.

The inventory itself installed no utility; the subsequent native SDK recovery
milestone completed step 1. The acquisition pilot advances step 2 through an
explicitly managed entry bridge. Next, integrate the qualified adapter into
service acquisition and replace the held managed bootstrap while preserving
transaction recovery; keep .NET-free capability entry as a separate open boundary. The
prerequisites delivered by the preceding milestones—immutable selection binding,
fresh runtime receipts, held startup, same-transaction return recovery and operation parity—remain reusable
regardless of the eventual acquisition adapter.
