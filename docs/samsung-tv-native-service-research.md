# Native collector supervision

Research and hardware validation: 2026-09-21, on the configured QN90A and S90D.

**A native service works on both TVs:** the system systemd manager creates a private
read-only VDFS view with `BindReadOnlyPaths`, then runs our ARM executable as owner
UID 5001. The native process survived bootstrap exit, restarted after a forced
failure, and stopped cleanly. Its maps contained no managed runtime.

This corrects the initial conclusion that executable signing was the only remaining
path. Signing is required on the ordinary writable path we tested, but the
read-only path is accepted on these exact firmwares. A C collector now passes
bounded ingestion trials on both TVs. Production still uses the signed managed
service; each trial restores it after verification.

## Hardware evidence

| Test | QN90A | S90D |
| --- | --- | --- |
| Owner manager runs trusted `/bin/true` in a transient unit | Exit 0 | Exit 0 |
| Custom ELF on writable storage, including inside a verified developer-signed TPK | `203/EXEC`; direct execution `EPERM` | `203/EXEC`; direct execution `EPERM` |
| Application launcher starts marker-enabled native package | Launch acknowledged; no marker; kernel signature rejection | Same |
| Fresh ELF through isolated read-only VDFS bind, executed as owner | Expected exit 42 | Expected exit 42 |
| Owner-manager unit with `BindReadOnlyPaths` | `203/EXEC` | `203/EXEC` |
| System-manager unit with `User=5001` and `BindReadOnlyPaths` | Expected exit 42 | Expected exit 42 |
| Native resident probe after temporary bootstrap cleanup | Running, PPID 1, UID 5001 | Running, PPID 1, UID 5001 |
| Resident process maps | No CLR/hostfxr/hostpolicy | No CLR/hostfxr/hostpolicy |
| Forced SIGKILL of only the probe unit's main process | New PID, `NRestarts=1`, running | Same |
| Explicit stop and cleanup | PID 0, inactive, transient unit removed | Same |

The resident probe had approximately 220/224 KiB RSS when inspected. This is a
minimal idle program with no TLS, parsing or sampling; it is **not** an estimate
of the eventual collector's memory use or a fair collector benchmark.

## Actual collector validation

The [C collector](../research/native-telemetry/collector/README.md) sent real samples
to the existing NAS receiver on both TVs without changing receiver code, identity,
credentials, certificate pin or chart history. The same ARM binary served both.
Each trial drained the managed sampler's lease before starting native collection.

| Device | Native RSS during sampling | Preceding managed RSS snapshot | Native CPU / one core |
| --- | --- | --- | --- |
| QN90A, two trials | 2.98–3.88 MiB | 23.93–24.29 MiB | 0.022–0.097% |
| S90D | 3.00–3.04 MiB | 22.77 MiB | 0.085% |

Each trial records eight receiver samples spanning approximately 70 seconds,
not long-term peak bounds. RSS describes each collector process, not total
TV memory; the old managed service stayed available for rollback. Native samples
matched the process's session and status, with zero send failures. Process maps
contained no CLR, and all four counter sources remained available.

The worker runs as `User::Pkg::MiniTelemetry`, preserving the existing pairing
directory's isolation. No credential migration or SMACK policy change was needed.
The native process uses the same private configuration, public preference format,
RAM status location and process lock as the managed sampler. Code lives in a
root-owned directory mounted read-only for the worker.

Eleven Linux integration tests cover real TLS pinning, connection reuse, receiver
validation, deadlines, backoff, settings, locks, signals and malformed inputs.
The project Python suite passes 150 tests, including five recovery-script tests.
The ARM build requires at most `GLIBC_2.25` on TVs with libc 2.30; firmware curl
and OpenSSL libraries remain dynamic, while json-c is linked statically.

An initial QN90A restoration rehearsal exposed two separate constraints: the
unsigned shell script also requires the read-only view, and package-labeled
processes cannot execute the `User::Shell`-labeled app launcher. The corrected
rollback uses an ordered pair of units: package-labeled marker restoration,
then a `User`-labeled Hub relaunch. S90D passed that complete restoration path.
The first QN90A trial used a guarded SDK relaunch; a second QN90A trial passed
automatic TV-timer restoration while the host only observed. Each trial retains
its evidence and recovery journal, then removes its staged code and pairing copy.

## Why the first attempt failed

Both kernels rejected `/opt/usr/apps/MiniNativeProbe/bin/probe` as unsigned, despite
successful per-TV developer-signed package installation and matching installed
hashes. QN90A logged UEP verification failure; S90D logged `Verification fail`.
Package signatures and executable verification are separate checks. A launch PID
alone does not establish that `main()` ran.

The ELF was ARMv7 soft-float, required only `GLIBC_2.4`, and used the existing
`/lib/ld-linux.so.3` loader. `/tmp` was not mounted `noexec`; normal executable mode
and ownership were present. These were not the cause of the rejection.

Samsung's older published
[UEP implementation](https://github.com/mmajchr/SamsungKernelSecurity/blob/main/sfd/uep/SfdUepHookHandlers.c)
contains a read-only VDFS classification and an unsigned-file exception for that
classification. This source is historical, not the exact deployed kernel. The
hardware tests above establish that a corresponding read-only execution path works
on our two firmwares. The existing S90D screensaver's read-only library overlay was
another reason to investigate this distinction.

A file mode such as 0555 is not a read-only mount. The successful process's own
`mountinfo` showed its executable directory mounted `ro` over VDFS, while the
backing `/opt` filesystem remained writable. The files were fresh copies, avoiding
reliance on the earlier rejected inode. No security module was disabled, no kernel
was patched, and no vendor executable or trust store was replaced.

## Revised structure

`privileged bootstrap → systemd system unit → unprivileged native collector`

Hub settings would reach the collector through a narrow, caller-validated control
channel. Bootstrap creates the unit and exits; systemd owns lifetime and restart.
The collector uses ordinary `main()` and Unix signals. It does not need
`service_app_main()`, a window or a .NET host. That native Tizen lifecycle API was
never itself a .NET dependency; the original C# service host introduced the CLR.

The tested unit properties are captured in
[`probe/lifecycle.service`](../research/native-telemetry/probe/lifecycle.service).
They include:

- `User=5001`, `Group=100`, `SmackProcessLabel=User`;
- `BindReadOnlyPaths` for a dedicated root-owned directory under `/opt`;
- `Type=simple`, `Nice=10`, bounded `Restart=on-failure`;
- a probe-only runtime timeout and the native probe's own 45-second deadline.

The system manager is a meaningful change from the original owner-manager proposal.
The owner manager accepted the read-only property but still failed execution in our
test. The system manager successfully prepared the execution view. The worker itself
ran unprivileged and belonged to the dedicated systemd unit's cgroup.

Production code should live in immutable version directories owned by root, with
reviewed hashes and no owner-writable backing alias. Update by staging a new version
and switching the unit after validation; do not modify an executing version in place.
The read-only service view does not protect a backing file from another process
that has permission to modify it.

## Startup capability boundary (follow-up)

The signed application and the SDK shell have different authority. On both TVs,
the installed telemetry service has **zero permitted, effective, inheritable and
bounding capabilities**. The SDK-launched `/usr/bin/dotnet` can prepare a private
mount namespace because its caller supplies the required inheritable capability;
that does not carry over to a normally launched application.

The owner systemd manager also lacks `CAP_SYS_ADMIN`. A disposable owner unit
running the signed .NET host reached our launcher, but `unshare(CLONE_NEWNS)`
failed with `EPERM` on both TVs. Asking that manager to apply the existing telemetry
package label failed with systemd status **236/SMACK_PROCESS_LABEL**. Neither
attempt started a native worker. All probe files and units were removed.

Consequently, `Hub → ordinary owner unit → short-lived .NET mount wrapper` is not
a working common startup solution on these firmwares. The remaining requirement
is an authorized privileged boot entry that prepares the system unit. Existing
S90D integration alone does not solve QN90A startup. Production remains managed;
no native reboot/standby acceptance is claimed.

The separate [Netdata feasibility trial](samsung-tv-netdata-native.md) does not
remove this startup requirement. Both Netdata and our C collector use the same
read-only execution view in their successful system-manager trials.

The [boot and restart decompilation follow-up](samsung-tv-native-autostart.md)
traces QN90A's unit loader, D-Bus generator and boot scripts. It confirms the
shared systemd supervision design but does not establish a persistent privileged
QN90A boot entry. Crash restart, cold boot and hang recovery are separate checks.

The [offline container follow-up](samsung-tv-native-autostart.md#offline-follow-up-registration-and-query-safety)
confirmed initialization-time zone discovery and additional template-launcher
permission gates. It also found a dispatcher input-contract defect that strongly
explains the earlier query incident without proving crash attribution. No usable
custom-container registration path or native boot acceptance was established;
do not retry `GetZoneList` or use `ZoneLock`/`ZoneAttach` as substitutes.

The [protected firmware capture](samsung-tv-native-autostart.md#protected-firmware-capture-actual-lxc-discovery)
recovered QN90A's exact LXC library and confirmed `/zone` as its root-process
discovery default, with `/etc/lxc/lxc.conf` as the global override. The override is
absent from the firmware catalog; both paths belong to the read-only filesystem.
This closes the direct writable-container-directory lead for the captured layout.
All capture resources were removed, zone-manager did not restart, and both managed
production sessions continued. A persistent QN90A bootstrap remains unresolved.

The [SDK activation follow-up](samsung-tv-native-autostart.md#sdk-boot-activation-and-tv-local-access)
traced the existing privileged SDK service and its file capability inheritance.
Its vendor TCP policy requires the configured development-host IPv4 address;
IPv6 is denied, and the child terminal helper is not an independent privilege
source. This closes the proposed signed-relay → TV-local SDK bootstrap under
the current settings. No daemon or policy changes were made; both managed
collector sessions stayed healthy during that capture.

The later [host-bootstrap pilot](samsung-tv-native-autostart.md#host-bootstrap-pilot-and-sdk-recovery)
implemented boot-aware reconciliation and passed QN90A PID preservation and local
native crash restart using an isolated receiver. Its software reboot returned
managed production telemetry, but SDK connections failed, preventing native
postboot startup. The owner's subsequent reboot restored SDK access; the canceled
pilot was removed and both production streams verified fresh. This implements
the fallback experiment without establishing reliable autonomous bootstrap.

The [Luna startup review](samsung-tv-native-autostart.md#autonomous-path-review-with-luna-subagents)
ruled out arbitrary boot commands through the persistent loader list. A separate
zero-capability QN90A trial reached sealed-memory-file `fexecve`, which failed with
`EPERM` and an explicit kernel unsigned-file rejection. A separate no-mount
`CLONE_NEWUSER` probe returned `EINVAL`; the exact .NET plugin clears capabilities
on its default path and gates alternative modes on platform privilege. The package-image service
is a real privileged mount path, but its registration, executable admission and
boot lifecycle remain unproven. Both managed production sessions continued and
all trial resources were removed; there is still no native startup acceptance.

## Remaining implementation work

The [package-image follow-up](samsung-qn90a-package-images.md) additionally tested
read-only ext4 and SquashFS images on QN90A. Mounting succeeded, but the same native
probe failed with `EPERM` and explicit unsigned-file UEP rejection on each. This
does not extend the VDFS result to other read-only filesystems or establish a USB
bootstrap. Both units, image files and loop associations were removed; production
sessions continued unchanged.

1. **Privileged bootstrap after reboot.** The experiments use the existing bounded
   administrative transport, including its temporary managed helper. It proves
   there need be no resident CLR; it does not yet remove every launch-time .NET
   dependency. Transient units disappear after reboot. QN90A's system cache is
   read-only, so S90D's existing persistence mechanism cannot simply be copied.
2. **Hub control.** An ordinary packaged Hub/relay must not be assumed to have
   permission to create system services. Implement a narrowly scoped control path,
   validate the caller, and preserve first-Hub-launch behavior. Access from the
   existing `MiniTelemetry.Start` package label has not been verified.
3. **Production packaging.** The native sampler and private pairing access now
   pass on both TVs using the existing package security label. Integrate immutable
   native versions, dependency checks, updates and rollback into normal setup only
   after startup/control integration is ready. `tvsetup.native_trial` is explicitly
   experimental and does not change deployment defaults.
4. **Lifecycle acceptance.** Verify repeated Hub entry, real telemetry ingestion,
   standby/wake and cold reboot separately. The initial probes did not reboot
   either TV; the later host-bootstrap reboot failed native startup acceptance.
   Measure the actual collector before claiming memory or CPU improvements.

The current service remains the rollback path until all four boundaries pass.
Moving the existing managed collector under systemd alone would not remove its CLR.

## Earlier static findings

Both TVs already run systemd 244 and an owner manager. The owner bus is available
through `kernel:path=/sys/fs/kdbus/5001-user/bus`; the conventional Unix socket was
absent on the inspected sessions.

QN90A decompilation established:

- `manager_startup` at `0x00090438` skips the system-wide `oneservice_setup()` for
  user-manager scope; read-only system cache alone does not rule out user services.
- `method_start_transient_unit.lto_priv.0` at `0x000b600c` authorizes and queues
  transient units; `transient_unit_from_message` at `0x000b5c8c` constructs them.
- `sd_bus_query_sender_privilege` at `0x000b8734` in the shared library includes a
  matching-UID path for a non-root manager. Socket access and SMACK still matter.
- `lookup_paths_reduce` at `0x00108ce8` removes nonexistent paths. A short observed
  `UnitPath` does not prove missing XDG/transient paths are unsupported.

Upstream systemd v244's
[transient-unit implementation](https://github.com/systemd/systemd/blob/v244/src/core/dbus-manager.c)
provides reference semantics; Samsung hardware observations take precedence.

## Evidence and cleanup

All raw dumps, signed packages and logs remain in the private research store.
Addresses are Ghidra addresses, not live ASLR addresses.

- Static exports: `qn90a/systemd-native-service-{review,details,paths,auth}.c`.
  Projects: `QN90A_ServiceReview_20260921` and `QN90A_Saver`.
- S90D config: `dumps/20260919T220353Z/extracted/startup-and-policy/`;
  captured unit state: `analysis/s90d-boot-units.json`.
- Experiment journals and results: `native-service-probe/{qn90a,s90d}/`, including
  `readonly/`, `readonly-unit/`, `lifecycle/result.json` and final health summaries.
- Collector build and library evidence: `native-service-probe/build/` and each
  device's `collector-inventory/` and `collector-smoke/` directories.
- Initial ingestion trials: `setup/runs/20260921T164308Z-647ec2b6` (QN90A) and
  `setup/runs/20260921T165325Z-81bf967d` (S90D). Both restored managed ingestion.
- QN90A automatic recovery trial: `setup/runs/20260921T165622Z-33cca4b3`.
  The native worker's deadline ended collection; TV-side timers restored the
  marker and relaunched Hub, and fresh managed ingestion resumed without a host
  restore command. Cleanup passed and the journal is `rolled-back`.
- Native collector SHA-256:
  `0bd3a69df5243a0433f8cc47dc63ce2cb96746301dc8a7fa76663620ade80613`.
- Writable-path kernel rejections: sessions `20260921T160121.591928Z` (QN90A)
  and `20260921T160133.883486Z` (S90D), both `setup-root-operation`.
- Read-only direct execution: sessions `20260921T160724.628140Z` (QN90A) and
  `20260921T160731.508458Z` (S90D), both `setup-root-operation`.
- System/owner manager comparison: sessions `20260921T160845.846529Z` (QN90A)
  and `20260921T160854.921591Z` (S90D), both `setup-root-operation`.
- QN90A systemd SHA-256:
  `b8a37a192dec9526a5a4e90b3afb611679fab92f881fcd029c2bf76d15602a60`;
  shared library:
  `9aeacb10c444f948dc7e57a9465f1f8d7bdd5ad9fd57a0fdd541764b85c61a53`.
- Original execution probe SHA-256:
  `08f6c365f0767c635acf9cfb40083d808203f11e6a15139608a708fd76104ffa`.

The dedicated package, transient units, temporary mounts, staged payloads and
probe-only TV backup directories were removed. The production collector and its
configuration were preserved; source is in
[`research/native-telemetry`](../research/native-telemetry/README.md).
See [telemetry operations](samsung-tv-telemetry.md) for the deployed architecture.
