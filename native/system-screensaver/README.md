# S90D native Asteroids screensaver

Status: live, reversible replacement of Samsung's native dot renderer, with
**automatic loading after a full reboot verified on this TV**. No dashboard package update
is required; it replaces the renderer Samsung's system-wide idle launcher uses.

Target tested: QN55S90DAFXZA, firmware 2130.0, Tizen 9 / T-PTMDAKUC,
192.0.2.12. Do not apply to the QN90A or another firmware using these hashes.

## Design

Samsung's `com.samsung.tv.glscreensaver-launcher` retains the idle path, black
background, key grabs, power-key exclusions, child lifetime, and return-to-app
handling. Its ContentList.json selects `com.samsung.tv.spotlight-ss`.
That app's managed LegacyPlayer calls ten native exports in
`/usr/apps/com.samsung.tv.spotlight-ss/lib/arm/libgl-demo-app.so`.

`renderer.c` implements that ABI with GLES2. `simulation.h` runs a silent,
self-playing Asteroids-style scene: an autonomous ship seeks targets, leads its
shots, avoids nearby rocks, coasts and thrusts, and wraps at the screen edges.
Swept bullet collisions split large rocks; small fragments disappear. Hits and
ship collisions emit fading sparks and expanding dim rings. Ship destruction
causes a brief pause and a respawn away from rocks. New asteroids fade in at the
edges to keep the scene evolving. There is no static score, logo, text or starfield.

The warm champagne/gold/bronze colors still derive from the launcher's
`web/style.css` (`#c8b58f`, `#dfc184`, `#77634a`) at much lower digital intensities.
Source-over blending prevents additive hotspots; the shader caps RGB at 0.18.
The frame starts as opaque black. The final minute fades down, and at 600 seconds
from the first successful renderer creation the native loop clears to black and
skips simulation and geometry drawing. GL context recreation in the same process
preserves that deadline. A new host process starts a new countdown; Samsung's
unchanged content rotation is configured for 36,000 seconds on this firmware.
Black output is **not standby** and does not perform panel compensation.

### Rendering and resource bounds

- Fixed 30 Hz simulation; no more than six catch-up steps per render callback.
  The wall clock controls the black deadline even if frames are delayed.
- Fixed pools: 24 asteroids, 18 shots, 128 sparks and 6 expanding rings. No
  per-frame allocation, networking, file writes, audio or child processes.
- `mesh.h` batches all antialiased vector strokes into one triangle draw call.
  Only small line quads are shaded; the old full-screen procedural fragment
  pass is gone. Geometry and VBO contents are reused between physics ticks;
  only simulation changes, viewport changes or context recreation trigger a
  rebuild/upload. Edge wrap copies are culled before geometry generation.
- One reusable 384 KiB vertex pool and VBO, with a hard 16,384-vertex capacity.
  Overflow drops excess geometry rather than writing beyond the pool. Typical
  uploads are much smaller. Circle vertices are precomputed, and asteroid
  outlines are generated only when rocks spawn.
- Native idle activation, remote wake, power handling and all panel settings
  remain Samsung's responsibility.

### OLED precautions and research

Samsung’s [Panel Care guidance](https://www.samsung.com/ae/support/tv-audio-video/how-to-use-panel-care-on-a-samsung-oled-tv/)
recommends Pixel Shift for static content and describes dimming fixed logos.
Its [OLED image-retention guidance](https://www.samsung.com/hk_en/support/tv-audio-video/how-to-troubleshoot-burn-in-or-image-retention-on-your-samsung-oled-tv/)
explains the native saver and notes that some apps, live video and external
inputs may not activate it. We preserve that native policy, key handling,
power behavior, and all panel settings. We do not bypass dimming or service-menu
protections, run a pixel-refresh routine, or expand idle coverage to inputs that
Samsung excludes. The current Panel Care setting values have not been independently
verified by this change.

The design reduces persistent illuminated content: most pixels remain black,
geometry continually traverses the panel, there are no stationary labels or
logos, and prolonged idle becomes fully black. The ten-minute cutoff is our
conservative policy, **not a manufacturer-specified safe duration**. Shader RGB
values are not measured nits; picture modes and the display pipeline affect
actual output. Motion, low digital output and sample tests cannot certify zero
burn-in risk or equal cumulative wear across every pixel.

Samsung’s [Screen Optimization guidance](https://www.samsung.com/hk_en/support/tv-audio-video/how-to-use-screen-optimization-on-a-samsung-oled-tv/)
explains that maintenance can run after normal remote power-off with mains power
connected. Continue normal standby use; the black saver does not replace it.
These Samsung regional instructions may differ in menu names/timing on this US
model; no regional numerical maintenance schedule is assumed here.

Sources accessed 2026-09-20.

The source lives in root-owned `/opt/minimal-saver`, with read-only access
through the overlay and the original library's SMACK label. A **read-only file bind mount in PID 1's mount
namespace** overlays the original library path. The original VDFS firmware bytes
are never overwritten. Automatic loading changes only the AT-HUB entry in
Samsung's writable service cache, as described below. No SMACK rules, account
files, firmware partitions, package registrations, idle timeouts, or app data
are changed.

## Build and checks

Use Debian bullseye cross packages `gcc-arm-linux-gnueabi` and
`libc6-dev-armel-cross`, plus GLES2/KHR headers from libgles-dev/libgl-dev.
This device uses **ARMv7 softfp**, not armhf. The final shared object's flag is
`0x5000200`; its required GLIBC versions are 2.4 and 2.17 (TV has 2.30).
From the repository root, use a private copy of this TV's `libGLESv2.so.2.0`, named `libGLESv2.so.2`:

```sh
GLES_LIBRARY_DIR=/path/to/private/tv-libraries sh native/system-screensaver/build.sh
node research/archive/system-screensaver/verify-shader.cjs
```

The verifier compiles the real C simulation and mesh builder with warnings as
errors and exercises twelve eleven-minute deterministic runs. It checks collisions,
splitting, forced ship destruction/respawn, finite positions, palette bounds and
vertex capacity. Binary fixtures from three runs (every ten seconds) are rendered
with the exact native GLSL in Chromium WebGL. It checks opaque alpha, lit area,
digital brightness, non-additive overlaps and the black deadline, saving
`bin/preview.png` and `bin/verification.json`. Sampled pixel dwell is a coarse
regression check, not an exhaustive continuous-time proof or panel measurement.
`verify-render-loop.c` additionally calls the real renderer against a stub GLES
driver and deterministic clock, proving VBO reuse, resize/context invalidation,
bounded catch-up, wall-clock fading and clear-only output at/after ten minutes.
With GLES2/KHR headers available (no real GLES library is needed for this test):

```sh
cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-parameter \
  -I/path/to/gles-headers research/archive/system-screensaver/verify-render-loop.c \
  -lm -o /tmp/couchroot-verify-render-loop
/tmp/couchroot-verify-render-loop
```

Native compilation resolves every symbol against the TV GLES library. `bin/` is
gitignored.

Reviewed original SHA256:
`4f0b36d9639a194936def6250a03db1383db284f11f74d83ec7dda50420befaa`

Reviewed replacement SHA256:
`db5656113275e613d9475c09af1c768cd8ad57d60eac31213214684721cc418a`

Rebuilds must be reviewed; update the renderer hashes in installers, rollback and
`boot/Program.cs`, then rebuild the helper and update its installer hashes.

## Apply, preview, inspect, and restore

From this directory on the configured Mac, using the existing private
`~/.local/share/samsung-tv-research` toolkit:

```sh
python3 control.py apply          # optional current-boot-only installation
python3 control.py enable-boot    # install the reviewed automatic boot path
python3 control.py update         # upgrade the persistent geometric version; then reboot
python3 control.py disable-boot   # restore the original cache; keep current image
python3 control.py preview
python3 control.py status
python3 control.py rollback
```

Apply validates the exact original hash and refuses an unknown existing mount.
Preview starts Samsung's existing native launcher. Applying while a saver is
already running does not replace its mapped library: dismiss it and let the next
idle activation load the replacement, or preview after dismissal.

Rollback first disables automatic loading, dismisses the active saver, waits
for its normal exit, unmounts only a matching source/path/hash, verifies the stock
hash, and removes the old app-shared copy. Root-owned backups and inactive helper
files remain in `/opt/minimal-saver` for recovery. Samsung's launcher delays process termination by five seconds after a
key. With automatic loading enabled, the one-shot helper restores the mount during
boot. After `disable-boot`, the next full reboot uses Samsung's original renderer.

The control script uses the existing one-shot private root collector. The boot
helper runs once under the existing root service and exits; it is not a resident
daemon. All root helper mounts, temporary accounts/keys and
staged root files are removed and the original account/key hashes checked after
each operation. Full private evidence remains in the toolkit's dated dumps.

## Asteroids update validation on 2026-09-20

- Twelve eleven-minute native simulation runs: 4,018 hits, 1,623 splits and 63
  autonomous ship destructions; forced collision/respawn assertions also pass.
  Maximum sampled batch: 3,342 vertices, with no pool overflow or invalid position.
- 201 actual mesh/GLSL frames across three seeded runs: maximum channel 45/255,
  peak lit area 0.652%, opaque alpha throughout, correct warm palette order,
  and fully black output from 600 seconds. Repeated overlaps remained below the
  cap. These are software regression bounds, not OLED safety guarantees.
- ARMv7 softfp and .NET builds pass. The updater keeps the previous geometric
  renderer/helper pair in `/opt/minimal-saver/before-asteroids`; the older
  `/opt/minimal-saver/before-geometric` backup remains untouched. Installer and
  boot-helper hashes are updated together. Full-reboot acceptance is required
  because the preceding update showed that live hash/mount checks alone do not
  prove Samsung's app loader has accepted a new native library.

- The render-loop cache/lifecycle test passes against the final renderer.
- AddressSanitizer and UndefinedBehaviorSanitizer also pass all twelve timelines
  and forced collision/respawn checks.
- Full reboot changed the boot ID to `00000000-0000-4000-8000-000000000037`.
  The first SDK-only inspection confirmed the new renderer hash/read-only mount
  and AT-HUB exit 0, before any root/apply action. Evidence:
  `sessions/20260920T161812.361267Z-run`.
- Native captures at 16:19 UTC show the autonomous ship and rock field with
  changing shots/effects. Three frames measured maximum channel 45, 45, 43
  and lit area 0.341%, 0.317%, 0.270%. All retrieved PNG hashes match their TV
  originals. Native processes mapped the new renderer inode. Evidence:
  `dumps/20260920T161919Z` and private `analysis/asteroids-saver/shot*.png`.
- Back dismissed the native content/launcher processes and returned focus to
  Minimal Hub at 16:20:45. The signed diagnostic, service offset table and
  reviewed patched boot-cache hashes remained unchanged. Evidence:
  `dumps/20260920T162033Z`.

- The final cache-enabled build was installed with a matching rebuilt helper.
  The prior tested Asteroids pair was retained separately in
  `/opt/minimal-saver/before-asteroids-cache`; the geometric rollback pair remains
  in `before-asteroids`. A second full reboot changed the boot ID to
  `00000000-0000-4000-8000-000000000007`. Initial SDK-only checks confirmed the
  final renderer hash, read-only overlay and AT-HUB exit 0. Evidence:
  `dumps/20260920T162622Z`, `dumps/20260920T162703Z`,
  `sessions/20260920T162847.142482Z-run`.
- With no preview/apply command after that reboot, Samsung automatically started
  the final renderer at ordinary idle. SDK evidence:
  `sessions/20260920T162932.613957Z-run`. The final native capture at 16:32 UTC
  shows the ship/asteroids, maximum channel 40/255 and 0.260% lit pixels;
  its retrieved SHA256 matches the TV original. Evidence:
  `dumps/20260920T163230Z`, private `analysis/asteroids-saver/final.png`.
- A ten-second steady-state sample of Samsung's complete managed content process
  measured about 64% of one CPU core and 69,612 KiB RSS, unchanged across the
  sample. This includes the managed host and display callbacks, not just our
  simulation; no isolated GPU/power measurement or controlled stock-renderer
  comparison was made. Mesh caching is verified by the render-loop test, but
  these measurements do not establish a whole-process CPU improvement.
  Evidence: `sessions/20260920T163220.716162Z-run`.

## Geometric update validation on 2026-09-20

- ARMv7 softfp build and .NET boot helper build pass with warnings treated as errors.
- Three sampled eleven-minute timelines: maximum channel 45/255, maximum lit
  area 9.01%, longest continuously nonblack sampled pixel run 44 seconds.
  These are regression bounds, not Samsung safety thresholds.
- Full-opacity overlaps also peak at 45/255; all samples at/after 600 seconds
  are exactly opaque black. Warm palette order is maintained.
- `update.sh` validates the old/new renderer and boot-helper hashes, saves the
  previous pair in root-owned `/opt/minimal-saver/before-geometric`, dismisses
  the saver, waits for process exit, and replaces files by rename. It preserves
  SMACK labels and the existing boot cache. On a caught installation failure it
  restores the previous pair and mount; interrupted mismatched pairs fail the
  boot hash check and leave the stock renderer available after a reboot.

- A live swap initially produced `DllNotFoundException` in Samsung’s app loader.
  The same binary loaded correctly after a full reboot, without any security
  policy change. **Treat a full reboot and native visual check as required for
  this update**; a successful bind/hash check alone is insufficient.
- At 15:58 UTC a controlled reboot changed the boot ID to
  `00000000-0000-4000-8000-000000000038`. The first read-only SDK check (before
  any root/apply operation) confirmed the new renderer hash and read-only mount.
  AT-HUB ran the updated helper and exited 0. The native content process later
  mapped the new library from writable VDFS, and a 1920x1080 compositor capture
  confirmed the warm geometric image.
- Two native captures (16:00:46 and 16:02:20 UTC) both peak at channel 45/255,
  with 8.87% and 8.42% lit pixels. 358,476 pixels changed between the captures,
  confirming motion on the real compositor, rather than just the host preview.
  At 16:02:28, Back had dismissed both native saver processes and restored
  Minimal Hub focus. The signed diagnostic and service offset table hashes
  remained unchanged; the persistent cache remained the reviewed patched hash.
- Initial binary image transfers through the private collector failed; root
  sessions were cleaned up and verified, then the image was successfully fetched
  through the existing SDK text-capture route as base64. No transport/security
  configuration was changed. Private evidence lives in
  `sessions/20260920T155924.075045Z-run` (first post-boot check),
  `dumps/20260920T160001Z/preview.txt` (native mapping),
  `dumps/20260920T160044Z` (capture) and `dumps/20260920T160217Z` (wake).
- After wake, no saver process was present at 16:04:16. At 16:04:48 Samsung
  had automatically started launcher PID 5523 and renderer PID 6373, without a
  preview/start command. A fresh native capture showed the new geometry. Evidence:
  `dumps/20260920T160445Z` and the private `analysis/geometric-saver/idle.png`.
- The full 600-second timeline is verified in the software renderer; it has not
  been timed end-to-end on the physical panel. No optical brightness or aging
  measurement is claimed.

## Original abstract version validation on 2026-09-20

- Shader compilation/render/motion tests passed; sampled maximum channel 48/255.
- Corrected ARM softfp renderer loaded in Samsung's real `DN_spotlight-ss`
  process; `/proc/PID/maps` confirms the custom file's inode on writable VDFS.
- A native 1920x1080 screen capture shows the four dim shapes.
- the owner confirmed **dim colored shapes moving slowly on the physical TV**.
- Automatic native idle activation was verified at 15:18:48 UTC: new launcher
  PID 11587 and renderer PID 13624 appeared after the dashboard was left idle,
  without another preview/start command. Both prior processes were absent at
  15:18:19 after wake.
- Launcher/renderer started over Minimal Hub and Plex. Back returned to the
  expected underlying app; the hub was restored after testing. Plex playback and
  every app-specific idle policy were not separately exercised.
- Rollback was executed and the original file's SHA256 verified before the final
  corrected build was installed. Global passwd/public-key hashes remained intact.

## Automatic boot loading

Samsung's `AT-HUB.service` already runs at `starter.target` as root, after the
existing buxton, udev, network, and device services. Its stock action executes
`/opt/etc/parseinfo.sh`, a signed script that writes build/model information to
`/proc/target_version`. That script remains **byte-for-byte unchanged**.

This firmware reads cached unit text from `/opt/etc/systemd/oneservice` using
fixed offsets in `oneservice.table`. `prepare-boot.py` validates the exact cache
hash and changes only the first 209 bytes (AT-HUB's entry). The replacement keeps
the original After dependencies and starts:

```text
/usr/bin/dotnet /opt/minimal-saver/Boot.dll
```

Every byte after offset 208 and the entire offset table are unchanged. The
original files are backed up on the Mac and on the TV. The cache is replaced
atomically. PID 1 keeps its current cache file open across daemon-reload, so the
new definition takes effect at the next full boot.

The .NET helper first runs the original signed diagnostic script. It then checks
its enabled marker, root identity, mount namespace, renderer source hash, stock
firmware renderer hash, and existing mounts. When compatible it installs the
same read-only file bind mount tested previously, logs its boot ID/result, and
exits. Overlay failures leave the original renderer in place; diagnostic exit
status is preserved. The helper has no networking, command input, persistent
process, or requirement for the Mac to be online.

Build and prepare on the configured Mac:

```sh
dotnet build boot/Boot.csproj -c Release
python3 prepare-boot.py /path/to/private/original/oneservice
python3 control.py enable-boot
```

The installer checks the hashes of all staged files. Updated builds require
reviewing/updating those hashes in `enable-boot.sh`. The original cache is
`3ffa26a62b1550c3e85993953bb59cf3cc38d688ddfd4f9d500cc37b6db15123`;
the patched cache is
`6cf17c5e96002b350bc7a7f4ba9a4c1b55a2d3fe9213570bcb7c3beab750598c`.

`disable-boot` restores the exact original cache and removes the enabled marker.
It leaves the helper available while PID 1 may still hold the patched cache;
without the marker it does not apply an overlay. The next full reboot uses the
original service command. Unknown independently modified cache contents cause
rollback to stop rather than overwrite unrelated changes.

This integration is specific to the inspected firmware cache. Firmware updates
may rebuild the cache and remove the hook; the renderer hash guard also skips
an incompatible firmware renderer. Recheck after an update. No firmware update
or factory-reset survival is claimed.

## Full reboot verification

At 15:31 UTC on 2026-09-20, Samsung's native deviced Reboot method restarted the
TV. The boot ID changed from `00000000-0000-4000-8000-000000000039` to
`00000000-0000-4000-8000-000000000040`.

The first post-boot check was read-only through SDK, before invoking a root
collector or any apply command. It showed:

- The custom renderer hash at the stock library path and a read-only bind mount
  from `/minimal-saver/libgl-demo-app.so` on the writable `/opt` filesystem.
- AT-HUB launched the .NET helper at 15:31:45 UTC and exited successfully at
  15:31:55 UTC, status 0; no helper remained running.
- The original diagnostic script and service offset table hashes were unchanged.
- After ordinary idle time, Samsung launched the native saver automatically.
  A post-boot 1920x1080 capture showed the dim colored shapes.
- A post-boot Back key dismissed both native saver processes and returned focus
  to Minimal Hub; the persistent hook and read-only overlay remained enabled.
- Disabling automatic loading restored the exact original cache hash. Re-enabling
  restored the reviewed patched hash; the already mounted library was not rewritten.

Private evidence: `dumps/20260920T152608Z` holds service-cache backups and xattrs;
`sessions/20260920T153321.016139Z-run` is the initial read-only post-boot proof;
`dumps/20260920T153502Z` holds native screen/renderer verification. The reboot
interrupted SDK file cleanup after the root helper had exited; the prepared
cleanup removed those staged files after boot and verified original account/key
hashes. A Buds connection-manager service failed after this boot (exit 1); the
screensaver helper exited 0, the hub displayed normally, and no change was made
to that unrelated service.
