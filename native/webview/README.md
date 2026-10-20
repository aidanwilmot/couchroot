# Native WebView Hub (experimental)

> Phase 2 remains unaccepted on hardware. WebView permits the TV Plus discovery
> exception; pure-native Hub does not. Native preference import refuses an invalid
> file as a whole, leaving the source file and existing WebView preferences intact.
> Missing files log `skipped=missing`; malformed ones log `skipped=format`.
> See the [current acceptance gates](../../docs/project/release-readiness.md#current-acceptance-gates-merged-phase-2).

QN90A firmware **T-NKM2AKUC-2301.1 only**. This host runs the existing `web/`
interface in Chromium/EWK inside an owner-UID EFL window. It starts from the
native boot hook. Background admission can precede Samsung's signed web-app
launch path; normal boot uses the signed Hub for a safe viewer handoff.
It is a third launcher option alongside the signed [web Hub](../../web) and
[retired pure-native experiment](../../research/archive/native-hub); see [the comparison](../../docs/guides/choosing-a-launcher.md).

The source, tests and recovery-command renderer are public. Deployment still
requires a private, model-bound installer using the shared setup journal, enrolled
root agent, exact backups and existing QN90A hook chain. `./tv-setup` does not yet
install this launcher. No vendor libraries, firmware dumps, credentials, private
journals or compiled TV binaries are included. S90D has not been tested.

## Behavior

- **Shared interface:** the build copies the signed package's web file list,
  excluding its manifest, inserts `native-shim.js` after `model.js` and appends
  `native-shim.css` to the bundle's copy of `style.css`.
  There is no second UI implementation or change to the signed WGT.
- **Engine:** `--engine=default|upgrade` chooses the EWK implementation before
  initialization, then verifies the loaded library in `/proc/self/maps`.
  QN90A's tested engines are Chromium 76.0.3809.146 and 120.0.6099.5.
  Before loading EFL/EWK, the host waits up to 20 seconds for readable, nonempty
  base and requested upgrade libraries. QN90A mounts these filesystems during
  boot; calling the wrapper too early permanently caches the default engine.
  Missing files fail with `engine-files-timeout`. Loaded mappings are still
  verified; an unexpected fallback is never presented as Chromium 120.
- **Rendering:** an Ecore/Evas `wayland_egl` window first draws a native loading
  screen in diagnostic mode. With `COUCHROOT_WEBVIEW_DEFER_SHOW=1`, the launcher
  instead lays out the hidden view at 1920×1080 and keeps its window unmapped
  until the Hub signals initial DOM/font readiness, EWK reports a subsequent
  `frame,rendered` signal and the page confirms that its rendered Home was
  presented (first contentful paint). Page load or a background-only paint is
  insufficient. The native bundle's `native-shim.css` rule keeps the static default
  markup transparent until `hub.js` has rendered, so a frame of that markup that
  finishes late under boot load cannot pass for the Hub. Chromium starts directly from the event loop, so hidden
  startup does not depend on a visible loading frame. Normal boot leaves the
  signed Hub visible during this wait; no native loading screen is shown. A
  bounded worker rechecks source, ISP owner, display and foreground before
  mapping the ready window. Another app/source cancels presentation without
  restarting or taking focus. Missing rendering times out after 35 seconds.
  `elm_win_fake_add` provides the Elementary parent EWK expects;
  explicit EWK focus makes arrows, OK and Back reach Chromium 120.
- **App bridge:** bounded workers discover installed consumer apps and launch
  them through `app_launcher`. Platform work does not block Chromium's event
  loop. Discovery is capped at 128 apps; launch acceptance is not foreground proof.
- **Boot modes:** both normal and background markers permit dispatch and remain
  valid to the early monitor. `boot.py` supplies the shared mode predicate.
  Background boot keeps the early empty-foreground admission. Normal boot may
  initially report standby: the host waits, bounded by 120 seconds uptime, then
  asks the signed Hub to dismiss the TV viewer before drawing. It admits only
  once that Hub is foreground with the screen on and the compositor ready.
  Another app, source or ISP owner cancels the handoff. The normal-mode monitor
  must retain the admission marker through 125 seconds (background: 65 seconds).
- **Launcher role:** `--native-guard --stay` runs the existing admission checks
  once, then supervises `--launcher-child`. Abnormal exits restart at most five
  times per ten-minute window; intentional clean exits do not restart.
  Page failures exit the child so supervision can recover it.
- **Home and return:** optional Home grab, tracked Live-TV → web Hub detour,
  saved-source re-arm about every 15 seconds, and return after app exit.
- **Wake from standby:** the remote's power button often leaves the system
  running with the screen off. On wake, Samsung shows Live TV and saves it as the
  boot source. A once-a-second worker check reads `memory/pm/state` (1 = screen
  on), the saved source and the foreground app, with no D-Bus call. A readable off
  state followed by screen-on opens a 20 s window. If Live TV is in front during
  it, the launcher takes the Home path: signed Hub handoff, re-arm, native Hub.
  Live TV opened while the screen stays on is left alone. A saved source that
  leaves the Hub is re-armed at once instead of up to 15 s later.
  Compositor focus can restore controls even when Samsung's foreground key is
  stale. `--source-rearm-wait` supplies the existing bounded normal-boot role.
- **Preferences:** one-time import of old native shortcuts/order, selection,
  layout, clock and startup choice, only if WebView has no saved shortcuts.
  Afterwards WebView `localStorage` is independent of both the old native file
  and the signed WGT. Preserve `/home/owner/.config/chromium-efl` on an installed TV.

The native adapter exposes **discovery and launch only**, not a complete Tizen
platform. Web Audio and other browser features can use Chromium where available;
Tizen-specific sound fallback, telemetry relay, monitoring and screensaver behavior
must not be assumed to work just because their UI is present. Retain the signed
web Hub for its ISP-source role and fallback. This does not register the native
window as a normal Samsung application.

## Build and checks

From the repository root, with the existing `samsung-native-collector:bullseye`
image (see [native collector build](../../telemetry/native-collector/README.md)):

```sh
WEBVIEW_OUTPUT_DIR=/tmp/couchroot-webview-build sh native/webview/build.sh
python3 -m unittest discover -s native/webview/tests -p 'test_*.py'
node native/webview/tests/native-shim.cjs
node native/webview/tests/diagnostic.cjs
npm test
```

The build uses Docker with networking disabled, produces ARMv7 softfp code and
rejects GLIBC requirements above 2.17. Output stays outside the repository.
It also produces `minimal-hub-procsample`, a measurement tool that is never
installed with the launcher (see [startup measurement](#startup-measurement)).
The bundle comes from the working tree, including uncommitted web edits.
The C tests use fake EFL/EWK/app-manager libraries; they do not simulate firmware,
security policy, rendering performance or physical panel behavior. Browser tests
require the project's Playwright installation and Chromium.

Standalone application mode (no boot installation):

```text
minimal-hub-webview [--engine=default|upgrade] [--native-bridge] [--defer-show] /absolute/page.html [seconds:1..3600]
```

The launcher installer sets `COUCHROOT_NATIVE_HOME=1`,
`COUCHROOT_NATIVE_SOURCE_REARM=1`, `COUCHROOT_WEBVIEW_DEFER_SHOW=1`,
`COUCHROOT_NATIVE_STATE` to the retained old
native preferences, and `COUCHROOT_WEBVIEW_ENGINE=upgrade` (or `default`). It must
provision `hub/index.html` beside the executable. Use the same owner UID, SMACK
label, read-only bind, Wayland/session environment and normal CPU policy as the
existing QN90A native launcher. Do not copy this model's execution assumptions to
other TVs or weaken firmware checks.

## Bridge boundary

The page sends serialized requests through `document.title`:
`hubbridge:1:<request-id>:discover`, `hubbridge:1:<request-id>:launch:<app-id>`,
`hubbridge:1:<request-id>:ready` (initial UI rendered) or
`hubbridge:1:<request-id>:painted` (that UI's first contentful paint was
presented; a 3-second fallback covers engines without paint timing).
The host replies with `HubNativePlatform.receive(...)` using
`ewk_view_script_execute`. IDs, operations, app IDs, sizes and URL identity are
validated; late, duplicate and unknown replies are ignored. No shell, filesystem,
network listener, settings mutation or uninstall operation is exposed.

EWK has no frame-identity getter on this firmware. The exact loaded URL check and
main-frame title constrain the channel to the loaded page, but **any script in
that page can use the bridge**. Keep the bundle trusted and local. Diagnostic
page titles are sanitized before logging. Worker stdout cannot corrupt replies.

## First-boot recovery

`rollback.py` renders commands; it is not an installer and never contacts a TV.
The private installer must:

1. Verify the device, firmware and current hook; preserve the exact previous
   hook, ownership and mode. Provision a unique root-owned state directory.
2. Generate a `Recovery` for the candidate hash, original hash, hook path,
   backup path and a unique systemd unit name. Store `watch()` as the immutable
   `rollback-command` in that state directory and journal every payload hash.
3. Insert `dispatch()` into the boot hook and verify all installed bytes before
   reboot. The script is read as data and passed as **one `/bin/sh -c` argument**.
   QN90A rejects `/bin/sh /unsigned/script` before its body runs; this caused the
   initial watcher failure. No firmware policy is changed.
4. After the default 150-second deadline, an unaccepted candidate is restored
   only if both candidate and backup hashes match. The watcher verifies the
   restored hash, records `rolled-back`, stops the candidate service and submits
   the signed web Hub fallback. It does not reboot the TV.
5. Check that the watcher is active and has logged `watcher-started`. After
   independently verifying boot, Home and app launch/return, execute
   `accept()` and complete the shared journal. Acceptance and rollback share a
   decision lock: acceptance cannot bless a hook already restored by rollback.

`rollback.log`, `accepted` and `rolled-back` live in the private state directory.
A missing log, failed unit or a hash/lock refusal requires inspection; a submitted
service is not proof of rollback. A crash while holding `decision.lock` requires
manual reconciliation, not deleting the lock blindly. Stop/launch failures happen
after hook restoration and remain visible. Keep manual recovery available.

## QN90A evidence (2026-10-12)

The initial installed WebView candidate passed a software reboot: admission at
9.129 seconds uptime, native loading frame at 10.270 seconds, Home grab ready at
15.505 seconds and page load at about 17.4 seconds. The upgrade library was
observed, 26 apps were discovered and six imported shortcuts appeared in a
1920×1080 compositor capture. Injected OK launched Plex; injected Home returned
to Hub. Terminating Plex through the owner app launcher restored Hub focus and
logged `native-return-focused`, despite a stale framework foreground key.

These are software and compositor observations, not physical-panel latency or
handheld-remote tests. The initial rollback watcher failed before its timer;
a subsequent deliberate unaccepted reboot verified the repaired watcher:
after its 150-second deadline it restored the exact original hook, stopped the
candidate and launched the signed web Hub. Both recovery units exited zero.

An owner restart also exposed a normal-mode dispatch gap: the previous hook suppressed web autostart
before waiting exclusively for background mode. Dispatch and its cancellation
monitor now use both mode markers. A repeat remote power-button restart
revealed a second condition: at 8.5 seconds the display still reported standby;
only later did it become active with the TV viewer foreground. The bounded
normal-mode handoff above handles that transition instead of drawing over the
viewer or requiring a manual Home press. That failed candidate also rolled back
automatically to the signed Hub.
With the standby-aware guard, the owner's next power-cycle test opened Hub
without pressing Home. Logs show one native child: normal admission at 21.792
seconds, native loading frame at 24.295 seconds, Home grab at 35.237 seconds and
page load around 37.3 seconds. The owner observed the signed Hub, loading text,
white/black frames and then the final Hub. This was not a crash/restart loop. The later deferred-presentation change
removes the intermediate native loading window; see validation below. Injected OK launched the selected Crunchyroll
app and injected Home restored native Hub focus. Acceptance was withheld while
an app-exit check was incomplete, and the watchdog again restored the fallback.

A fresh install of the same binary then passed a background software reboot:
admission at 9.561 seconds, native frame at 10.226 seconds and page load around
15.9 seconds. The selected Crunchyroll app launched; injected Home returned to
Hub, and a second launch followed by owner app termination restored native focus
with `native-return-focused`. The active watcher and every installed payload
were checked before acceptance completed the setup journal.

The deferred-presentation build passed another full background software boot.
The logged milestones were:

| Milestone | Seconds after boot (approximate) |
| --- | ---: |
| Admission | 9.21 |
| EWK initialization begins (window hidden) | 10.52 |
| Page load finishes (window hidden) | 16.09 |
| EWK frame after load | 16.17 |
| Window show request, after source/foreground recheck | 16.31 |
| First mapped canvas render (not proof of Hub content) | 16.35 |
| Home grab ready | 16.44 |

There was one child startup. The native loading screen was never mapped; the
rendered Hub capture matched the prior ready-state capture byte for byte.
Injected launch, Home and return after app exit passed before journal acceptance.
An earlier warm trial confirmed EWK rendering with an unmapped window above the
signed Hub. A separate startup screenshot sampler failed and supplied no frame
sequence; logs and the final capture do **not** certify every physical panel
frame or the full normal-mode transition. No person watched this profiled boot.
An initial attempt was declined because the saved source was Live TV after the
warm trial; restoring the configured Hub source preceded the successful cycle.

The repaired buffer sampler subsequently exposed a gap in that earlier claim:
the first mapped frame was only the dark page background. Hub cards arrived
about 2.4 seconds later. The host now waits for the bundled Hub's initial DOM
and fonts, a readiness message before an animation frame, and a subsequent EWK
paint. The hidden view is sized before navigation and remains browser-visible
so hidden startup can continue rendering.

Two full background software reboots with this change produced 33/32 recorded
buffers (28/24 display commits). In both captures, the first nonblank display
commit contained the Hub cards; they stayed visible afterward. There was one
mapped Hub window, no loading text, no full white frame and no return to black
after the Hub appeared. The sampler stopped cleanly after its post-presentation
tail. Home retained native focus and the installed payload hashes were verified
before journal acceptance.

Both boots also exposed early engine failures before any native window mapped:
one aborted inside EWK view creation with allocator corruption; the other loaded
the default engine despite requesting upgrade. The existing supervisor recovered
with Chromium 120. Hub content appeared at 43.36 and 28.78 seconds respectively.
These trials alone did not establish reliable first-attempt Chromium startup;
the later mount-readiness investigation below supersedes that status. Neither captured cycle reproduced the
handheld remote's normal-mode boot, and neither was a physical-panel recording.

The next investigation found a concrete engine-selection race: EWK initialization
started around 9.35 seconds, before the upgrade mount became active at 9.69
seconds (base mount: 9.38 seconds). The wrapper permanently caches its first
selection, so a later filesystem mount cannot repair that process. The host now
checks readable, nonempty engine files before loading EFL/EWK, polling every
50 ms with a 20-second deadline and honoring termination. Tests cover a delayed
upgrade file, unavailable/empty files and default mode without an upgrade mount.

Two full background software reboots of the mount-readiness build then loaded
Chromium 120 on the first attempt: one child each, no failure or supervisor
restart. Hub content appeared at 17.319 and 17.290 seconds. Both frame sequences
showed a single Hub appearance with no white frame or blackout afterward; Home
retained native focus. The engine mounts were already active around 7.6 seconds
on these two cycles, so they validate clean startup, while the delayed-file test
exercises the waiting branch. The earlier allocator abort was not reproduced;
its exact internal cause has not been established. This is two-cycle evidence,
not a long-term stability claim. Installed hashes were checked and the journal
accepted; the guarded rollback remains available for future candidates.

Standby/resume and the WebView Live-TV detour remain unverified. The owner's
"power cycle" was not independently classified as mains removal versus a remote
restart. Pure-native Home/source behavior has separate evidence in its README.

Earlier warm trials verified arrows/OK/Back on both engines, local diagnostics,
visibility notification and bounded exit. Two of twelve default-engine Hub runs
crashed during page loading (SIGSEGV / allocator abort); root cause remains
unknown. The later early-boot upgrade trial also aborted during view creation,
as recorded above. Supervision
bounds recovery attempts but does not prove long-term stability.

### Startup and memory profile (2026-10-12)

Thirteen further background software reboots ran instrumented builds with the
compositor capture and `minimal-hub-procsample`. Measurement candidates were
rolled back. The final candidate was later installed and accepted after another
verification boot: one Chromium start, Hub content at 15.6 seconds, saved tiles
in the first content frame, and the injected-key checks below. Child-relative seconds,
from readable engine files to the first presented frame:

| Segment | `main` behavior (3 clean boots) | Final candidate (5 clean boots)¹ |
| --- | ---: | ---: |
| EFL load, `elm_init`, window | 0.93–1.13 | 0.81–1.08 |
| Engine load in `ewk_set_version_policy` | 4.40–4.88 | 4.71–5.18 |
| View creation | 0.36–0.66 | 0.30–0.39 |
| Navigation to presented window | 1.98–2.67 | 2.42–3.07 |
| Total | 8.36–8.60 | 8.83–9.21 |
| Hub content (compositor, uptime) | 16.99–17.86 | 17.98–19.70 |
| Processes after startup | 5 | 5 |
| Hub-tree CPU until content | 4.44–4.70 s | 4.45–4.54 s |
| Idle CPU (50 s, Hub in front)² | 0.21–0.30 % of one core | 0.21–0.31 % |
| PSS / private, 20 s after start | 91.5–91.8 / 60.2–60.3 MB | 91.4–92.5 / 60.1–60.4 MB |
| PSS / private / swap, settled² | 57.4–58.0 / 30.2–30.8 / 7.9–8.9 MB | 56.8–59.0 / 29.6–31.8 / 6.6–10.2 MB |

¹ Same host binary; three of these boots used the rule as a separate stylesheet.
² Measurement boots only; verification boots launched apps during that window.

The five processes are the supervisor, Chromium host, zygote, renderer and
platform worker. Of the settled PSS, about 25 MB is the shared engine library.
The final candidate's slower engine segment comes before any changed code runs;
boots differ by up to 0.8 s in that segment. Startup time did not improve.

- **Engine load dominates.** `ewk_set_version_policy(1)` makes the wrapper load
  the 88 MB Chromium 120 implementation from its zlib squashfs image: 4.4–5.2
  seconds, about 1.75 s of it CPU (1.5 s kernel), with no major faults. The same
  load in a restarted child later in the boot took 0.55 s. All four cores were
  99.7–99.9 % busy, mainly with Samsung Home, `slive-provider` and preloaded web
  apps. Those apps use the default engine image; the processes found mapping the
  upgrade engine afterwards all started later.
- **Rejected after measurement.** Each of these was built, measured on device and
  removed:
  - Starting the platform worker before EWK left the presentation check
    unchanged at 0.11–0.20 s.
  - A read-ahead helper shortened the engine segment by about 0.5 s but slowed
    EFL by about 0.5 s and used 103 MB of page cache.
  - Lowering the Hub session's autogroup nice to −10 did not change the
    engine's CPU share.
  - On Chromium 120, `ewk_process_model_set` and
    `ewk_memory_optimization_mode_enable` only log, and
    `ewk_context_memory_saving_mode_set` and
    `ewk_chromium_append_command_line_flag` are empty stubs.
- **Intermittent crash.** Two of these boots (one with `main` behavior) aborted
  in `ewk_view_add` with glibc `double free or corruption (fasttop)`.
  Samsung's kernel then waits 100 × 0.204 s for `get_coredump_config` and writes
  no core. That wait does not change with `RLIMIT_CORE` or `PR_SET_DUMPABLE`,
  and signal handlers are not invoked. Restart cost about 23 s: Hub content
  arrived at 40.6 and 43.1 seconds. Fixed; see "Startup crash" below.
- **Stale default tiles (fixed).** Under boot load a compositor frame takes about
  one second. A frame of the static `index.html` markup could therefore finish
  after `ready` and pass for the Hub. 3 of 9 captured boots, `main` included,
  showed the default Plex/YouTube tiles for 70–180 ms before the saved
  shortcuts. With the transparent markup and the `painted` confirmation, 6
  candidate boots showed the saved tiles from the first content frame, including
  one where confirmation followed the frame by 0.33 s. No boot had a white frame
  or a return to black after content. In fast boots the confirmation adds 3–5 ms.

**Remote power button (2026-10-12).** Depending on the press, the power button
either fully reboots the TV or puts it in standby with the system running.
`app-boot-manager` (decompiled from this firmware) treats the power key as
wakeup reason 1. On that full boot it starts Live TV hidden only while
`db/boot/last_service` is a service source (`isp-service` maps to 1); otherwise
Live TV is shown. A software reboot reports reason 0x32/0x34 and is always quiet.
With the wake return installed:
- A remote full reboot came up quiet with the Hub at 17.6 s and no Live TV.
- A quick standby cycle went from display state 4 to 1. Live TV was detected
  1 s later, and the native Hub was active 5.6 s after the screen turned on.
- Idle CPU rose from 0.21–0.31 % to 0.37 % of one core, from the
  once-a-second check.

The final candidate passed the injected-key checks after a single Chromium
start: arrows, OK launching Plex, Home back to Hub, and `app_launcher -k`
returning focus (`native-return-focused`). It also passed them after the crash
recovery above. These are background software reboots, not physical-panel
recordings, handheld-remote normal-mode boots or a crash-rate estimate.

### Startup crash (2026-10-13)

The supervisor records each crash during Samsung's ~20 s hold (`crash.h`): every
thread's `sp`/`pc` from `/proc/<pid>/task/<tid>/syscall`, a bounded scan of its
stack for return addresses (as library+offset), and the executable mappings.
Fatal-signal handlers never run on this firmware, so this is the only in-field
record. Lines start with `launcher-child-crashing`, `launcher-crash-thread`,
`launcher-crash-stack` and `launcher-crash-map`.

The crash reproduces without rebooting. A hidden standalone host
(`--native-bridge --defer-show` with a page that never reports ready, so it is
never shown) was started repeatedly beside the running Hub under a separate
`HOME`. Built as before (`-ldl` only), it crashed in 21 of 170 cold starts,
always during the first browser context creation inside `ewk_view_add`, when
Chromium starts its GPU, IO and ThreadPool threads. glibc reported `double free
or corruption` (`fasttop`, `!prev`, `out`) or `corrupted size vs. prev_size`
on whichever thread noticed (main, `Chrome_InProcGpuThread` or a
`ThreadPoolForeground` worker); one start faulted in `ld.so`.

**Fix.** The host executable did not link libpthread: it arrived only later,
as a dependency of the EFL and Chromium libraries the host `dlopen`s, while the
process had started single-threaded. QN90A runs glibc 2.30, before libpthread
was merged into libc (2.34). Linked with `-lpthread` (loaded at startup) and no
other change, the same host did not crash in 100 starts; every libpthread-linked
build in the investigation was clean (0 of 503), every build without it crashed.
`build.sh` links it with `--no-as-needed` and fails if `libpthread.so.0` is not
`NEEDED`. Paired runs of the final build against the unfixed one:

| Condition | Without | With libpthread |
|---|---|---|
| Upgrade engine, idle | 21 / 170 | 0 / 100 (0 / 503 all variants) |
| Upgrade engine, 3 busy-loop processes | 6 / 60 | 0 / 200 |
| Default engine | 24 / 60 | 0 / 150 |

Boot batches with the fix installed (software reboots): 20 boots, no crash,
Hub content median 17.0 s (control 16.7 s, 15 boots).

Ruled out on the way, each still crashing without libpthread at startup:
never unloading libraries (6 of 119), preloading the license-manager Cynara
plugin, initializing EGL on the main thread first, and Samsung's reference EWK
call order. Forwarding Chromium's Cynara calls through the host first looked
like a fix (0 of 303), but those builds also linked libpthread; without it the
forwarders crashed 2 of 17.

## ABI and evidence

The EFL and EWK view APIs follow the
[Tizen](https://docs.stg.tizen.org/application/native/api/iot-headed/latest/group__WEBVIEW.html)
and [EWebKit](https://ewebkit.github.io/ewebkit-doc/ewebkit2/html/d6/daf/ewk__view_8h.html)
declarations. The QN90A exports were confirmed in the captured rootfs:
`elm_win_fake_add`, `ewk_view_focus_set`, `ewk_view_script_execute`,
`ewk_view_url_get` and `ewk_view_visibility_set`.

**`ewk_set_version_policy`** has no public declaration. All of the following
comes from the QN90A 2301.1 captured binaries.

- **Wrapper**, `/usr/lib/libchromium-ewk.so` (sha256
  `8fb23fa7055953e6d6b27c38b2e1723bc7db9140a585e170f2a4dbc3c872a0ed`).
  - The export at `0x4105b43d` takes an int in r0 and returns an int.
  - Values 0 and 1 are stored in a flag byte at `0x4106400c`. Other values
    are logged as "Unknown preference" and leave the flag unchanged.
  - The call is then forwarded to the implementation's export.
- **Lazy loader.** It reads that flag when it first resolves a symbol:
  - Flag set and `/usr/share/chromium-efl/upgrade/lib/libchromium-impl.so`
    exists: it loads the upgrade engine.
  - Otherwise it loads the default engine, without reporting the fallback.
  - So filesystem readiness must precede wrapper loading, the policy call
    must precede `ewk_init`, and the loaded library must be verified.
- **Engine binaries.**
  - Default `libchromium-impl.so`: sha256 `23bee1f3…e192`.
  - Upgrade `libchromium-impl.so`: sha256 `de041301…cda8`.
  - Both export `ewk_set_version_policy`. Their version strings are
    76.0.3809.146 and 120.0.6099.5.
- **Runtime confirmation.** On the TV, mapped libraries and child argv
  confirmed the upgrade selection.

## Startup measurement

Each `webview event=` line records child-relative wall time, cumulative process
CPU time (`cpu_ms`, all threads of this process only), its kernel part
(`sys_ms`) and, on Linux, major page faults (`majflt`). The startup sequence is:
`main`, `engine-files-ready`, `efl-loaded`, `elm-init-done`, `window-created`,
`ewk-init-start`, `ewk-wrapper-loaded`, `engine-policy-set` (upgrade only; the
wrapper loads the implementation here), `ewk-init-done` (after the
loaded-engine check), `view-created`,
`navigation-start`, `load-finished`, `hub-ui-ready`, `page-frame`,
`hub-ui-painted`, `page-present`, `native-first-render`. Only compositor frames prove that Hub
content was visible; `page-present` is a show request.

`minimal-hub-procsample OUT_DIR EXE_PREFIX SECONDS INTERVAL_MS [SNAPSHOTS]`
runs as root during a private test boot. It follows processes whose executable
lies under the install prefix and their descendants, which includes Chromium's
`efl_webprocess` children but not other web apps' processes. It records
per-thread CPU, state and faults, plus a once-a-second system view (`/proc/stat`
and every process's CPU) that shows competing boot work. Snapshots split PSS,
private, shared and swapped memory into the engine library, other files,
anonymous memory and device mappings. QN90A refuses to execute it directly from
`/tmp` or `/opt` (even as root); run it from a systemd unit that read-only
binds its directory, as the launcher unit does. Keep its output private.

## Boot frame capture

`capture.sh` records QN90A compositor buffers, including direct hardware planes,
plus uptime and Hub-window changes. It uses 1/8-size images, a 512-buffer cap,
a low-memory cutoff and an exit trap that flushes/stops the dump. This is a
firmware-specific diagnostic, not a physical-panel recording or fixed-rate video.
Static frames are not repeated. Keep its output private.

The private installer runs it only during an unaccepted test boot, with a
60-second systemd runtime limit, 5-second stop timeout, and an independent unit
that stops buffer dumping after 65 seconds. Do not leave dumping enabled on
ordinary boots. Encode the script as base64, then pass one shell argument that
decodes it into `/bin/sh` standard input. This prevents systemd from expanding
shell variables in the script before execution; passing the raw multiline body
through systemd caused the original sampler's empty counters and failed capture.
No firmware security setting is changed. Buffer filenames contain leading spaces;
preserve and quote them when reading timestamps or analyzing frames.
