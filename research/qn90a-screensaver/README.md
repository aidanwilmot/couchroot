# QN90A Asteroids screensaver

**Status (2026-09-20): the owner selected a dashboard-owned five-minute timer.
QN90A Minimal Hub 0.4.0 includes that timer; Asteroids 1.0.1 provides the corrected
visible renderer. The global timeout override has been removed. Native selector
persistence remains unresolved. The final dashboard path passed a real five-minute idle trial after Plex;
the owner confirmed visibility and physical Right returned to the dashboard.**

Target: QN85QN90AAFXZA, 192.0.2.11, T-NKM2AKUC-2301.1, Tizen 6 / ARMv7.
Never apply this TV's fixed native offsets to another model or firmware.
Minimal Hub adds the QN90A-only idle timer. Saved configuration, Home routing
and AirPlay rules are unchanged.
Read [ROLLBACK.md](ROLLBACK.md) before making device changes.

## How it works

The signed standalone app `MiniSave01.Saver` reuses the S90D's C simulation,
geometry through embedded WebAssembly and WebGL 1. The QN90A now has its own
fragment shader: four times the source ink, capped at 0.65, and wider strokes.
The prior thin OLED-level output appeared black to the owner on this LCD even
while compositor captures contained faint geometry. No S90D source or deployment
was changed. Simulation runs
at 30 Hz with bounded catch-up, fixed pools, 2 MiB WASM memory and a 384 KiB
vertex buffer. Rendering fades to black at ten minutes; context recreation
retains that deadline. The web runtime adds overhead beyond those fixed buffers.
It makes no network requests, plays no audio, writes no saved state and exits
when hidden or woken. No resident root service or process killer is installed.

Chromium 76 rejects synchronous WASM compilation above 4 KiB. The corrected build
uses asynchronous compilation of embedded bytes, without a resource fetch.
Both synchronous bootstrap errors and rejected initialization exit the app.

Unlike the S90D, this TV has no `glscreensaver-launcher` or `spotlight-ss`.
Its native screensaver runs inside Enlightenment's `e-mod-tizen-screensaver`.
The Wayland `screensaver_set_appid` API accepts the saver, but ordinary app
transitions reset it to DEFAULT. A one-time API selection is insufficient.

`memory-apply` changes the DEFAULT string selection in the already mapped stock
module: one four-byte literal pointer and a 17-byte NUL-terminated app ID in
unused mapped padding. It checks the exact firmware file hash, expected memory
bytes and process mapping first. It briefly stops the compositor, rechecks the
bytes, writes and verifies them, then resumes in a `finally` block. A failed
readback attempts to restore the prior bytes. It changes no instructions or
on-disk firmware. The helper exits after the operation. Native setters are asynchronous: they
flush a Wayland request without acknowledging its effect. The helper keeps the
connection open and checks the selected ID/timeout before reporting success.
Immediate process exit produced stale readback in an earlier rollback trial.

Samsung retains idle eligibility, app-specific enable/disable behavior,
wake handling and its native fallback if launching the saver fails. The original
fallback branch was inspected, but an intentionally failed launch has not been
validated on the TV. This does not force a saver over playback or excluded inputs.

## Timeout ownership

The final policy follows the owner's clarification: Minimal Hub owns five minutes
of idle while visible; Plex and other apps keep their own timeout and playback
policy. The dashboard cancels its timer while hidden and starts a fresh five
minutes on return or input. At the deadline it launches `MiniSave01.Saver` through
the existing ordinary signed-app launch privilege. Launch failure leaves the
Hub usable and waits for new input/return before retrying. It sends no native
screensaver setter, creates no background service, and does not poll other apps.

Samsung's public [AppCommon API](https://developer.samsung.com/smarttv/develop/api-references/samsung-product-api-references/appcommon-api.html)
provides enable/disable, but no arbitrary timeout setter for web apps. This is
therefore a **dashboard idle timer**, not a request to change Samsung's native
interval. It is packaged only by `scripts/sign.py --profile MinimalHubQN90A`; the shared
S90D web package is untouched. The timer is installed code and needs no Mac/root
helper after reboot. The separate system-wide Asteroids selector is still
memory-only and still needs manual reapplication after a full reboot.

## Diagnosed native timer reset (superseded approach)

The native `screensaver_set_default()` API sends two requests: select DEFAULT
and set **7,200,000 milliseconds**. The follow-up observed the saver itself and
Plex requesting 7200. A one-time request for 300 therefore did not persist across
app transitions. No evidence tied this reset to Minimal Hub's sound effects.

A temporary 32-byte ARM policy mapped every exact 7200 request to 300. Two full
five-minute native trials passed, but it also overrode Plex's timeout. The owner
preferred per-app ownership, so **no supported command now installs that policy**.
`apply` removes it, retains the native Asteroids selector, and restores 7200.
Its exact known bytes and emulator test remain for guarded rollback of earlier
sessions. Enable/disable requests were never patched.

## Build, sign and use

With Emscripten installed (tested with Debian Bookworm's package):

```sh
sh research/qn90a-screensaver/build-web.sh
node --test research/qn90a-screensaver/verify-web.cjs
~/.local/share/samsung-tv-research/.venv/bin/python research/qn90a-screensaver/verify-timeout.py
node research/system-screensaver/verify-shader.cjs
python3 research/qn90a-screensaver/package.py
```

Generated `core.js` and `shaders.js` are ignored. Signing uses the existing private
`MinimalHubQN90A` profile and stages outside Git. Install the printed private
`AsteroidsSaver.wgt` with the Tizen CLI, explicitly selecting `192.0.2.11:26101`.
The working package is recorded privately in
`signing/builds/qn90a-saver-97llz7wl/manifest.json` (version 1.0.1).
The previous renderer has a privately signed forward-version rollback, prepared
before installation. The ARM test needs clang, pyelftools and unicorn 2.1.4.

From the repository root:

```sh
~/.local/share/samsung-tv-research/.venv/bin/python tools/qn90a/screensaver.py inspect
~/.local/share/samsung-tv-research/.venv/bin/python tools/qn90a/screensaver.py apply
```

Build the QN90A dashboard with `python3 scripts/sign.py --profile MinimalHubQN90A`.
This stages version 0.4.0 plus `hub-idle.js` outside Git. Install the printed
`MinimalHub.wgt` on `192.0.2.11:26101` with the existing profile. See the exact
forward-version dashboard rollback in ROLLBACK.md.

`timeout-five-minutes` is now only a native diagnostic setter; it is unnecessary
for the dashboard timer and other apps can overwrite it. `timeout-restore`
removes the old policy and restores 7200. `memory-apply` is selector-only;
`apply` additionally removes the superseded global policy and restores 7200.

Reapply the optional system-wide selector manually after a full reboot if needed.
The dashboard timer itself does not require reapplication. The command is firmware-guarded
and idempotent for its exact known original/patched states. It refuses unknown
memory contents. If `inspect` reports no mapped module after reboot, first run
`tools/qn90a/screensaver.py module-restore` to recover the stock module, then `apply`.
Ordinary standby/wake retention has not been verified.

For a short acceptance test, `idle-trial` changes only the idle timeout to 15
seconds. It does not select the app or enable a saver that an application has
disabled. Finish with `timeout-restore` to return to the final dashboard-owned policy,
or `restore` for the original Samsung behavior. `wake` sends one native Right key. `capture` takes one compositor
screenshot; capture alone is not proof of animation or native activation.

## Rejected persistent approach

A copied native module was staged in Enlightenment's writable user module search
directory. The full restart did not load it; the native saver was left disabled.
The copy was removed immediately and the stock module explicitly reloaded.
Correcting directory labels did not fix loading. An isolated loader diagnostic
also rejected an **unchanged** copy with `failed to map segment from shared object`,
while the firmware original reached normal symbol resolution. This evidence
points to restrictions on copied executable mappings, not just the string patch.
The failed staging commands have been removed from the supported CLI.

Other inspected routes do not provide the S90D's existing writable boot hook:
QN90A's systemd oneservice cache is in read-only firmware, and its user-manager
unit path excludes writable user configuration. Its native app-defined event
registration requires a preloaded app or Samsung platform certificate. The
existing private signing profile does not meet that requirement. No package
identity, certificate flags, boot script, policy or firmware was altered to
work around these restrictions. A persistent route remains future work.

## Earlier verification (before the follow-up)

Automated local checks passed:

- Actual WASM/WebGL rendering, offline loading, bounded catch-up, ten-minute
  black deadline, GL restoration preserving the deadline, key/hidden exit and
  synchronous bootstrap failure handling.
- Shared C simulation across 12 seeds and 11 minutes each, including geometry
  bounds, dim warm palette, opacity and black deadline checks.
- All 24 existing QN90A Home/casting/cleanup tests.

Live TV checks (SDK/native input, not physical-remote confirmation):

- Signed installation succeeded using the existing private identity.
- At native idle, state changed to screensaver-on with `MiniSave01.Saver`
  foreground. A compositor capture shows the gold ship and asteroids.
- A native Right key cleared screensaver-on, returned to Minimal Hub and left
  no saver process. This is the corrected build, not the initial blank trial.
- Opening Plex retained the patched default app ID. Plex subsequently disabled
  the native saver and reset its timeout to 7200; no saver started in that trial.
  Its playback/idle policy was left intact.
- The memory redirect was restored to Samsung and reapplied with native ID
  readback, exercising the actual rollback. The timeout helper also verifies
  native timeout readback rather than relying on the API return code.
- Original passwd and signing-verifier hashes remained unchanged after every
  bounded root operation, and temporary root helpers exited and were removed.

Private evidence includes sessions `20260920T173621.044661Z-qn90a-saver-watch`, `20260920T173956.206595Z-qn90a-root-home-saver-capture`,
`20260920T174023.423487Z-qn90a-saver-state`,
`20260920T174113.484006Z-qn90a-root-home-saver-inspect`, and
`20260920T174233.743894Z-qn90a-root-home-saver-inspect`.
Firmware copies, screenshots, certificates, signed packages and full traces
remain under `~/.local/share/samsung-tv-research`, outside Git.

The owner withdrew an earlier visual report because it concerned the other TV.
That report is excluded from QN90A evidence. In the follow-up, the owner
confirmed that physical Right immediately returns from the black-looking saver
to the dashboard. The old renderer was explicitly rejected as appearing black.

Earlier setter readback (not a five-minute acceptance result): `MiniSave01.Saver`, native saver Enabled and timeout
300 seconds. The full rollback to the stock selector and 7200 seconds passed,
then Asteroids and 300 seconds were reapplied. Evidence:
`20260920T175420.503753Z-qn90a-root-home-saver-restore`,
`20260920T175424.436537Z-qn90a-root-home-saver-memory-apply`, and
`20260920T175428.220154Z-qn90a-root-home-saver-timeout-five-minutes`.
Task-created SDK copies and the diagnostic screenshot were removed after hash
checks; private copies remain on the Mac. No failed user module remains on TV.

These were the outstanding items before the follow-up; the newer evidence below
supersedes the earlier visibility result. Full-reboot persistence is absent.


## Follow-up evidence (2026-09-20)

- Baseline at 18:00: native Enabled / 300 seconds / MiniSave01, but no saver
  foreground yet. At 18:03 the saver was running and its native request history
  named its process as requesting 7200 seconds. This is the observed timeout
  reset, not an inference from a setter return code.
- The owner reported the old saver looked black and confirmed physical Right
  immediately returned to the dashboard. A fresh 15-second diagnostic activation
  again looked black on the panel while the compositor capture contained dim
  geometry. Version 1.0.1 widens/brightens only this TV's renderer.
- Full native rollback of both runtime patches at
  `20260920T181232.214514Z-qn90a-root-home-saver-restore` succeeded, including
  native 7200-second readback. Reapplication succeeded at
  `20260920T181341.079256Z-qn90a-root-home-saver-apply`.
- Version 1.0.1 installed with MinimalHubQN90A. Installed config, core, shaders
  and saver JavaScript hashes exactly match the signed build and local source.
  WGT SHA-256: `186bfc27bc1b281025593b7d953fa43920dc48ba7cd67d9a7e951ba7cbe69aa7`.
- Trial 1 started with native Right at uptime 3204.04–3204.20. Read-only samples
  found native off at 3503.61 (299.41 seconds after input completion), on at
  3504.85 (300.65 seconds), and MiniSave01 foreground at 3506.21 (302.01 seconds).
  No setter, key or launch was submitted during that complete idle period.
  114 samples across eleven bounded requests are preserved privately in
  `qn90a/five-minute-trial-1.json` and the referenced timestamped sessions.
- The owner then confirmed “It is showing now” on this QN90A. The capture
  `qn90a/five-minute-visible-1.png` shows the brighter gold ship/asteroids.
- Post-launch native history still records the saver's requested 7200, while
  effective readback is **300** with the policy active. Evidence:
  `20260920T182039.960084Z-qn90a-root-home-saver-inspect`.
- Home row 82 and both accepted AirPlay return rows were read back intact;
  database integrity is `ok`. The live system manager's UnitPath contains
  `/etc/systemd/system`, `/usr/lib/systemd/system` and transient `/run` locations;
  `/usr/local` is also on read-only firmware, not an `/opt` symlink.
- Local checks: 1,016 ARM emulator cases validate the exact deployed thunk,
  its native tail-call and preserved registers; WASM/WebGL checks include actual
  framebuffer brightness, warm palette, opaque black background, offline
  behavior and the ten-minute deadline. All 24 QN90A integration tests pass;
  the unchanged shared S90D simulation/shader tests also pass.


The follow-up also inspected the actual `/sbin/init.wrapper` (the generic
`rc.sysinit` is not evidence of this TV's active boot path). It starts
`run_enlightenment.sh` and then `/opt/data/DeviceTracker/Dlog_buffer.sh` on normal
boot. That existing writable script carries a Samsung UEP signature. A harmless
new script containing only `exit 0`, temporarily staged in the same directory,
was explicitly rejected by the firmware shell: **`[uep][bash] the file is NOT
signed!!`**. The probe was deleted in `finally`; the original diagnostic script
was never modified or manually run. Its SHA-256 remains
`80c00041929fbb37ea1ce31322b4f5143d8d9ab3678a9c09a6a99e05af4ea74e`.
Evidence: `20260920T182630.726545Z-qn90a-root-home-saver-script-probe`.
This is a concrete additional boot-integration blocker; the widget signing
profile does not supply Samsung's firmware script signature. No signature
verifier, trust key, logging policy or diagnostic service was changed.


## Power-cycle recovery evidence

The bounded native standby experiment was unsuccessful: it disconnected SDB and
suspended its own planned Power On. That operation was removed from the CLI.
The owner turned the TV back on physically. The recovered boot ID was
`00000000-0000-4000-8000-000000000030`, different from the trial's
`00000000-0000-4000-8000-000000000031`. This proves a restart occurred, not ordinary
standby retention or its failure. No root helper remained running. Exact staged
files were removed after hash checks and both global system-file hashes matched.
Evidence: `20260920T183847.437999Z-qn90a-standby-recovery-inspect` and
`20260920T183910.840228Z-qn90a-standby-recovery-cleanup`.

Post-restart inspection also found the native screensaver module **disabled and
unmapped**, with timeout zero, even in Minimal Hub. Empty directories from the
old rejected override remained. They were removed with non-recursive operations
that refuse nonempty directories. Loading the canonical module name failed;
loading the original absolute firmware path succeeded. The reason the boot loader
disabled the module is not conclusively established; empty directory shadowing is
a possibility, not a proven cause. `module-restore` now includes this directory
cleanup and checks actual native selection/readback. No copied module was tried.
Stock selection / 7200 and subsequent Asteroids / 300 readback both succeeded.
Private logs: `qn90a/post-reboot-modules.log`, `post-reboot-absolute-restore.log`,
and `post-reboot-apply.log`.

Opening Plex before the restart recorded another 7200-second request, but the
policy preserved effective 300. Native Home returned to Minimal Hub. No playback
was started; this is evidence of transition handling, not playback acceptance.
Home row 82, both AirPlay return rules and database integrity were checked intact.
Physical AirPlay return and active-playback exclusion were not retested.


Trial 2 (before the owner selected dashboard ownership) started at uptime 535.31
on the new boot. Last native-off sample was 834.36 (299.05 seconds); first native-on
was 835.67 (300.36); saver foreground was 837.24 (301.93). No key, setter or launch
was sent during that interval. Evidence: `qn90a/five-minute-trial-2.json`.
This verifies the superseded native policy, not the new dashboard timer.


## Final dashboard policy evidence

- QN90A dashboard 0.4.0 signed with MinimalHubQN90A and installed. The installed
  idle script, index and config hashes match the signed staging exactly. The
  pre-update dashboard's config/index/hub/bridge hashes matched the source used
  for the signed forward rollback package.
- Package: `signing/builds/hub-hqkx955d/MinimalHub.wgt`, SHA-256
  `b1900df8bba92e50a1cdd953e5622e103a8892afe10763b735bdf3060ee3bd73`.
- The old global policy was actually restored, and native readback returned 7200
  with pointer `000bbf71` / normalized=False. The selector remains MiniSave01.
  Evidence: `qn90a/dashboard-policy-native-apply.log`.
- Plex launch then read **Disabled / 7200**, with its appcommon plugin as the
  last native requester. After Home, Minimal Hub read **Enabled / 7200**.
  This demonstrates respect for Plex's native policy and the absence of the
  global normalization. No media playback was started.
- All 41 Hub tests pass, including four new idle lifecycle cases, plus the
  actual WASM/WebGL renderer checks and all 24 QN90A routing/cleanup tests.

- Final dashboard trial: native Right completed at uptime 1162.78. Asteroids
  first appeared foreground at 1464.40, **301.62 seconds** later, with native
  screensaver-on **False** throughout. The native timer had read 7200 before
  the trial. This establishes that the dashboard timer, not the old native
  override, caused activation. No key, setter or app launch was submitted from
  the Mac during that five-minute interval. Evidence:
  `qn90a/dashboard-five-minute-wake.log` and `dashboard-five-minute-trial.log`.

- The owner confirmed **“Visible; Right returned to dashboard”** for the final
  dashboard-owned activation. At 18:58:38, readback showed Minimal Hub foreground,
  native saver off, and no saver process. This physical confirmation applies to
  the final path, not merely the earlier native trials.
- Exact known SDK package copies and the captured screenshot were removed after
  hash checks. No root helper/staging directory, script probe or rejected module
  directory remains. Global passwd, verifier and Samsung diagnostic-script hashes
  match their originals. Home/AirPlay rows remain intact; database integrity is
  `ok`, and AirPlay reports `ready`. Evidence:
  `20260920T185902.495672Z-qn90a-final-screensaver-cleanup-and-routes`.

Remaining limits: no ordinary standby/cold-boot acceptance trial was completed
for the final dashboard timer. Its installed lifecycle requires no runtime patch,
so it is designed to survive reboot; that is distinct from measured power-cycle
acceptance. The optional system-wide Asteroids redirect does not survive full
reboot. Native module boot loading also needs further diagnosis if it again comes
up disabled. No supported persistent system-wide boot hook was found under the
owner's constraints. Physical AirPlay and actual streaming playback were not
retested, though their routes and Plex's native disable request were preserved.


Samsung Home fallback was launched successfully as `com.samsung.tv.csfs` in the
partial-app slot. Native Home returned to Minimal Hub with no partial app.
Final inspection reads **Enabled / 7200 / MiniSave01.Saver / normalized=False**;
Hub is foreground and native saver is off. The five-minute setting belongs to
Hub's installed timer. Machine-readable acceptance is in
`inventory/qn90a-screensaver-20260920.json`; full traces remain private.
