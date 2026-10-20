# Samsung S90D on-demand root after reboot

Update, 2026-09-20: the system screensaver now has a separate, verified one-shot
boot hook. It changes only AT-HUB's entry in Samsung's writable service cache,
preserves the original diagnostic script, and restores the read-only renderer
overlay after reboot. The current renderer runs a dim launcher-colored Asteroids simulation
and fades to black after ten minutes; the updated helper was verified through
a full reboot. See [implementation and rollback](../../../../native/system-screensaver/README.md).
The notes below document the earlier on-demand root work; its temporary access
mechanism remains unchanged.

Target: QN55S90DAFXZA, 192.0.2.12, firmware 2130.0,
Tizen 9 ARMv7, build T-PTMDAKUC-0090-REL-202605141701.
User authorized inspection, reversible persistence work, and a controlled reboot.

## Decision and rollback prepared before reboot

The existing Developer Mode boot route survived a controlled reboot. No additional boot hook,
privileged daemon, persistent payload, capability change, or security-policy
change was needed or installed. Root is recreated by the Mac only when explicitly invoked:

```sh
~/.local/bin/samsung-tv root-check
```

This command is a fixed root identity/access diagnostic; it is not an interactive
shell or arbitrary root-command interface. Existing research collectors use the
same temporary root chain for explicitly supplied operations.

Rollback/cleanup command (preserves the existing developer access route):

```sh
~/.local/bin/samsung-tv run ~/.local/share/samsung-tv-research/persistence-cleanup.sh
```

It refuses to clean while a known root helper is running, removes only the known
staged files, refuses directory symlinks, leaves unknown files untouched, and
checks the original passwd and public-key hashes. No persistent configuration
needs restoration: the existing boot route works. Disabling Developer
Mode would remove the pre-existing entry point and is outside this rollback.

Exact boot files/binaries and the marker were backed up before the reboot into
private `~/.local/share/samsung-tv-research/dumps/20260919T222450Z/`.
The archive preserves modes/ownership/timestamps/link targets; the accompanying
xattr JSONL preserves capabilities and SMACK labels. All four transferred
artifacts passed SHA-256 verification. Raw backups remain outside git.

## Verified mechanism and inspected restrictions

The package-name SDK injection runs as UID 901, SMACK `System`. SDB's stock
service supplies inheritable KILL, DAC_OVERRIDE, SETGID, SETUID, and SYS_ADMIN.
`/usr/bin/dotnet` has `cap_setgid,cap_sys_admin=ei`; arbitrary managed code gains
those capabilities. Its `security.SMACK64EXEC=User` changes the process label
when executed. `/usr/sbin/sdbd-tarlauncher` has `cap_setgid,cap_setuid=eip`.

The managed helper creates a private mount namespace, makes propagation
recursively private, verifies no shared mounts remain, and temporarily bind-mounts
a disposable verification key and a passwd view where only owner's UID/GID
become zero. The signed test archive is accepted by tarlauncher; its credential
switch then gives the command real/effective/saved/filesystem UID/GID 0.
The private binds are removed when the helper exits. Host passwd and public-key
bytes are unchanged. SMACK remains `User`; root is not a claim of unrestricted
access through every Samsung policy or verified-boot mechanism.

Startup/configuration findings:

- The stock `sockets.target.wants/sdbd_tcp.socket` symlink is present under
  `/usr/lib/systemd/system`. `systemctl` reports the socket as `disabled`, but
  that does not negate the vendor dependency: it started automatically at boot.
- The release drop-in `store-develop-mode-release.conf` clears the base unit's
  negative condition and requires the persistent `develop_mode` marker.
- Marker: `/home/owner/apps_rw/com.samsung.tv.store/data/develop_mode`, zero bytes,
  owner 5001, group 1051, mode 0644, SMACK `User::Pkg::com.samsung.tv.store`.
  It resides under `/opt` on writable VDFS and retained its original timestamp.
- `/etc/systemd/system`: root:root 0755, SMACK `_`, on the read-only system image.
  `/opt/etc/systemd`: root:root 0755, SMACK `_`, on writable data storage.
- `/opt/etc`: root:system_share 0777, SMACK `System::Shared`; its diagnostic
  scripts are SDK-writable. `AT-HUB.service` references `/opt/etc/parseinfo.sh`,
  which is root:root 0777, SMACK `_`, and contains a Samsung signature trailer.
  AT-HUB was inactive/disabled. These hooks were inspected and left unchanged;
  mere writability would not establish that a modified signed script executes.
- Staging directory: owner:users 0777, SMACK `User::App::Shared`, writable by SDK.
  It is persistent storage despite its `tmp` name: staged reboot-collector files
  survived reboot and were subsequently removed with the prepared cleanup script.
- SMACK policy and xattrs were inspected privately. No SMACK rule, capability,
  host mount, account, firmware partition, boot slot, or startup configuration
  was changed.

## Controlled reboot and root verification

On 2026-09-19 UTC:

| Check | Result |
| --- | --- |
| Before reboot, 22:24:04 | UID/GID 0; permitted/effective capabilities `0000003fffffffff` |
| Native reboot request, 22:28:40–45 | Samsung deviced D-Bus `Reboot(s)` returned `i 0` |
| Boot ID before | `00000000-0000-4000-8000-000000000015` |
| Boot ID after | `00000000-0000-4000-8000-000000000011` |
| First post-reboot SDB inspection, 22:29:51 | New boot ID, uptime 62.05 seconds, same build; SDB active |
| Direct post-reboot proof, 22:30:23 | Fresh root with full capabilities, no persistent payload |
| Normal installed `samsung-tv root-check`, 22:30:47 | Passed once HTTP status API was ready |
| Original files, 22:30:44 | All 13 hashes matched; Developer Mode marker ownership/label and binary capabilities unchanged |
| Cleanup/rollback, 22:30:17 and 22:31:44 | Removed reboot-staged files, then passed again idempotently |
| Final check, 22:32:20 | Empty staging; no root helpers or host key/passwd bind mounts; SDB active |

The ordinary `systemctl reboot` path was unsuitable: SDK was denied, and root
received `Unit reboot.target not found`. Neither failed request restarted the TV.
Live D-Bus introspection exposed Samsung's native `Reboot` method with a string
reason. Static inspection of this TV's deviced handler showed it routes through
its power manager's `request_reboot`, including existing power-state checks.
The exact command is recorded in `scripts/samsung-tv-persistence/reboot.sh`.
It was executed using the existing temporary-root collector; no force reboot,
raw reboot syscall, or replacement systemd unit was used.

The root collector exited and unmounted both overrides before the reboot.
Its later SDK file-cleanup attempt lost connectivity during reboot. The prepared
cleanup script removed the remaining known files after boot, before repeating
the root proof. The collector's ephemeral local TLS key was also removed.

SDB became reachable before HTTP port 8001. During that interval, a bounded
one-off SDB diagnostic verified the exact build/architecture and performed the
cleanup/proof. The installed launcher's identity checks were not weakened.
At approximately 22:30:30 the API again reported the exact model/platform,
Developer Mode `1`, and developer IP `198.51.100.32`; the ordinary command then
passed. Allow boot services to settle before invoking the normal launcher.

## Normal operation and scope

The user reported a Pluto TV picture after reboot. CSFS, HomeSidebar, HomeMedia,
and webappservice were running. There were five failed systemd units after boot,
all already present in the eight-failure pre-reboot baseline; no new failed unit
was observed.

YouTube (`9Ur5IzDKqV.TizenYouTube`, version 2.1.527) and Plex
(`kIciSQlYEM.plex`, version 5.64.1) each launched through `app_launcher` and
reported `running=true`, `visible=true` through the TV API. Plex was left in the
foreground. These are launch/visibility checks; signed-in playback and A/V quality
were not exercised. App data and startup preferences were not edited.

This establishes repeatable on-demand root after a normal reboot on this exact
build. It does not install a root service that starts at boot. Continued access
requires Developer Mode, its configured Mac address, the local research toolkit,
and unchanged firmware behaviors. Firmware updates or a factory reset were not
tested, and this does not promise survival of either.

## Evidence and recovery

Sanitized summary: `inventory/samsung/2026-09-19/persistence/verification.json`.
Full commands/results remain in private toolkit sessions. Exact startup backups,
metadata, and SMACK/capability sidecars are in the backup directory above; host
passwd/public-key copies were subsequently saved there and verified against the
pre-reboot hashes. No private test key, app database, or binary dump is in git.

The cleanup command above is the rollback for temporary artifacts. It was actually
used against the files surviving reboot, then verified a second time. There is
no persistent root installation to uninstall. The existing Developer Mode setup
was deliberately retained. If an invocation is interrupted, reconnect and inspect
before cleanup; never blindly repeat a submitted mutating operation.

Prior detailed investigation notes are in
[the exploit-chain guide](../../research/exploit-chain.md).

## Hub-installation follow-up

A second controlled reboot during hub testing changed the boot ID to
`00000000-0000-4000-8000-000000000012`. The standard `samsung-tv root-check`
passed afterward in `sessions/20260919T232612.731333Z-root-check/`: UID/GID 0,
effective/permitted capability mask `0000003fffffffff`, private mounts removed,
original file hashes unchanged, and probe directories absent. No privileged
startup service was added. Root remains a fresh on-demand action after reboot.

The local Python wrapper now sets the reviewed transport's
`SDB_APPINSTALL_MAX_SAFE_BYTES` to `400` immediately after import. This firmware
rejected a 495-byte inline request; staging the same script succeeded. This is
a Mac-side transport adjustment, not a TV security/configuration change. Exact
previous wrapper: `signing/samsung_tv.py.before-inline-limit` in the private
toolkit. The pinned upstream checkout remains unchanged.

The completed hub configuration was also tested after a final reboot with boot ID
`00000000-0000-4000-8000-000000000014`. The ordinary `root-check` again returned
UID/GID 0 with effective/permitted capabilities `0000003fffffffff`, then removed
its private mounts and staging directories and verified unchanged originals.
The hub uses ordinary app/startup settings; root access remains on demand.
