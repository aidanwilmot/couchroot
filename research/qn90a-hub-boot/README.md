# QN90A automatic Minimal Hub startup

Target only: QN85QN90AAFXZA / `192.0.2.11`, T-NKM2AKUC-2301.1,
ARMv7, .NET Core 3.1.3. Shared baseline: commit `4c65125`.

## Mechanism

A normally signed, no-window `MiniHubBoot.Start` UI application is requested by
one additional persisted `/opt/dbspace/.app-context.db` task rule:

```
source: package:org.tizen.welcome-mode
source_event: start
request: launch
target: package:MiniHubBoot.Start
```

This Samsung process starts during the normal boot manager's post-display work,
after the context manager has subscribed to application events. The rule does
not redirect or replace Samsung's welcome process. Its existing power-key
handling remains intact. A separate managed-app row registers our helper.

The helper creates no window and uses the ordinary public application-control
launch privilege. It claims an exclusive file on `/tmp` once per boot. It checks
the exact firmware, 32-bit runtime, boot uptime, readable native boot-completion
state, active power state, and foreground application. Boot completion must be
stable for five seconds (plus timer scheduling); only empty, TV-viewer, or Samsung
Home foreground state is accepted. Another app or inactive display aborts.

It makes at most three launch attempts. After a rejected request, it waits at
least three seconds from the native call's return before another attempt; a slow
call does not consume that pause.
Once a request is accepted, it never sends another: it observes foreground for
up to 60 seconds, then exits. Total admission/execution is bounded by uptime 120
seconds and 110 timer ticks. Hub already foreground is a successful no-op.
A retained RAM claim prevents another welcome-process start from redoing startup.
There is no persistent polling service, recurring flash log, key interceptor,
application killer, wake request, or network dependency in the helper.

The original rollout kept Hub at version 0.4.1; relay updates do not update Hub.
Its existing `MiniTelemetry.Start` →
`MiniTelemetry.Service` route starts telemetry normally. Its preferences, signed
package, splash handling, Home and AirPlay rules, and dashboard Asteroids timer
are not modified. The helper does not set or repurpose `first_screen/type`,
`home_appid`, `overlay_home_appid`, `auto_start`, or last-app preferences.

## Why the earlier routes did not work

- Home row 82 is a **key-event** mapping. A persisted target is not a boot event.
- Samsung's cold-boot `/usr/bin/firstscreen.sh` hard-codes Samsung Home. Previous
  real-reboot trials of `first_screen/type=MiniHub001.Hub` plus `auto_start=1`
  already failed; these preferences also affect resume/source behavior.
- `db/appfw/booting_appid_backup` is persisted but mutable app-framework history,
  not a fixed startup instruction. `memory/system/boot_done`, foreground IDs,
  helper claim/status, and process state are runtime state reset by a full reboot.
- A normally signed `on-boot="true"` service probe installed successfully, but
  this firmware rewrote its installed manifest to `on-boot="false"`. Its code
  worked when explicitly launched; it did not run after reboot. This is not a
  viable public-certificate boot registration. No certificate flags were edited.
- An initial TV-viewer `launch` rule gated on boot_done=0 and a subsequent
  ungated TV-viewer `start` rule both survived reboot but missed startup. TV-viewer
  begins before the context manager. On the measured second boot, `/proc` start
  ticks were 344 and 685 respectively, with live `getconf CLK_TCK=250`:
  approximately 1.376 and 2.740 seconds. Welcome mode began at 17.516 seconds.
- The boot manager waits for display initialization, completes its main jobs,
  sets `memory/system/boot_done`, and schedules `/tmp/app_ready` about three seconds
  later. Ordinary apps cannot stat the readiness files under their package SMACK
  label (`app_ready` is System::Privileged). The helper leaves those labels intact
  and uses readable boot/power state, settling time, and bounded normal framework
  requests instead. `wm=false`/`app=false` in its status means unavailable to the
  package, not proof the system marker is absent.
- System systemd paths/cache are read-only; `/run` is transient. The writable
  DeviceTracker script needs Samsung's firmware signature. App-defined
  `launch_on_event` registration requires a preloaded/platform-signed application.
  None of these restrictions was weakened.

See [independent investigation](independent-investigation.md), including primary
Tizen/Samsung documentation and exact-firmware decompilation references. Samsung
[prelaunching](https://developer.samsung.com/smarttv/develop/guides/fundamentals/prelaunching-applications.html)
is not supported on 2019-and-later TVs and is not foreground autostart.

## Install, status, rollback

Current updates use the shared setup engine with `--components startup`; see
[TV setup](../../docs/tv-setup.md). The commands and ledger below describe the
original research rollout. Do not use the historical uninstall/reinstall flow
for a routine update to an installed relay.

From the repository root, with the existing private SDK/signing profile and
validated Home/AirPlay integration:

```sh
python3 research/qn90a-hub-boot/manage.py install
python3 research/qn90a-hub-boot/manage.py status
python3 research/qn90a-hub-boot/manage.py reboot
python3 research/qn90a-hub-boot/manage.py rollback
```

`install` refuses an unknown existing package or route. It verifies network
model/platform, firmware, ARMv7, .NET runtime, Samsung host hash and original
account/verification-key hashes through the existing temporary-root transport.
It saves a consistent SQLite backup, builds/signs with `MinimalHubQN90A`, verifies
installed assembly/runtime-config hashes, checks exact Home/AirPlay dependencies,
and adds only the two owned rows in a transaction. Native Vconf setters notify
the context manager without replacing Buxton labels; operations allow its six
second reload interval. `quick_check` must return `ok`.

Private recovery ledger:
`~/.local/share/samsung-tv-research/qn90a/hub-boot/installed.json`.
It is written **before** package mutation and tracks partial installation/removal.
Backups and the deployed manifest are under `/opt/minimal-hub-boot/`; a fresh
consistent backup is made on each installation, never on routine boots.
The initial research baseline remains `context-before.db` (SHA-256
`bf93fb0cff7d9dc31e3419aee69234c2aa4cc2e040f51cfb67a70ae4cb671495`).
Do not restore the whole database over later settings changes.

`rollback` removes only the exact owned rows, reloads native routing, stops only
our short-lived helper if necessary, and removes its signed package using normal
`pkgcmd -u -n MiniHubBoot --global`. The Samsung TV CLI's web-oriented uninstall
path did not remove this native package; its output/exit status was insufficient.
The command now verifies package files are actually absent. A retry handles
already removed rows/package after an interrupted rollback. Backups remain.
Hub, telemetry, screensaver and all unrelated routing remain installed.

A failed/uncertain mutation is not automatically repeated. Run `status`, inspect
the private ledger/evidence, then `rollback` to unwind a partial install. Unknown
artifact hashes or conflicting owned rows cause refusal rather than overwrite.
For an update, rollback this small helper then install the rebuilt version;
never uninstall Hub or telemetry to update boot integration.

`reboot` schedules one native DeviceD reboot after temporary-root cleanup. It
contains **no postboot launch**. SDB may retain stale Mac transport state afterward:

```sh
~/.local/share/samsung-tv-research/bin/sdb kill-server
~/.local/share/samsung-tv-research/bin/sdb start-server
~/.local/share/samsung-tv-research/bin/sdb connect 192.0.2.11:26101
python3 research/qn90a-hub-boot/manage.py status
```

This resets the local SDK daemon only. It is not part of TV startup. Keep SDK
captures/operations sequential: overlapping a long SDK sampler with staging can
also stall the legacy transport. Passive REST observation avoids that conflict.

## Diagnostics and acceptance

RAM-only `/tmp/minimal-hub-boot/status.json` records boot ID, entry/request/final
uptime, observed foreground, readiness/power state, attempts, accepted result,
and outcome. Since 0.2.1, it also retains every attempt's API stage, result,
start/return time and foreground/readiness observations (at most three records).
Version 0.2.2 records the last call's completion time and uses it for retry
spacing. It is replaced only at lifecycle transitions. `foreground-confirmed`
is stronger than an accepted launch request; REST visible=true and native
foreground readback were additionally checked before any assisted launch.
Telemetry status retains its separate boot/session and send counters.

[Machine-readable evidence](../../inventory/qn90a-hub-boot-20260920.json) records
individual full-reboot trials and exact timing. Private raw sessions, transport
commands, signed packages, REST/NAS observations and screenshots live under
`~/.local/share/samsung-tv-research/qn90a/hub-boot/` and `sessions/`.
No credentials are included in the repository.

The final 0.2.0 code passed two full native reboots:

| Kernel boot ID | Helper entered | Hub request | Foreground confirmed | Passive telemetry evidence |
| --- | ---: | ---: | ---: | --- |
| `00000000-0000-4000-8000-000000000026` | 18.38 s | 25.69 s | 44.99 s | New boot, sequence 4, uptime 90.52 s |
| `00000000-0000-4000-8000-000000000028` | 18.32 s | 25.48 s | 43.67 s | New boot, sequence 2, uptime 84.73 s |

Times are TV kernel uptime. Each boot issued one accepted Hub request, then the
helper exited. REST reported Hub running/visible before SDB reconnection. On the
second final-code trial the Mac SDB daemon was explicitly stopped until both Hub
visibility and new-boot telemetry were observed. These were passive GETs, with no
postboot application launch. Native readback then confirmed Hub fullscreen and
an empty partial overlay. Telemetry launched through the unmodified Hub relay;
one initial network failure on the second boot recovered automatically.

Three earlier full reboots tested two failed TV-viewer event rules and the first
working welcome-process rule. The first working helper's 15-second observation
expired before Hub rendered, even though Hub subsequently became foreground.
The final code extends only that confirmation window to 60 seconds and never
retries an accepted launch. All five trials remain in the evidence inventory.

Rollback was exercised on the device: all three routing tables matched the
original backup including row IDs and every column, the native package was
removed, and retries completed partially removed states. Reinstallation through
the final installer produced the second final-code reboot above. The deployed
assembly SHA-256 is `8805dfafe290ca87222cc7a11584556a1038ca481c5a8121429320acd032fee9`.

After startup, deliberately launching the helper again while Plex was foreground
left Plex in front and preserved the boot status/claim hashes. Native `XF86Home`
returned Plex to Hub with no partial overlay. An idle AirPlay web receiver was
brought foreground, then paused through its native API; Hub returned within
0.8 seconds. Both AirPlay routing rows remain exact. This tests native routing,
not an actual iPad stream or physical remote transmission.

The unchanged dashboard timer also passed after the final reboot. Last input was
uptime 438.07 s; native samples showed Hub at 734.15 s and Asteroids at 744.04 s
(the sampling interval brackets activation at 296.08–305.97 seconds after input).
Passive REST checks and a captured frame confirmed the saver. The native system
screensaver flag stayed false, consistent with dashboard-owned activation. A
Right key returned to Hub by uptime 796.10 s with no partial overlay. Telemetry
retained PID 3436 and its original session, reaching sequence 72 / 71 sent; the
boot helper's completed record stayed unchanged. The installed idle script's hash
matched the repository. Hub and Asteroids screenshots remain in private evidence.

Tests passed: 37 QN90A Python tests, 12 production relay timer scenarios, and
9 JavaScript telemetry/dashboard-idle tests.

Tests:

```sh
python3 -m unittest discover -s tests -p 'qn90a*test.py' -v
python3 tests/qn90a_boot_relay_test.py
node --test tests/telemetry-service.test.cjs tests/qn90a-idle.test.cjs
```

SQL tests cover exact row preservation, conflicting dependencies and rollback.
The host harness executes the unchanged production timer logic with controlled
native/file I/O, testing bounded retries, accepted-request dedupe, readiness,
power/foreground aborts and deadlines. ARM startup/claim and actual scheduling
are device checks, not simulated proof.

## Boundaries

The [2026-09-22 diagnostic follow-up](../../docs/samsung-qn90a-startup-launch-diagnostics.md)
records the 0.2.2 retry correction, 18 production timer scenarios and additional
device reboots. The earlier 0.2.0 measurements above remain historical evidence.

The [web startup profiling pass](../../docs/samsung-qn90a-web-startup.md) tested
a three-second initial settle in 0.2.3. Its results overlapped the five-second
controls, so 0.2.4 restores the five-second policy and retains the 0.2.2 retry fix.
This pass also exercised the corrected post-return retry gap on real hardware.

This is exact-firmware integration through an existing Samsung configuration
engine, not a vendor-supported consumer-TV boot extension. A firmware update or
package/routing regeneration can invalidate it; identity guards intentionally
refuse an unknown firmware. Welcome mode failing to start, severe boot delays
beyond 120 seconds, or framework rejection makes it fail closed for that boot.

An accepted asynchronous framework launch cannot be revoked by this helper. It
never retries an accepted request. Foreground changes observed before a request
abort; user-selected Live TV/HDMI inside the same TV-viewer process during the
short startup window cannot be distinguished from initial TV-viewer startup.
Normal subsequent switching/playback is not watched or relaunched.

Full native reboot changes the kernel boot ID. Physical AC cold power-on,
ordinary standby, wake with the physical remote, and background-maintenance
boot are distinct and are not established by this reboot test. No physical AC
cycle or ordinary standby/wake acceptance was performed in this change. Existing
system-wide native screensaver memory-patch limitations remain; the preserved
production saver is the dashboard-owned timer. Actual streaming playback and
fresh real iPad AirPlay sessions require separate acceptance from native route
and idle-receiver tests.
