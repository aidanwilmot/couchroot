# Native startup and restart

Exact-firmware investigation, 2026-09-21. Production remains on the managed
collector. The initial pass inspected firmware and decompiled binaries; the
follow-up added a bounded QN90A loader test. A subsequent offline pass verified
zone-manager's discovery path, dispatcher defect and template-launcher permission
checks. A further guarded capture recovered the protected LXC library through
read-only firmware block reads and confirmed its discovery defaults. A subsequent
SDK capture traced its boot activation, TCP admission policy and inherited mount
authority. Those captures did not install a boot hook or reboot either TV. A later
isolated host-bootstrap pilot tested QN90A reconciliation and crash recovery, then
failed postboot SDK acceptance; the owner's subsequent reboot restored access.
The pilot was removed. The earlier vendor zone-manager incident below recovered
automatically. The subsequent [package-image continuation](samsung-qn90a-package-images.md)
traced external and internal image installation and tested read-only ext4 and
SquashFS execution; both mounted, but UEP rejected the unsigned native probe.

**Use the system systemd manager for native process supervision on both TVs.**
Crash restart has already passed hardware tests. Recreating that service after
a full reboot is a separate requirement: S90D has an existing privileged boot
integration, but no equivalent QN90A entry was established by this investigation.

The later [Tizen 6 applicability investigation](samsung-tizen6-research-survey.md)
confirmed SharedRO in the Web Hub's namespace, but isolated .NET UI and service
trials both lost that view on entering Samsung's appzone. SharedRO therefore does
not solve the current managed launch path. The diagnostic was removed, collection
stayed healthy, and native boot acceptance remains unchanged. Exact privileged
broker analysis found no ordinary .NET caller rule or custom system-service
control. Its constrained Node/WSA internal image-mount rules remain a separate
format, trust and lifecycle research lead; they have not been invoked.

## What works, and what remains open

| Boundary | Evidence | Status |
| --- | --- | --- |
| Run the C collector without resident .NET | Actual ingestion on both TVs through a system unit with a read-only code view | Proven in bounded trials |
| Restart a failed native process | Native probe killed; new PID and `NRestarts=1` on both TVs | Proven in bounded trials |
| Explicitly stop the service | Probe stopped and transient unit cleaned up on both TVs | Proven in bounded trials |
| Recover a hung process | Would require a worker heartbeat/watchdog and a separate hang test | Not implemented |
| Recreate the unit after reboot | Transient units and `/run` disappear | QN90A bootstrap unresolved |
| Management-host bootstrap | Idempotent reconciliation and local crash restart passed on QN90A; SDK rejected connections after the trial reboot | Pilot implemented; reboot acceptance failed |
| Read-only package-image filesystem | ext4 and SquashFS mounted successfully; both native exec attempts returned `EPERM` with unsigned-file UEP rejections | Mounting alone does not supply the VDFS execution exception |
| Launcher-managed SharedRO | Web Hub has the read-only VDFS view; ordinary .NET UI and service diagnostics both see writable `/opt` after entering appzone | Does not supply the current managed launcher's execution view; native probe deliberately skipped |
| Restart across standby/wake | Different from a full boot; requires power-state testing | Not verified |

The [collector research](samsung-tv-native-service-research.md) records the
hardware tests and capability boundary. Native Netdata uses the same launch
mechanism; its successful S90D trial does not establish boot persistence.

## Decompilation findings

These findings apply to the inspected QN90A firmware, `T-NKM2AKUC-2301.1`.
They rule out the paths examined, not every possible firmware integration.

| Candidate | Exact evidence | Consequence |
| --- | --- | --- |
| Normal system unit/drop-in | `load_from_path.lto_priv.0` walks the manager's search paths; `unit_load_fragment_and_dropin` uses those paths for dependencies/drop-ins. Live `UnitPath` contains only firmware and `/run` directories. | A unit stored under `/opt` is not automatically discovered at boot. |
| Samsung unit cache | `oneservice_setup` opens `/usr/lib/systemd/oneservice` and its `.table`. `open_follow.isra.0` consults that cache, then falls back to opening a unit file. | The cache is not the only loader, but neither it nor the persistent normal search directories are writable on QN90A. |
| D-Bus activation generator | Its system branch scans `/usr/share/dbus-1/system-services` and `/usr/lib/systemd/system`; its user branch selects the corresponding fixed user paths. | It does not generate root units from a service file placed under `/opt`. |
| Ordinary D-Bus activation | Captured system configuration uses standard system service directories. The inspected daemon contains the standard firmware prefixes; no writable extension directory was identified. | Changing to D-Bus activation has not supplied a persistent privileged entry. This is configuration/string evidence, not a complete daemon decompile. |
| Alternate boot manager | `init.wrapper` changes `SYSTEMD_UNIT_PATH` only after `bm_init.sh` succeeds. That script first requires firmware boot-mode flags; the writable JBM script is reached later. | Creating the JBM files alone does not add a normal-boot hook. |
| Persistent mount table | `/etc/fstab` and `/opt/etc/fstab` are absent. Captured `mount.sh.common` mounts fixed partitions and implements recovery, without reading a custom mount table. | There is no demonstrated fstab route for recreating the read-only execution view. |
| DeviceTracker boot script | Normal init launches the signed `Dlog_buffer.sh`. Its configuration controls diagnostic collection; earlier replacement-script testing was rejected by executable verification. | Writable storage does not make this a general unsigned startup-script extension. |
| udev rule | Inspected paths are firmware or `/run`; no persistent writable rules directory was identified. | No usable boot entry established; this was a path/string review. |
| Stability monitor | Decompiled configuration initialization sets built-in thresholds/process tables. `setvconfToRelaunchHitComp` sets the fixed `memory/hitcomp/isrunning` key. | These routines expose vendor-specific recovery, not a custom collector registration API. Other monitor routines were not exhaustively reviewed. |

The installed application and owner systemd manager cannot substitute for a
privileged bootstrap: the prior owner-manager launch reached the signed .NET
host but failed `unshare(CLONE_NEWNS)` with `EPERM` on both TVs. Retaining a tiny
managed launcher alone does not solve this authority boundary.

## QN90A follow-up: loader and container startup

### Trusted loader test

Tested the same reviewed ARM probe three ways under system units as UID 5001,
with the telemetry package label, an empty capability bounding set,
`NoNewPrivileges=yes` and a five-second deadline:

| Invocation | Result |
| --- | --- |
| Direct executable on writable VDFS | `203/EXEC` |
| Firmware `/lib/ld-linux.so.3` with that executable as its argument | Exit 127 |
| Direct executable with `BindReadOnlyPaths` | Expected exit 42 |

Kernel messages specifically rejected both writable-path copies as unsigned.
Explicitly invoking the trusted loader therefore does not remove the read-only
mount requirement on this firmware. The successful control confirms that the
worker itself needs no capabilities once the system manager prepares its view.
All three units and their staged files were removed.

### AT-HUB and zone-manager findings

QN90A does have an `AT-HUB.service` entry. Its cached command runs
`/opt/etc/parseinfo.sh`, a Samsung-signed script that copies firmware/model
information into `/proc/target_version`. It contains no custom startup command or
configuration include. S90D's writable **unit cache**, rather than merely the
existence of an AT-HUB service name, is the relevant difference.

Decompiling QN90A's `zone-manager`, `libzone.so.5` and `zone-template-launcher`
found a separate native autostart mechanism:

- Manager initialization obtains `lxc.lxcpath` and enumerates defined containers.
- `ZoneFactory::getZone` reads `lxc.start.auto`; `startAutoStartZones` queues
  container-start events when the zone's state permits.
- The captured firmware `/zone/appzone/config` actually sets
  `lxc.start.auto=1`, starts `/usr/bin/zone-init` as UID 5001/GID 100, and masks
  system-service/configuration directories inside that container.
- `zone-template-launcher` loads
  `/zone/template/templatezone/config_templatezone`, applies command/mount
  arguments to an LXC object and starts it locally. This is different from
  registering a persistent container with the running manager.
- `libzone` requests startup of a named zone through D-Bus, while its attach
  routine performs namespace operations in the calling process. A successful
  named-zone request would not by itself prove an ordinary app can prepare our
  execution view.

This is a real firmware boot mechanism, **not yet a custom collector boot path**.
The initial pass did not establish the actual global LXC configuration or a
supported persistent registration path. Reads of `/zone/config` and its LXC library
were denied through the tested SDK/administrative contexts, including a bounded
system-manager read unit. The protected firmware capture below subsequently
resolved the library and global lookup; custom registration remains unproven. Do not interpret those denials as absent files or conclude that the manager
scans `/opt/zone` merely because that directory exists. No zone definition,
security rule, vendor script or service was changed.

### Vendor service incident

A read-only D-Bus `GetZoneList` request timed out. Roughly 20 seconds later,
`zone-manager.service` exited with SIGSEGV at 18:10:18 UTC. Causation is not
established; no repeat request was made. Its existing stop timeout/restart policy
recovered it at 18:11:54 UTC (`NRestarts=1`, new PID 23727, active/running).
The main application services remained active, but QN90A's managed telemetry
process disappeared during recovery and its receiver became stale. Launching the
relay directly from SDK did not satisfy its Hub-caller validation. Bringing the
already-running Hub to the foreground restarted collection through the normal
authorized chain; new-session samples resumed. The prior foreground was the
screensaver. S90D collection stayed fresh. Physical remote/playback behavior was
not verified.

Further zone work should start with offline inspection of the exact LXC
configuration/library and the query failure, before any custom-container trial.
Do not restart or modify a shared vendor container to provision the collector.
The production recommendation remains unchanged pending a proven bootstrap.

### Offline follow-up: registration and query safety

The continuation used the existing firmware copies, the Ghidra project in
read-only/no-analysis mode, an independent ARM Thumb disassembler and a host-only
GLib contract check. **No TV commands, container calls or live trials were run.**
Only the existing NAS dashboard was queried for production freshness.
Both device locks/pending-journal checks passed. Two receiver observations showed
fresh samples and 18 sequence advances per TV with unchanged boot IDs;
the dashboard omits session IDs, so the earlier claim of unchanged sessions from
those observations was incorrect. The final sample ages were 4.22 seconds on QN90A and 9.97 seconds on S90D. This
checks ongoing ingestion, not process identity or power-state acceptance.

**Container discovery is initialization-time state in the inspected manager.**
The only direct calls to `list_defined_containers` are in `main` at `0x00013fd6`
and the `GetZoneList` handler at `0x000204b4`. Only initialization calls
`ZoneFactory::getZone` (`0x00014020`) to populate the context. The query builds a
reply; it does not register the returned names. `ZoneContext::getZone`
(`0x0001cc34`) searches the existing in-memory map, and `ZoneStart` ultimately
uses that lookup through `sendEventToZone`. An unknown name fails; it does not
load a new definition from disk. The later autostart checks iterate the existing
context rather than repeating discovery.

The embedded XML and 13-entry dispatch table contain version/list/state/PID,
start/stop, freeze/unfreeze, lock/unlock and attach/wait methods. They contain no
create, register, import or rescan method. This establishes the inspected D-Bus
surface, not the absence of every possible firmware provisioning mechanism.
Creating a directory and issuing `ZoneStart` is therefore not a demonstrated
registration procedure, even if a writable discovery directory is later found.

Both `zone-manager` and `zone-template-launcher` have `DT_NEEDED=liblxc.so.1` and
`DT_RUNPATH=/zone/config`; the manager also explicitly opens that library path for
monitor helpers. Its factory expects Samsung's `lxc.container_type` behavior.
An upstream LXC default directory or ABI cannot establish this firmware's global
configuration. `init_template_path` (`0x00022324`) creates/labels
`/opt/zone/template/securedata`; that is storage preparation, not evidence that
`/opt/zone` is the autostart search root.

**The dispatcher contains a concrete input-contract defect.** The firmware XML
declares `GetZoneList` with no inputs (`()`), but `callVTable` (`0x00026c38`)
unconditionally extracts `(s)` for each recognized method before checking the
zone type and calling the selected handler. The method-table entry at
`0x00044d64` confirms that `GetZoneList` follows this path.

| Exact ARM evidence | Meaning |
| --- | --- |
| `0x00026d88` calls the parameters getter; `0x00026d94` calls `g_variant_get` | The format literal resolves to `(s)` at `0x0002e6fc`. |
| Output argument is `[r7+0x20]` | No preceding initialization of this local appears on the dispatcher path. |
| `0x00026da8` loads that local; `0x00026dbc` calls `strlen` when non-null | Failed extraction can leave a value that is consumed before handler dispatch. |
| Handler call is later, at `0x00026dfc` | The unsafe path precedes LXC enumeration in `GetZoneList`. |

[GLib's documented contract](https://docs.gtk.org/glib/method.Variant.get.html)
rejects incompatible value types. Its
[2.62.6 implementation](https://github.com/GNOME/glib/blob/2.62.6/glib/gvariant.c#L5138-L5153)
checks the format before processing output arguments. A local check against host
GLib 2.88.3 confirmed that `()` leaves an initialized sentinel output unchanged,
while `(s)` assigns the expected string. The host test never dereferenced a failed
output and did not execute Samsung code. At that stage the TV's exact GLib implementation and crash backtrace were
unavailable, so this was a **strong incident hypothesis, not proven attribution
of the observed SIGSEGV**. The firmware capture below subsequently confirmed the
GLib failure branch; the crash backtrace is still unavailable.

The same dispatcher mismatch affects the declared inputs of `ZoneLock` (`(sb)`)
and `ZoneAttach` (`(sasasii)`); both also left the host test output unchanged.
Do not substitute those calls for the prohibited `GetZoneList` experiment.
The query handler itself uses the correct array builder type `as`, element format
`s` and reply `(as)`. Upstream
[LXC 4.0.12](https://github.com/lxc/lxc/blob/lxc-4.0.12/src/lxc/lxccontainer.c#L5142-L5219)
allows either names or container-object output to be null, so that difference
between the query and initialization is not itself evidence of a bug in Samsung's
unavailable library.

**The template launcher has additional permission gates.** Its `main`
(`0x00011354`) reads `/proc/PARENT_PID/zone` using `%d` and rejects values at or
below `0x34` (52); the comparison is at `0x00011646`. For the default `hybrid`
type it additionally resolves the init path, calls `libkUEPUser.so`'s `verifyFile`
with `/usr/lib/key.pub` and `UserCaller`, and checks the `:UEP` trailer and a
signature-level byte greater than ASCII `4`. Explicit `isolate` skips that
init-file verification branch but still requires the parent-level gate and the
LXC control-permission check. These are static checks, not measured ordinary-app
authorization. The launcher changes a local template LXC object and starts it;
no persistent registration write was found in this path.

The exact LXC library and its global-config lookup were still missing at the end
of that offline pass. The separately authorized capture below resolves those
questions. Persistent custom registration and native boot acceptance remain open.

### Protected firmware capture: actual LXC discovery

The bounded QN90A capture used the shared transport, device lock, pending-journal
check and firmware/runtime hash guards. A temporary managed reader ran under the
existing administrative helper. It made no zone D-Bus calls, loaded no LXC code,
and changed no vendor container, policy, boot file or production collector.

The reader reported UID 0, full effective capabilities, process label `User` and
`/proc/self/zone` value `50 0`. Directory access to `/zone/config` and reads of the
running zone-manager's proc metadata were still denied. This is a newly measured
managed-root context, not evidence that the files are absent. Its zone level also
falls below the template launcher's previously established parent gate (>52).

**Read-only firmware acquisition succeeded.** The reader verified that `/` was
VDFS on major/minor `179:19`, read-only, and checked the matching partition's sysfs
identity and size before opening `/dev/mmcblk0p19` with `O_RDONLY|O_CLOEXEC`.
Each data read was bounded to at most 16 MiB. The acquisition retained only the
header, filesystem metadata and selected file extents: 49,618,944 bytes of the
1,782,579,200-byte firmware partition. No raw reads targeted writable data or DRM partitions.
Temporary range files were hash-checked after transfer and removed.

An offline parser based on the
[Samsung VDFS layout and unpacker source](https://github.com/HinTak/vdfs-tools/tree/b87531ea78f713aa3e946deeae570c3fe5e75642)
validated the superblock, extended-superblock, translation-table and catalog/xattr
node CRCs. Selected compressed files additionally passed their footer CRCs and
per-chunk SHA-256 checks. These are integrity checks, not a claimed RSA signature
verification. Independently, the reconstructed zone-manager and stock appzone
config matched the earlier filesystem captures byte for byte.

| Captured fact | Result |
| --- | --- |
| `/zone/config/liblxc.so.1` | Symlink content `liblxc.so.1.4.0`; target recovered, 730,682 bytes |
| `/zone/config` | Firmware directory, UID/GID 0:0, mode 0755, Smack label `!` |
| `/zone` | Firmware directory, UID/GID 0:0, mode 0755, Smack label `_` |
| Root process global lookup | `/etc/lxc/lxc.conf`; default config `/etc/lxc/default.conf` |
| Root process default `lxc.lxcpath` | **`/zone`**, not `/opt/zone` |
| Firmware `/etc/lxc` and both config files | Absent from the validated catalog |
| Non-root global lookup | `$HOME/.config/lxc/lxc.conf`, with `$HOME/.local/share/lxc/` default |
| Enumeration | Immediate children whose `<lxcpath>/<name>/config` exists; no recursive `/opt` scan |

These lookup/default behaviors are decompiled from this exact library, with
literals independently resolved from ELF bytes. At Ghidra base `0x10000`,
`lxc_global_config_value` is `0x0005dec8`: `geteuid` at `0x0005def0` selects the
root branch, whose path loads start at `0x0005df70`. The `lxc.lxcpath` fallback
starts at `0x0005e112`. `list_defined_containers` is `0x00058d88`; its helper
`config_file_exists.lto_priv.0` at `0x0005ca6c` constructs `%s/%s/config`.
The earlier captured system unit starts zone-manager without a `User=` override.
The reader's mount table showed no separate `/zone` or covering `/etc/lxc` mount;
`/opt` was a different, writable data filesystem.

**This closes the direct writable-directory registration lead for the captured
normal firmware layout.** Its compiled root default is a read-only firmware
directory, and the global override path is also under that filesystem. The prior
manager decompilation additionally establishes initialization-only registration.
Creating `/opt/zone/<name>` or an owner's LXC config therefore does not establish
a persistent privileged boot entry. The running manager's private mount view and
cached value were not queried, so this is firmware/default-path evidence rather
than direct observation of its current cache. No custom-container trial is justified
by these findings, and no shared vendor container was restarted or modified.

The acquisition also recovered the exact `libglib-2.0.so.0.6200.3`. Its
`g_variant_get` at ELF address `0x431c6630` calls the format/type validator at
`0x431c6654`; the validator uses `g_variant_is_of_type` at `0x431c2744` and returns
false on mismatch. The failure branch emits diagnostics and returns without
calling `g_variant_get_va` or writing through the caller's output pointer.
This confirms the relevant GLib contract in the TV's own bytes and strengthens
the dispatcher-defect diagnosis. It still does not prove the precise instruction
that caused the earlier SIGSEGV; do not repeat the failing query.

**Cleanup and production checks passed.** The unique reader directory and all
range files were removed, and the administrative helper verified its own cleanup.
Zone-manager retained PID 23727, its original start timestamp and `NRestarts=1`.
Raw NAS receiver observations (which include session IDs) showed the same boot
and session before/after on both TVs: QN90A advanced 86 samples, S90D 85; capture-end
ages were 1.34 and 7.18 seconds respectively. A final receiver check after offline
analysis remained fresh at 2.63 and 8.48 seconds. No foreground launch or collector
restoration was needed. This verifies ingestion continuity, not standby, cold
boot or physical remote/playback acceptance.

The remaining QN90A task is a different persistent privileged bootstrap, or an
explicitly chosen management-host-assisted bootstrap using the existing guarded
transport. The shared systemd worker/restart design and managed production
fallback remain unchanged.

### SDK boot activation and TV-local access

The guarded read-only SDK capture is `setup/runs/20260921T190138Z-f1e3fcbd`.
It recovered 13 firmware files through the existing administrative connection;
no temporary TV helper, mount, unit or staging directory was created. The exact
daemon, vendor plugin and child terminal helper were analyzed offline.

**The SDK has boot-time mount authority, but its current TCP policy does not
provide a TV-local bootstrap for the signed relay.** This closes the proposed
relay → local SDK → administrative helper chain under the current settings.
It does not establish that every other privileged firmware interface is unusable.

The activation evidence is concrete:

- `sockets.target.wants/sdbd_tcp.socket` exists in the firmware catalog. The
  socket listens on TCP 26101 and activates `sdbd.service`; its installed drop-in
  requires the store application's persistent `data/develop_mode` marker.
- The service runs as `sdk:sdk` with Smack label `System`, inheritable
  `cap_dac_override,cap_kill,cap_setgid,cap_setuid,cap_sys_admin` and
  `SecureBits=keep-caps`. Its restart drop-in sets `RemainAfterExit=no` and
  `Restart=on-failure`.
- Live PID 3339 had UID/GID 901 and `CapInh`, `CapPrm` and `CapEff` all
  `0x2000e2`, with `NRestarts=0`. Its monotonic start timestamp was 51,713,915 µs
  after boot. This proves an existing privileged SDK service in this boot, not
  native collector startup or cold-boot acceptance.
- `EnvironmentFile=-/run/sdbd-env` is optional. The first `test -r` result only
  established unreadability; subsequent `ls -ld` returned `ENOENT`. Live
  `/proc/3339/cmdline` contained `/usr/sbin/sdbd` without arguments. No producer
  of that optional file was identified in the inspected artifacts. It is not
  evidence of a persistent writable boot hook. Neither `launch_sdbd.sh` nor the
  HyperUART script was executed.

The daemon loads `/usr/lib/libsdbd_plugin.so` at `load_sdbd_plugin` (`0x16aa0`).
`server_socket_thread` (`0x28080`) obtains the actual peer from `accept()`, formats
its address, and calls the admission handler before registering an SDB transport.
The vendor plugin's ten-entry table routes command 1003 to `verify_peer_ip`
(`0x16d38`); `_verify_peer_ip` (`0x16d04`) compares the address with the vconf
string `db/sdk/develop/ip` using `strcmp`. There is no IPv4 loopback exception.
The configured address observed during this capture is the development host,
and developer mode was 1. IPv4-mapped IPv6 follows the same IPv4 check; native
IPv6 uses command 1011, absent from the vendor table, and the daemon's default
`verify_peer_ipv6` (`0x176bc`) denies it. `request_sync_cmd` (`0x19294`) confirms
that fallback. The daemon's permissive *default IPv4* handler is therefore not
the active vendor IPv4 policy. The emulator branch does not apply to this TV.

The daemon's secondary server listener is disabled in its normal `sdb_main`
path; the captured command line and TCP tables showed 26101 listening, with
neither 26099 nor 26103 listening. `sdbd-user` creates a per-child Unix socket to
pass a terminal file descriptor to its parent. Its `main` (`0x10d24`) forks and
executes `/bin/sh`; it has no file capabilities or set-user-ID bit. This helper
does not supply independent mount authority to an ordinary app.

The CRC-checked firmware xattr tree explains the capability boundary:

| Executable | File permitted mask | File inheritable mask | Effective flag |
| --- | --- | --- | --- |
| `sdbd`, `sdbd-service` | `0` | `0x2000e2` | Set |
| `/usr/bin/dotnet` | `0` | `0x200040` | Set |
| `sdbd-tarlauncher` | `0xc0` | `0xc0` | Set |
| `sdbd-user` | No file capabilities | No file capabilities | — |

These are root-owned mode-0755 files. For a non-root caller, file inheritable
bits can contribute only capabilities already in the caller's inheritable set;
see the [Linux exec capability rules](https://man7.org/linux/man-pages/man7/capabilities.7.html).
Thus the ordinary app's measured zero capability sets cannot acquire mount
authority by executing `sdbd`, `sdbd-service` or `dotnet`. The archive launcher
has only `CAP_SETGID`/`CAP_SETUID`; its previously analyzed normal path selects
the owner account. The existing private-namespace administrative chain already
needs the SDK's mount capability before invoking that launcher.

No local SDB connection probe, developer-IP change, daemon restart, vendor
container query or persistent modification followed these findings. Final raw
receiver snapshots retained the same boot and collector session on both TVs:
QN90A advanced 64 samples and was 9.27 seconds old; S90D advanced 65 and was
5.08 seconds old. SDK PID 3339 still had zero restarts; zone-manager remained
PID 23727 with its prior single restart. No recovery action was needed.

At the end of that SDK capture, the fallback was management-host-assisted bootstrap through the
existing authorized connection, followed by local systemd crash supervision.
The subsequent pilot below implements bounded reconciliation, but does not pass
reboot or host-absence/late-reconnection acceptance. It is not
standalone TV startup. Further standalone research must identify a different
persistent privileged entry with a legitimate caller path from the signed app.
Do not retry this SDK chain by changing its network admission policy.

### Host-bootstrap pilot and SDK recovery

The isolated QN90A pilot is `setup/runs/20260921T192723Z-2df3903f`, now terminal
`rolled-back`. Source is `tvsetup/native_bootstrap.py` and
`tvsetup/native_bootstrap_trial.py`; it is experimental CLI tooling, with no
installed host daemon or scheduler. The signed managed collectors remained the
production path. The pilot used a separate TLS receiver, throwaway credentials,
private data directory and RAM lease; it did not copy or alter production pairing,
preferences or enable markers. S90D was observed for health, not piloted again.

The bounded supervisor uses a stable per-run unit name, records the TV boot ID
before submitting a start, verifies existing unit properties, and preserves a
healthy PID during reconciliation. An absent unit in the same recorded boot is
left quiescent, including after a lost reply, explicit stop or unit collection.
It only permits recreation for a new boot while the journal still requests it
and its deadline has not expired. Cancellation is saved before SDK connection,
so an offline stop cannot become an unintended start after reconnection.

The live evidence establishes:

- Two repeated reconciliation calls preserved native PID 17740. The worker ran
  as UID 5001 with the telemetry package label and a read-only code mount;
  process maps contained no managed runtime.
- Killing only that unit's main process produced PID 18995 and one additional
  systemd restart. The isolated receiver accepted 13 samples across four native
  sessions over 107.59 seconds during the reconciliation/failure exercises.
- The service had `Restart=on-failure`, `RestartSec=2s`, a 60-second start-limit
  interval and burst 3. Repeated forced failures ended with `MainPID=0`,
  `NRestarts=4`, `ActiveState=failed`, `Result=signal`. Reconciliation returned
  `quiescent` and did not reset/restart it. This proves the observed stopped
  outcome and host behavior; it does **not** prove a `start-limit-hit` result or
  the precise internal stop cause. The SDK journal query returned no entries.
- An independent expiry timer was armed before starting the worker. Its firing
  was not observed before reboot, so autonomous expiry acceptance remains open.
  Probe runtime limits are not a production configuration.

One delayed software reboot used the existing reviewed deviced API. Managed
QN90A telemetry returned under a new boot ID before any postboot pilot start or
manual Hub launch. However, the first guarded SDK capture failed when its sync
channel closed; subsequent SDB connections failed. TCP 26101 accepted a socket
and immediately returned EOF without an SDB exchange. The HTTP identity API
reported power on, Developer Mode 1 and the expected developer-host address, and
the actual TCP source address matched. Bounded retries and one host-side target
disconnect/reconnect did not recover access. No TV daemon was restarted or
developer setting changed. A listening port and HTTP developer flag therefore
do not establish a usable bootstrap transport.

The owner reported the Asteroids screen saver, then rebooted the TV. A second
new boot ID was verified and guarded SDK access returned. The pilot had already
been canceled durably; it was not resumed. Its main and expiry units were
`not-found`, and privileged readback verified all isolated pilot paths absent
after cleanup. The local receiver was stopped, administrative helper cleanup
passed, and neither TV had a pending setup journal. The recovered SDK was
PID 4239, `NRestarts=0`, starting at 65.34 seconds uptime; zone-manager was
PID 788 with zero restarts. Runtime developer mode was 1 with the expected IP;
`/run/sdbd-env` was absent. Both production sample sequences advanced, at final
ages 7.72 seconds (QN90A) and 2.56 seconds (S90D); S90D retained its pretrial boot
and collector session.

**Native postboot startup remains unaccepted.** No native worker was recreated
after either reboot. The owner's recovery reboot is not unattended bootstrap
acceptance, and neither reboot establishes power-loss or standby/wake behavior.
The failed boot's runtime SDK state was inaccessible: developer-key readiness,
peer admission and daemon lifecycle remain hypotheses rather than attribution.
A bounded privileged journal read after recovery also reported no journal files
and no previous-boot data, so it could not recover the missing failure record.
The next evidence needed is the SDK launch/admission state during a failed boot,
using an independently validated passive observation path. Do not infer it from
the recovered boot or attempt to repair it by changing vendor policy.

Offline callback analysis makes that next investigation specific. In the pinned
vendor plugin (SHA-256
`66a485e671b95b788e3fa90f4897902fcdcc04eae83167b1f01dacefeac6a89e`,
Ghidra image base `0x10000`):

- `_verify_sdbd_launch` at `0x16dc8` requires a successful read of
  `db/sdk/develop/mode` greater than zero. Otherwise it checks inherited listening
  sockets, accepts/closes a pending connection where possible, and calls
  `exit(0)`. This is consistent with immediate EOF, but does not identify its
  cause in the failed boot.
- That function registers the Thumb callback at `0x133e8` for early wakeup. The
  callback unsubscribes itself and calls `exit(-1)`, a failure exit relevant to
  the service's existing `Restart=on-failure` policy. We did not invoke it.
- It also registers the callback at `0x15de4` for changes to the same developer
  key. This callback checks the key name and current integer value; a successful
  read below 1 reaches cleanup calls, unsubscribes early wakeup and calls
  `exit(0)`. A failed read instead logs and returns. The cleanup helper was not
  analyzed here; its effects must not be inferred from the caller alone.

`audit_callbacks.py` checks the captured ELF hash, resolves the callback/key
literals and independently disassembles the three exit call sites. Ghidra's
existing callback locations had incorrect/unrecognized function analysis; their
Thumb bodies were reconstructed only in a read-only project session, with no
saved project changes. This identifies lifecycle gates to observe, not a new
collector boot hook or permission to alter developer settings.

Private evidence is under `native-service-probe/host-bootstrap-20260921/` and the
pilot run above. The unchanged ARM collector hash is
`0bd3a69df5243a0433f8cc47dc63ce2cb96746301dc8a7fa76663620ade80613`.
Local tests cover boot reconciliation, uncertain submissions, target binding,
offline cancellation and SDK retry exceptions. The full Python suite passes
169 tests; these are not hardware acceptance. Retry/cancellation hardening after
the failed connection was checked locally and has not passed another reboot trial.

### Autonomous path review with Luna subagents

The next pass separated package-image mounting and privileged executable entry
points into Luna investigations, with the primary agent reviewing the application
launcher and coordinating all device reads. Guarded read-only captures
`20260921T200607Z-30137f2e`, `20260921T200826Z-3195c21f` and
`20260921T201456Z-cad5946f` recovered 21 QN90A files. A fourth capture,
`20260921T203445Z-142dfbab`, added the exact .NET launcher core/util libraries;
`20260921T204059Z-2df658db` added its TV plugin, and
`20260921T204244Z-ce52a46a` captured deviced plus its library/unit/busname.
These six captures recovered 28 files. Each completed journal pins
their SHA-256 values. The upgrade script `701.app2sd.patch.sh` was inaccessible;
that failure does not establish absence. Production sessions continued, and no
launcher, mount API, new boot entry or vendor container was activated by these
captures.

**A persistent loader directory is not an arbitrary boot-command interface.**
The captured `launchpad-process-pool` hash is
`98fbf1a5b6808ede86d1bfa4972a8d862d28c276a7e1d412367153c692de5225`.
In `QN90A_LaunchpadPool_20260921` (image base `0x10000`):

- `main` (`0x13c20`) reads `/opt/share/loaders`; `_loader_info_load_dir`
  (`0x180b8`) selects `.loader` files. The parser (`0x1799c`) understands `EXE`,
  `ON_BOOT` and other activation fields, but parsing them does not prove use.
- `__add_default_slots` (`0x199ec`) creates boot slots from the separate,
  read-only `/usr/share/aul` directory. Its `__add_slot_from_info` (`0x1ca98`)
  checks executable file capability flags before accepting a slot.
- The persistent `/opt` list instead serves the add-app-defined-loader request.
  That branch fixes the executable to `/usr/bin/app-defined-loader`, uses selected
  extra/TTL data and supplies a false on-boot flag. It does not honor an arbitrary
  `EXE`/`ON_BOOT` pair from that file as a startup command.
- The package parser's `LaunchpadParser::Install` (`0x13578`, separate project
  `QN90A_LaunchpadParser_20260921`, base `0x10000`) requires privilege level 3;
  its diagnostic identifies this as platform privilege. A normal developer-signed
  package is not established as an authorized registration caller.

The CRC-checked VDFS executable/xattr audit also found a narrower new question:
`devzone-launcher`, `dotnet-launcher`, `launchpad-starter`,
`launchpad-process-pool` and `wrt` have both file-permitted and file-inheritable
capability masks `0x3002c01c0`, including `CAP_SYS_ADMIN`. This differs from the
previously inspected SDK daemon and plain `dotnet`, whose file-permitted masks
are zero. `audit_mount_authority.py` reproduces the enumeration offline. These
metadata are not proof of a callable bootstrap: executable admission, argument
validation, capability bounding and privilege-drop order still govern each path.

Read-only process evidence further narrows the caller boundary. The current Hub
has zero inheritable/permitted/effective capabilities but a full bounding set.
The managed telemetry service also has a **zero bounding set**, so its child
cannot reacquire the launchers' file-permitted capabilities through ordinary
execution. Launchpad itself retains mount authority. This kernel's captured
status files omit `NoNewPrivs`; omission must not be interpreted as false.
No launcher invocation was used to probe these boundaries.

### Signed launcher authority: dropped or gated before managed entry

The exact .NET launcher core/util and TV plugin resolved the file-capability
question without invoking those vendor paths. In `QN90A_DotnetLauncher_20260921`
(image base `0x10000`), `main` unconditionally queries its current AUL application
identity and application root before initializing CoreRuntime. Parsing
`--standalone` does not bypass those calls; the default `--appType` remains
`dotnet`.

The exact plugin SHA-256 is
`baa7ff3489f8d21d8062e00c1a61ddd61fce7410429bbd6c84c3546e9345eaf1`.
In `QN90A_DotnetPlugin_20260921` (image base `0x10000`):

- `plugin_initialize` (`0x23720`) selects the app-type branch. The default
  `dotnet` branch enters the existing zone-check/attach path. This is vendor
  container machinery, not a custom read-only-code preparation interface.
- `plugin_before_execute` (`0x23ca0`) calls `cap_init` and `cap_set_proc` with
  an empty set on that default path. CoreRuntime calls this hook before the
  managed execution delegate. File capabilities possibly acquired at launcher
  exec therefore do not reach our managed mount initializer through this path.
- The alternative `inhouse`/`normal` branches skip that drop but call
  `checkAppHasPlatformPrivilege` (`0x226f8`) through `SetAppInfoInhouse`
  (`0x23160`). That gate requires
  `http://tizen.org/privilege/internal/default/platform` and exits when absent.
  Choosing an argument is not proof that our signed package passes the gate.

The separate `devzone-launcher` canonicalizes the SDK tool path and uses zone
context/debug/attach operations before exec. It does not register a persistent
boot entry. None of these vendor launchers or container APIs was invoked in this
pass. Unknown caller `NoNewPrivs` still affects initial file-capability acquisition,
but does not remove the observed default-path drop or alternative privilege gate.

### Sealed memory-file execution: rejected on QN90A

The independent Luna execution review identified an untested boundary: a trusted
managed host creating a sealed `memfd`, then using kernel `fexecve` to replace
itself with the native probe. This would shed the CLR if accepted; it would not
itself register a boot service. A host Linux control passed with zero capabilities,
`NoNewPrivs=1`, unchanged PID, no CLR in the native maps and expected exit 42.
That control established harness behavior only.

Two bounded QN90A system-manager trials then separated launcher admission from
native execution. Both used UID 5001/GID 100, an empty capability bounding set,
`NoNewPrivileges=yes`, no read-only bind, no restart and a 15-second maximum:

| Trial | Observed boundary | Result |
| --- | --- | --- |
| `20260921T203641Z-cef619a1`, telemetry package label | SMACK denied execution of firmware `dotnet` labeled `System::Tools` | `203/EXEC`; managed harness never ran; no memory-file policy conclusion |
| `20260921T203721Z-b179db50`, `User` label | Harness ran with all four capability sets zero, created/sealed the memory file, and called `fexecve` | `EPERM` (errno 1), harness exit 77; kernel UEP explicitly rejected `/memfd:minimal-native-policy-probe (deleted)` as unsigned |

The second log identifies the backing filesystem as `tmpf`, mount flags `4000`.
It closes this tested fd-backed execution route on `T-NKM2AKUC-2301.1`; no native
entry or CLR-free worker occurred on the TV. Sealing the bytes does not satisfy
executable verification. Do not substitute a userspace ELF loader for this failed
kernel handoff or infer ordinary application authority from a system-manager test.

Each trial removed its transient unit, staged code, RAM output and transport
helpers. Both journals are terminal `rolled-back`. `zone-manager` and `sdbd`
kept the same PID/restart state; both production receiver boot/session identities
were unchanged and sequences advanced. Neither collector was paused or relaunched.

### Unprivileged user namespaces: unavailable in the tested QN90A context

Earlier `CLONE_NEWNS` failures did not test `CLONE_NEWUSER`. Guarded read-only
capture `20260921T205104Z-511a7ca7` now identifies QN90A's kernel as Linux 4.1.10.
Its `/proc/self/ns` contains ipc/mnt/net/pid/uts but no user namespace;
`uid_map`, `gid_map`, `setgroups`, user-namespace sysctls and `/proc/config.gz`
are absent. Do not substitute the separate S90D Linux 5.4.249 dump for this evidence.

The follow-up no-mount trial `20260921T205300Z-5b3aaa73` ran the signed host as
UID 5001, label `User`, all four capability sets zero and system-unit
`NoNewPrivileges=yes`. `unshare(CLONE_NEWUSER)` returned `-1`, errno 22
(`EINVAL`). The wrapper exited 77 without attempting `CLONE_NEWNS`, a bind or a
remount. This closes the tested user-namespace wrapper route; it is consistent
with disabled kernel user-namespace support, although the build configuration was
not captured. The unit, payload, output and transport helpers were removed, vendor
service state was unchanged, and both managed sessions advanced.

### Package-image mounting: real service, incomplete startup candidate

The exact QN90A `app2sd-server` (SHA-256
`46fdf6a9f9ff49e773d45b6e1b68bfe57852cd4107c323266fb37a3cb31058b3`)
implements encrypted ext4 image preparation and mount/remount operations.
Its captured system unit runs as root with label `System`; the D-Bus activation
file names that unit. The D-Bus policy requires
`http://tizen.org/privilege/packagemanager.admin`. Its persistent metadata database
is `/opt/dbspace/.app2sd.db`, but a writable registry is not an authorized arbitrary
command interface.

The launchpad implementation calls `OndemandSetupInit` for external storage and
has a separate `IsMounted` wait for `__AUL_TEP_PATH__` entries, bounded to roughly
five seconds. That second call targets `org.tizen.system.deviced.Tzip`, not
app2sd; the two services must not be conflated. The inspected daemon initialization establishes D-Bus service;
database access is present in later lifecycle/request paths. No boot-time restore
of a custom image or automatic read-only remount was established. Ext4 mounting
also does not establish the read-only **VDFS** executable exception that passed
our earlier hardware tests.

The exact QN90A `deviced` and client-library capture found no matching Tzip
interface or handler. Its fixed interface registration and startup library load
were reviewed offline; neither binary contains Tzip/`IsMounted` names. The generic
launchpad client therefore does not establish an implemented TEP provider on this
firmware. No Tzip D-Bus query was made.

The [package-image continuation](samsung-qn90a-package-images.md) subsequently
resolved app2sd's launch-time read-only mount and USB lookup, traced vendor TPK
storage handling and the separate internal `.tmk` mount workflow, and tested the
native probe on read-only ext4 and SquashFS. Both filesystems mounted, but both
exec attempts failed with explicit unsigned-file UEP rejection. Normal package
registration and any additional package trust mechanism remain untested; mounting
alone is insufficient. Direct database injection, arbitrary app2sd D-Bus calls
and vendor-container changes were not performed.

Private parent evidence, harness sources and decompilation are in
`native-service-probe/autonomous-startup-review-20260921/`. The three Luna reports
are retained separately under `native-service-probe/luna-{startup,launcher-authority,exec-boundary}-20260921`;
the execution-boundary report is a file. Firmware binaries and raw traces remain
outside Git.

During final review, S90D telemetry became stale and its guarded identity read
could not connect. The user then reported powering it back up; collection resumed
without an agent launch or recovery command. Both receivers were fresh again
before the final namespace trial and afterward. The interrupted preflight
`20260921T204923Z-1a9a0c05` is terminal `preparation-failed`; it submitted no QN90A
namespace operation. This observation does not establish native standby acceptance.

## Shared lifecycle design

```text
authorized bootstrap once per boot
  → system systemd unit
    → native worker as UID 5001
```

Keep bootstrap separate from supervision. The common service should use a fixed
unit identity, immutable root-owned version directories, a read-only code view,
the existing telemetry package label and the existing collector lease. Bootstrap
must verify an existing unit before reusing it and leave an already healthy worker
running. Hub entry must not create a second sampler.

For the C collector, retain `Restart=on-failure`, add a modest restart delay, and
bound repeated failures with a start-rate limit. A rate-limited service needs
explicit recovery; the interval expiring alone is not a promised new start.
Use an explicit service stop for disabling collection. Preserve the enabled
preference and lease checks so a restart cannot undo the user's choice. Network
errors belong in the worker's existing bounded retry loop.

The firmware's `service_enter_dead` implements the restart-policy decision and
arms a restart timer. This agrees with
[upstream systemd v244](https://github.com/systemd/systemd/blob/v244/src/core/service.c),
and the earlier hardware test demonstrates the failure path. Do not enable
`WatchdogSec` until the worker actually sends compatible heartbeat notifications.
Keep probe-only runtime deadlines out of a production service.

There are two bootstrap directions:

- **Standalone TV:** adapt S90D's existing privileged entry to the shared unit;
  preserve its splash/screensaver duties. QN90A still needs a separately proven
  privileged boot entry. The existing welcome-event Hub launch starts an ordinary
  app and does not grant mount authority.
- **Management-host assisted:** an always-on host could detect a new boot,
  wait for the existing administrative transport, and recreate the same unit
  idempotently. Subsequent crash restarts remain local to the TV. A bounded pilot
  now implements reconciliation using tested launch components, but QN90A
  postboot acceptance failed when SDK access was unavailable. It depends on host/network/SDK
  availability and still uses the temporary managed administrative helper.

Until one bootstrap path passes cold-boot acceptance, keep the current managed
collector as the production fallback. No entirely .NET-free startup or standalone
QN90A native boot is claimed.

## Acceptance and evidence

Before cutover, test a new boot ID with no manual postboot Hub launch, one worker
PID/lease, fresh receiver data, forced failure restart, deliberate stop, rate-limit
exhaustion, repeated Hub entry, standby/wake and recovery to the managed collector.
For host-assisted startup, also test host absence and late reconnection. Physical
power loss remains distinct from a software reboot.

Raw firmware and exports remain under the private research store. Reproduction
uses these artifacts, not ASLR addresses:

- `qn90a/systemd-{autostart-review,load-path,open-follow,restart-activation}.c`
  and their resolved exports; project `QN90A_ServiceReview_20260921`.
- Systemd SHA-256:
  `b8a37a192dec9526a5a4e90b3afb611679fab92f881fcd029c2bf76d15602a60`.
  This project's image base is `0x10000`; resolve PIC strings with that base.
- Functions: `unit_load_fragment_and_dropin` at `0x00066f74`,
  `service_enter_dead` at `0x0007d6b0`, `open_follow.isra.0` at `0x00092250`,
  `load_from_path.lto_priv.0` at `0x0009b1fc`.
- `qn90a/dbus-generator-autostart.resolved.c`; project
  `QN90A_Activation_20260921`, entry function `FUN_00010dac`.
  Generator SHA-256:
  `e05581982d7e32ed8a561829c5b9986f0fc329d6c145dbfb552d235839890403`.
- Guarded device captures: `native-service-probe/{qn90a,s90d}/boot-path-review/`.
  Some SDK pulls are permission-restricted; a failed pull is not evidence that
  the firmware file is absent.
- `qn90a/stability-monitor-activation.resolved.c`, same activation project:
  `setvconfToRelaunchHitComp` at `0x00064048` and
  `stability_monitor_config_init` at `0x00068fb8`.
  Binary SHA-256:
  `1452ed7d737372932e307af5a83269b8af622b9b61b15e87b67ea07486c09460`.
- QN90A loader trial: `setup/runs/20260921T180211Z-3779d13c`, terminal
  `rolled-back`; kernel rejection evidence in `boot-deep-review/` SDK captures.
- Zone dumps: `native-service-probe/qn90a/boot-deep-review/` and exports
  `qn90a/zone-{activation,manager-activation,template-activation}.resolved.c`.
  Firmware-copy staging journal `20260921T180410Z-9d83d96b` is `rolled-back`.
  Cleanup used hash verification because this firmware lacks `cmp`.
- Zone manager SHA-256:
  `8847a290447e696bc0f5015f3c0864f6b1d34c21e95d52bde84ac819babf0766`;
  template launcher:
  `1a1f919748699bf4ffa329cd5fb5844deee0231229f10af723adfe0237946efe`.
  Ghidra image base `0x10000`: manager `main` at `0x00013c84`, factory
  `getZone` at `0x0001d89c`, `startAutoStartZones` at `0x00023ca8`;
  client `zone_attach_process_to_container` at `0x00014eb8`.
- Offline continuation: `native-service-probe/qn90a/zone-offline-review/`.
  `elf-audit.json` records hash-checked dynamic dependencies, all 13 XML/table
  contracts and resolved short literals; `dispatcher-capstone.txt` independently
  checks the instructions against `manager-ghidra.txt`. `template-ghidra.txt`
  records the permission branches. Exports use `ghidra-scripts/ZoneOfflineAudit.java`
  with project `QN90A_Activation_20260921`, `-readOnly -noanalysis`.
  `audit_elf.py` reproduces the byte audit using the private research Python venv;
  `variant-contract.c` and `.log` retain the four host-only GLib checks.
  `input-export-hashes.json` pins the earlier decompilations/configuration.
  Receiver observations and their timestamps are retained in the same private
  directory. No new TV staging or recovery journal was needed.

- Protected firmware acquisition: `setup/runs/20260921T183007Z-43b30d17`, terminal
  `rolled-back`. `journal.json` records range hashes and confirmed removals;
  `managed-root-inspect.json`, `block-header.json`, `ranges/`,
  `discovery-catalog-evidence.json` and `extracted-manifest.json` preserve evidence.
  `parse_vdfs.py`, `extract_selected.py` and `audit_captured_elf.py` reproduce the
  offline checks. Run the ELF audit with the private research Python venv.
- LXC target SHA-256:
  `98bc25e170d4ebd9d3ad5cb31e20ebb80c5e08eb91be22bb1ec8d1776f09056b`;
  template config:
  `654f35c25ffff13e73bcc6aa6f0d2fb05e36ac6781023aa2ebb3b13e821afc5a`.
  Project `QN90A_LXC_20260921`, image base `0x10000`; exports
  `lxc-{initial,config,discovery-helper}.resolved.txt`, verified literals and
  independent Capstone output are in the capture run.
- Exact GLib SHA-256:
  `4785d0ab4f961d308c8bccc2bc0c158868019aa98946f75436b75f89170e75e1`.
  Project `QN90A_GLib_20260921`, original ELF base `0x431a0000`;
  `glib-{contract,format-helper}.resolved.txt` and `glib-contract-capstone.txt`
  retain the matching-firmware contract check. No firmware library was executed
  on the host or loaded into a TV probe.
- SDK capture: `setup/runs/20260921T190138Z-f1e3fcbd`, terminal `complete`,
  no TV mutations. `journal.json` pins all 13 files; `audit_sdk.py` verifies
  pinned ELF bytes, the ten plugin handlers, PIC literals and firmware xattrs.
  `sdk-key-checks-capstone.txt` independently checks critical Thumb instructions.
  `runtime-final-readonly.txt` and `health-{before,after,final}.json` retain
  activation and production continuity evidence. No credentials were collected.
- SDK daemon SHA-256:
  `b55f4cf1e769c1fd10dbee0a3bf48dd78270b4a115d7e9b86268b2c0c9b552ed`;
  vendor plugin:
  `66a485e671b95b788e3fa90f4897902fcdcc04eae83167b1f01dacefeac6a89e`;
  child terminal helper:
  `050ea3a92529c3b9875a1c49e9d9c59ada1e8012cfa2152502d616b756eaac6c`.
  Projects `QN90A_SDK_20260921`, `QN90A_SDKPlugin_20260921` and
  `QN90A_SDKUser_20260921`, each with image base `0x10000`.
  The private run contains decompilation, references and disassembly exports.
