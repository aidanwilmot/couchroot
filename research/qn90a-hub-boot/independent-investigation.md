# Independent boot investigation

Date: 2026-09-20. Scope: QN85QN90AAFXZA, T-NKM2AKUC-2301.1,
ARMv7/.NET Core 3.1.3. This document records local evidence and primary-source
research; deployment and reboot acceptance belong in this directory's main
report. The independent investigator did not access or modify the live TV.

## Why Home routing is not boot routing

The [2026-09-22 direct-boot investigation](../../docs/samsung-qn90a-direct-boot.md)
extends this analysis with live fastboot/viewer scripts, instruction-level
confirmation of the initial-mode gate, and the exact QN90A Samsung Home
assembly's cold-boot visibility policy.

The accepted QN90A Home implementation changes one persisted `key_filter` row
in `app_context.db`: `XF86Home` routes to `package:MiniHub001.Hub`. The framework
must receive that key event to execute the rule. Merely loading the database at
boot does not execute its rules. AirPlay `task_filter` rows similarly wait for
pause/deactivate events. These rows are persistent configuration, not a daemon
or a boot hook.

The exact-firmware private `app-boot-manager` decompile separately reads
`db/first_screen/type` (`mgr_util_get_firstscreen_appid`, 0x13ba4) and
`db/menu/smart_hub/ontvsetting/auto_start` (`mgr_util_get_autostart`, 0x142c0).
Changing Home row 82 does not change either. Root investigator's current live
readback is stock firstscreen `com.samsung.tv.csfs`, auto-start 0, and home
`org.tizen.tv-viewer`. `db/appfw/startup_appid` is absent.

Other persisted values are not fixed launch instructions. The boot manager
consults last-service/last-app settings only under specific boot, product,
display, power and wake-reason conditions. `db/appfw/booting_appid_backup` can
follow the most recently used application, including the screensaver. Treating
that value as a permanent Hub selection would be incorrect.

The apparently simpler firstscreen preference route was already tested and
failed on this exact TV: [the QN90A integration report](../../docs/samsung-qn90a.md)
records `db/first_screen/type=MiniHub001.Hub`, `auto_start=1`, and a real boot-ID
change from `00000000-0000-4000-8000-000000000006` to
`00000000-0000-4000-8000-000000000005`. The settings persisted, but native
readback and the owner's panel observation showed Live TV. Home still opened
Samsung's bottom menu. The original preferences were restored.

The private session `20260920T135502.324514Z-qn90a-preinstall/output.txt`
contains `/usr/bin/firstscreen.sh`: it hard-codes
`app_launcher -f com.samsung.tv.csfs ... entry_point cold_booting` and retries
until that request succeeds. It never reads the firstscreen preference. The
boot-manager decompile's `FUN_00019274` additionally bypasses its configurable
firstscreen launch when its initial-boot argument is zero, reserving that route
for a qualifying resume path. Substituting the boot helper's ID cannot repair
the cold-boot route. It also has side effects: the context-manager library
constructs a `name:firstscreen` task for that ID with Samsung Home/source-key
bundles, and sets its UI type from `memory/eden/show_status`. Preserve this
preference rather than assigning it to a no-window helper.

## Observed firmware boot machinery

The captured `/sbin/init.wrapper`, rather than a generic `rc.sysinit`, is the
relevant early path. It mounts persistent `/opt` and `/mnt/systemrw`, creates
fresh tmpfs `/tmp`, `/run`, and `/run/user/5001`, applies SMACK, starts Samsung
fastboot and `run_enlightenment.sh`, starts its diagnostic script on normal boot,
and execs `/usr/lib/systemd/systemd`. The systemd oneservice cache and regular
system unit directories are in read-only firmware on this model.

`app-boot-manager` has distinct initial/full-boot and resume modes, with its
decisions depending on power state, wake reason, ambient/art/product features
and persisted last-service settings. The ordinary path uses application launch
jobs and readiness events rather than a single interchangeable "startup app"
setting. Relevant exact-binary observations:

- Initial mode waits at most 100 × 100 ms for `/tmp/vconf_ready`.
- Post-boot mode waits up to 10 seconds for `/tmp/wm_start` and can launch
  `org.tizen.welcome-mode` in the background.
- `mgr_util_set_boot_done` writes runtime `memory/system/boot_done=1`.
- `FUN_00017b7c` sets boot_done first, then schedules the normal app-ready
  callback after approximately 3 seconds. `FUN_00019044` creates `/tmp/app_ready`.
  Therefore boot_done alone is not the final display/application readiness test.
- Jobs use `aul_launch_app` or `aul_launch_app_async`, with firmware retry logic.
  An accepted async request is not proof the requested window is visible.

The decompile resolves many literal strings but has imperfect types and
unresolved function arguments. These observations identify testable paths, not
a substitute for actual startup traces.

## Package lifecycle and alternative hooks

| Mechanism | Evidence and result |
| --- | --- |
| Signed service `on-boot` | Correct first candidate. The root investigator installed a separately signed marker-only native/.NET probe. Its signed manifest had `on-boot=true`, but installed `/opt/share/packages/MiniBoot001.xml` had `on-boot=false`; SDK launch successfully wrote a RAM marker. This is normalization, not autonomous boot acceptance. Evidence: private session `20260920T195610.982487Z-qn90a-root-home-telemetry`. |
| Service `auto-restart` | A restart policy after process termination does not establish an initial boot trigger. Enabling it also conflicts with the desired finite, one-shot lifecycle. |
| Samsung prelaunch metadata | Samsung's documentation explicitly says prelaunch is unsupported starting with 2019 consumer TVs; it would be background preloading even where supported. QN90A is not eligible. |
| App-defined `launch_on_event` | Exact QN firmware `libapp-context-manager-common.so`, used by `tvctx-manager`, supports `vconf://`, file, and key-sequence events, but `FUN_4684e608` requires a preloaded package or platform certificate before registering handlers. Merely adding `vconf://memory/system/boot_done` to a public package cannot supply the hook. Do not forge preload flags or certificate visibility. |
| Writable diagnostic shell | Prior live probe in `/opt/data/DeviceTracker` was rejected with `[uep][bash] the file is NOT signed!!`. The genuine `Dlog_buffer.sh` is Samsung-signed; replacing it would violate the current constraints. |
| Writable systemd cache | S90D's solution is inapplicable. QN90A cache and searched system unit directories are read-only. `/tmp` and `/run` overrides disappear on a full reboot. |
| SDK-installed helper invoked by Mac | Useful for controlled tests only; cannot prove autonomous startup. |
| Existing persisted task routing | Promising reversible integration point: add a narrowly gated application lifecycle rule that launches a separately signed no-window helper through AUL. This uses the same already active configuration store as Home/AirPlay and needs actual reboot validation. |

The task-rule database exposes `managed_app`, `key_filter` and `task_filter`; it
does not expose a general `event_filter` table. `vconf:(0=memory/system/boot_done)`
is a selector evaluated when a task event happens, not a subscription by itself.
`test_task_filter` is called for launch, start, run, pause, activate, deactivate,
stop and reset events. The firmware's JSON configuration also supports context
enable/disable events, but adding a runtime context requires a separate supported
configuration path; inventing such a database row is not sufficient.

## Candidate acceptance conditions (before live trials)

The following candidate order was proposed during the independent investigation.
The main report records its actual results: both TV-viewer triggers missed boot;
the later welcome-process start event passed the full-reboot tests.

The least invasive fallback to investigate is a rule observing the normal
`org.tizen.tv-viewer` boot launch while boot_done is 0. Prefer a launch event for
the first marker-only test: asynchronous start/run events might arrive after
boot_done becomes 1. Timing must be checked on an actual full reboot; it is not
established by the decompile.

The helper should have a single instance, a per-boot RAM claim made atomically,
a short uptime/deadline admission window, bounded readiness checks and bounded
launch retries. It should stop immediately after Hub is confirmed in the
foreground, skip a Hub already foreground, and abandon startup when a different
user application or active playback has taken over. It should never reset the
claim on normal exit. Runtime diagnostics and claims should be in `/tmp`, with
no recurring persistent writes. `on-boot=false`, `auto-restart=false` avoids
conflicting package restarts. No-window behavior must be measured because a
manifest's `nodisplay` flag alone only controls app-list visibility.

Each actual reboot must capture boot ID, uptime, helper state and accepted
launch timing, foreground framework/window state and telemetry session. No
postboot REST/AUL/SDK Hub launch may occur before proving foreground. Read-only
SDK inspection after autonomous startup is evidence collection, but the helper
must not depend on an SDK-created environment, temporary root namespace or
mounted root staging. Standby/wake keeps RAM state and is distinct from a new
boot; physical AC loss remains a separate untested case unless performed.

## Evidence and primary references

Private exact-firmware artifacts under `~/.local/share/samsung-tv-research/`:

- `qn90a/originals/init.wrapper`, `app-boot-manager`, `tvctx-manager`,
  `appctx-config.json` and `appsvc-readonly-copy.db`.
- `qn90a/boot.resolved.c`: boot/readiness/application jobs.
- `qn90a/routing.resolved.c` (`libapp-context-manager-common.so`): `test_task_filter` (0x46854834), task event
  handlers (0x46855f50 onward), and platform-cert check (0x4684e608).
- `sessions/20260920T170021.975006Z-qn90a-saver-boot-paths/output.txt`:
  filesystem mounts and boot-unit paths.
- `sessions/20260920T182630.726545Z-qn90a-root-home-saver-script-probe/`:
  prior unsigned-script rejection and cleanup.

Primary documentation consulted 2026-09-20:

- [Samsung prelaunch documentation](https://developer.samsung.com/smarttv/develop/guides/fundamentals/prelaunching-applications.html).
- [Tizen Web Runtime specification](https://docs.tizen.org/platform/compliance/media/tizen-3.0-wrt-core-spec.pdf): Web service on-boot requires partner certification.
- [Official native manifest reference](https://github.com/Samsung/tizen-docs/blob/master/docs/application/native/reference/manifest-xml.md) and
  [service application guide](https://github.com/Samsung/tizen-docs/blob/master/docs/application/native/guides/applications/service-app.md): current documentation describes native services but omits detailed on-boot policy; the live probe is authoritative for this firmware.
- [Samsung application-installation FAQ](https://developer.samsung.com/smarttv/develop/faq/application-installation.html): consumer USB auto-launch is not a general supported solution; hotel/server-specific behavior must not be transferred to this consumer TV.
