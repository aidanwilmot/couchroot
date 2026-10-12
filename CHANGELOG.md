# Changelog

## 0.1.0.dev1 — unreleased

- Add the experimental native Hub (`native-hub/`, QN90A only). It is an Ecore/Evas
  launcher started from the earliest boot hook. QN90A software time to a rendered Hub
  is 8.8–10.1 s across five reboots; the best web path was about 37–47 s.
  - Root cause found: Samsung's systemd starts late boot services at `SCHED_IDLE`.
    The native unit opts out with `CPUSchedulingPolicy=other`, the vendor
    convention, at normal priority.
  - Dispatch moved ahead of the other hook layers.
  - See the [launcher guide](docs/guides/choosing-a-launcher.md) and the
    [boot performance record](docs/devices/qn90a/boot-performance.md).
- Reduce QN90A Live TV boots after watching TV. Opening Live TV/TV Plus rewrites
  the saved boot source at once, so native re-arms `isp-service` about every 15 s
  while it runs. A power-off before the next re-arm can still start one Live TV boot.
  Home from Live TV asks the web Hub to open, then raises native once a re-arm no
  longer sees the viewer in front. Picture and audio were not measured.
  - The Home fallback is now one tracked attempt at a time, with a launcher deadline,
    a fixed overall deadline, and cancellation if another app takes the foreground,
    the worker restarts or a reply is late. Mock-tested only; not yet on hardware.
- Refresh the native Hub visuals (designed in two parallel passes, see
  `native-hub/DESIGN.md`):
  - Layout: one margin system, a quiet header clock, a balanced grid and a single
    footer control bar with quiet key hints.
  - List pages: consistent rows, previews and badges.
  - Tiles: dark brand-tinted, with a soft bottom brand glow and one Bold wordmark rule.
  - Focus: a bright ring with a dark gap, a halo, and brightened brand light.
  - The validator checks contrast against the composited tile, at rest and focused.
  - QN90A capture verified; one boot rendered at 9.26 s, within the earlier range.
- Generate native tile art from validated per-app specs (`native-hub/cards/`), with
  contrast, clean wordmark-area and in-card checks; 12 cards use 73 retained scene
  objects in the current harness, instead of 386. Add an opt-in startup profiler
  (`COUCHROOT_NATIVE_PROFILE=1`); its stop flag is now mutex-guarded.
- Root agent: archive and maintain the request journal; add the Python transport
  used by the setup engine.
- Reorganize the repository. Device scripts move to `tools/`, signing and packaging
  to `scripts/`, and the native launcher to `native-hub/`. Docs are grouped into
  `guides/`, `devices/`, `research/` and `project/` with an [index](docs/README.md).
  Fix two QN90A operation scripts that no longer parsed after the move and the card
  preview's repository root; an offline test now parses every tracked Python file and
  checks repository-root expressions.
- Defer initial app discovery and monitoring I/O until Hub has focus, keeping
  saved shortcuts available first. Avoid inspecting the native sound fallback
  when Web Audio is available. QN90A startup profiling did not establish a
  consistent total boot-time reduction; the tested three-second relay settle
  was reverted to five seconds in relay 0.2.4. See the startup profiling report.
- Avoid a false launch-failure dialog when Samsung Home opens as an overlay
  while Hub stays visible, as verified on QN90A. Missing callbacks and reported
  failures still offer recovery.
- Move shortcuts directly in the Home grid, undo the latest removal, and offer
  optional hold-OK editing (off by default). Keep launch progress visible until
  Hub leaves the screen; let Back dismiss it. Reuse unchanged Home tiles on
  return, defer catalog refresh, and improve secondary-text contrast/readability.
  Both TVs received the UI update; see the hardware validation record for the
  exercised behaviors. Hardware wake latency and HDMI handoff still need
  model-specific verification.
- Add remote-operated launch recovery with Retry and Samsung Home, remember
  Home selection across restarts with a First favorite option, and replace dimmed
  scroll-edge rows with directional cues. Existing shortcut order is preserved.
- Cache the static Home backdrop separately from interactive content and isolate
  footer painting; use solid utility-page backgrounds and batch scroll-edge
  updates. Preserve artwork, focus rings and settings, with a browser regression
  that checks actual paint reuse during remote navigation.
- Polish the Hub UI: 16:9 tiles with em-scaled artwork, one rounded focus ring,
  shared rows/preview/hint layout for Edit apps, Add apps and Settings, unified
  dialogs, an actionable empty Home, in-list loading/failure notes, dimmed
  unavailable tiles and error-toned status lines. Storage keys are unchanged.
- Fix the TV monitoring dialog on Chromium 76 (`inset` and px sizing), focus
  rings clipped after scrolling, and a late app list erasing "added to Home".
- Keep applied runs recoverable until saved choices and ownership ledgers are
  durable. Schema 2 records local rollback state and preserves subsequent edits;
  recover older journals with their original checkout.
- Reconcile interrupted inverse operations and verified staging files, preserve
  unknown staging content, and prevent new apply inspection while a run is pending.
- Bound nested reboot observations with one remaining deadline, without launching
  Hub or retrying the reboot request. Report uncertain diagnostic cleanup.
- Add crash/storage-failure tests and source-only Linux/container validation,
  plus a cross-path QN90A saver reproducibility check in CI. Physical hardware
  acceptance and owner disclosure/licensing decisions remain release blockers.

## 0.1.0.dev0 — unreleased

- Separate portable firmware profiles, private site settings, preferences and
  independently enrolled signing trust; remove personal defaults from current files.
- Replace the CLI's private dump-collector dependency with a source-built, bounded
  model-specific root runner. Hardware validation remains outstanding.
- Bind recovery journals to destination/trust, check source before reconciliation,
  reject apply after rollback starts, and continue reversible rollback when
  managed application reinstall requires manual recovery.
- Add dependency checks, deterministic native builds, offline platform CI,
  privacy scan, installation/security documentation and release acceptance gates.

The CLI version follows semantic versioning once released; `devN` marks an
unreleased development tree. Package versions on a TV remain separate and must
increase for in-place installs. Journal schema changes require explicit migration
review; never upgrade an unfinished run in place. A supported firmware change is
not implied by a CLI patch version.
