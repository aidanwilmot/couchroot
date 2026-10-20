# Native telemetry

This directory contains the [native collector](../../telemetry/native-collector/README.md) and bounded
hardware probes for replacing the resident managed worker with a systemd service.
It does not change the deployment default. See [firmware findings](../../docs/lab/research/native-service-research.md).

**2026-09-21 follow-up:** native execution and supervision passed on both TVs using
the **system manager**, `User=5001` and `BindReadOnlyPaths` over a root-owned VDFS
directory. The resident probe survived bootstrap exit, restarted once after
SIGKILL, and stopped cleanly, without a managed runtime in its maps. The ordinary
writable-file path remains rejected even inside a developer-signed TPK; the owner
manager's read-only unit attempt also failed. The C collector now preserves the
receiver and pairing contract; privileged boot integration and Hub control remain
unfinished. The follow-up owner-manager launch test lacks mount authority on both
TVs; see the firmware findings before choosing a bootstrap design. Probe-only resources are removed after verification.

The [startup/restart investigation](../../docs/lab/research/native-autostart.md)
separates proven failure restart from the unresolved QN90A cold-boot bootstrap.

- `probe/probe.c`: ARM executable that prints its identity, writes one diagnostic
  marker in its dedicated test package's data directory, and exits with **42**.
  No network access, credentials, background loop or telemetry settings.
- `probe/tizen-manifest.xml`: isolated `MiniNativeProbe` package. It has no boot
  hook, service restart registration or privileges.
- `probe/resident.c`: native signal/lifecycle probe with a 45-second normal-exit
  deadline. No network or file writes. Its idle RSS is not a collector benchmark.
- `probe/lifecycle.service`: fixture matching the successfully tested system
  transient unit. Its extra timeout/restart limit bounds abnormal execution.
- `probe/owner`: disposable managed diagnostic launcher. It drops to owner UID
  5001, uses the kernel D-Bus transport and creates a transient service with a
  five-second runtime limit. This helper itself is not a .NET-free launch solution.
- `probe/build.sh`: build only; requires the ARM soft-float cross compiler and the
  repository's .NET SDK. Builds were checked with Debian bullseye cross GCC.

The owner helper accepts one executable path, `--direct` to inspect the installed
probe's execution error, `--exec PATH` for a direct namespace test, or
`--unit-readonly PATH` for the unsuccessful owner-manager mount test.
It prints systemd's actual `ExecMainStatus`; its process
exit code reports submission, **not** successful native execution. Expected values:
trusted `/bin/true` → 0; native probe → 42; systemd execution failure → 203.
The helper's `User` security label is not the installed telemetry package's label.
Direct execution tests report the executable's exit status; native code returning
42 is the success marker, even though shell conventions treat it as nonzero.

Use the operations workflow's device identity guards, per-device lock and pending
run check. Sign and verify the dedicated TPK through `tvsetup.artifacts`, retain a
journal and package-database backup through `tvsetup.operations`, then verify the
installed bytes. Never replace the production telemetry package for these probes.
Raw evidence, cross-compiled binaries and signed TPKs stay in the private store.

Before a run, confirm the probe unit, staging directories and package are absent,
or reconcile the preceding run. A clean first run must not overwrite an unrelated
package. After collecting results, stop/reset only the probe unit, remove its known
staged files and uninstall only the probe package created by the run. Verify that
production collection remains fresh. No reboot or security-policy change is part
of this initial test.

## Netdata comparison

[`netdata/`](../../tools/netdata-trial/README.md) contains the pinned upstream ARM preparation and
minimal trial configuration. It uses the same guarded transport with a separate
journal and a hard runtime deadline, while normal telemetry continues. It is a
feasibility benchmark, not a production installation or a replacement for the
NAS history store.

`probe/launch/` tests mount setup through the signed .NET host. `OwnerProbe --launch`
starts it through the owner manager, then stops the disposable unit. Its observed
`77` means `unshare` failed; it is not successful native execution. The launcher
has a fixed probe directory and must never be used as a production bootstrap.
