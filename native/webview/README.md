# Native WebView Hub (experimental)

QN90A firmware **T-NKM2AKUC-2301.1 only**. This host runs the existing `web/`
interface in Chromium/EWK inside an owner-UID EFL window. It starts from the
native boot hook. Background admission can precede Samsung's signed web-app
launch path; normal boot uses the signed Hub for a safe viewer handoff.
It is a third launcher option alongside the signed [web Hub](../../web/) and
[pure-native Hub](../../native-hub/); see [the comparison](../../docs/guides/choosing-a-launcher.md).

The source, tests and recovery-command renderer are public. Deployment still
requires a private, model-bound installer using the shared setup journal, enrolled
root agent, exact backups and existing QN90A hook chain. `./tv-setup` does not yet
install this launcher. No vendor libraries, firmware dumps, credentials, private
journals or compiled TV binaries are included. S90D has not been tested.

## Behavior

- **Shared interface:** the build copies the signed package's web file list,
  excluding its manifest, inserts `native-shim.js` after `bridge.js` and appends
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
image (see [native collector build](../../research/native-telemetry/collector/README.md)):

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
