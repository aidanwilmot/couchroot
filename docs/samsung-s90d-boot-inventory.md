# S90D boot-to-dashboard inventory design

Status: recorder implemented and two instrumented full restarts captured. A
repeatable 40-second Samsung boot-splash wait explains the late resume request.
The normal helper and dashboard are restored and a third full restart without
instrumentation confirms the same timeout. The implementation section supersedes
the proposed mechanism.

The question is **where power-on-to-visible-and-responsive-dashboard time goes**.
A running process, an active service, a rendered page and a visible panel are
four different milestones. Report them separately.

## Findings from the existing boot

S90D QN55S90DAFXZA, firmware T-PTMDAKUC-0090-2130.0, boot ID
`00000000-0000-4000-8000-000000000007`. Times below are seconds since kernel boot,
not seconds since mains power was restored. This was the earlier software full
restart used for screensaver validation, not a measured unplug/replug boot.

| Time | Evidence | What it establishes |
| --- | --- | --- |
| 1.812 | systemd userspace timestamp | PID 1 userspace initialization milestone |
| 2.071 | preserved kernel log: enlightenment signals `/run/.wm_ready` | Window-manager readiness signal |
| 2.639 | kernel log contains PID 442 named `MiniHub001.Hub` | Dashboard-named process exists; JS/visibility unknown |
| 2.856–39.730 | `app-boot-manager.service` process timestamps | 36.9 seconds of process lifetime, including waits |
| 4.655 | avocd signals `/tmp/avoc_ready` | Vendor AV readiness event |
| 7.426 | dashboard-named PID observes `/tmp/vconf_ready` ready | Its startup has reached a configuration dependency |
| 10.135–19.964 | AT-HUB/screensaver helper process timestamps | 9.8-second lifetime, not proven added dashboard delay |
| 37.723 | app boot manager signals `/tmp/app_ready` | Late vendor boot milestone |
| 39.798 | display-manager oneshot completes | A late check of an already-existing readiness marker |
| 70.489 | SDB service becomes active | Remote collection misses early boot |
| 182.292 | systemd finish timestamp | Overall boot-job completion; not dashboard visibility |

AT-HUB is `Type=simple` and was marked active at 10.135 seconds, essentially at
process start. Its process exit at 19.964 seconds is not automatically an ordering
barrier. `app-boot-manager` does not declare an After/Requires edge to AT-HUB in
the captured state. Indirect resource contention remains possible; none is proven.

The signed diagnostic script is short and contains no explicit sleep. Splitting
managed runtime startup, diagnostic execution and overlay application into timed
spans will avoid attributing the whole helper lifetime to its diagnostic child.

915 loaded unit records were collected. Some long-lived services exit normally
well after the screen may be usable; ranking process lifetimes cannot identify
a critical path. One iot-hub-control setup unit reports timeout, but we have no
evidence that the dashboard waits for it.

## Available evidence and gaps

- `systemd-analyze` is absent. Use `systemctl show` monotonic properties and
  dependency edges directly. Unit files on disk can differ from Samsung's cached
  active definitions: inspect `show`, not just `cat`.
- Journal directories exist, but `journalctl -b` reports no journal files.
- A current dmesg snapshot began around 69 seconds; early records had wrapped.
  Samsung's `/tmp/hsm_boot_klog` preserves about 1.3–46.5 seconds for this boot.
  Collect it immediately after each measured boot; verify freshness using boot ID,
  contemporaneous messages and the capture manifest. Its coverage is partial.
- `dlogutil -d` returned no app messages and reports `enable_apps(0)`. Do not
  depend on console output or enable broad vendor logging for the first trial.
- Wall clock changes from the epoch to current time during startup. File mtimes
  and wall-clock log lines alone are unsuitable for duration calculations.
- App boot-manager analysis exposes waits for `/tmp/avoc_ready`, `/tmp/dbus_launch`,
  `/tmp/deviced-ready`, `/run/ps_agent.pid`, `/tmp/wm_start`, `/tmp/app_ready`,
  `/tmp/tvs_ready` and `/tmp/firstscreen_ready`. Observe these; never create or
  signal vendor readiness events to accelerate startup.

## Measurement design

### 1. Read-only baseline collector — prepared now

`research/s90d-boot-inventory/operations.json` collects identity, systemd timestamps
and dependencies, available logs, preserved boot log and Home/startup settings.
Use the existing private root toolkit from the repository root:

```sh
DUMP_OPERATIONS_FILE="$PWD/research/s90d-boot-inventory/operations.json" \
  python3 "$HOME/.local/share/samsung-tv-research/gather-dumps.py"
python3 research/s90d-boot-inventory/summarize.py /PRIVATE/DUMP/unit-timestamps.txt
```

Verify the collector manifest and per-operation stderr. Empty/missing records
are unavailable evidence, not zero-duration events. The unit query handles
`-.mount` using `--`. The summarizer preserves missing timestamps, labels service
readiness limitations and reports overlapping lifetimes without summing them.

### 2. Bounded on-TV recorder — proposed implementation

Add an opt-in diagnostic launch to the existing reviewed AT-HUB helper, before
its diagnostic work. Launch one native recorder without waiting for it. Keep the
original service ordering, diagnostic behavior and overlay behavior unchanged.
The trace starts around AT-HUB entry (10 seconds in this baseline), so immediately
copy retained kernel data and later copy Samsung's preserved boot log to recover
earlier evidence. This is not complete pre-kernel instrumentation.

Proposed recorder contract:

- Root-owned `/opt/boot-inventory/enabled` marker; no marker means no recorder.
  Create output exclusively, reject symlinks, acquire a nonblocking per-boot lock.
- Record boot ID, firmware/build, app version, helper hash and trace schema.
  Use CLOCK_MONOTONIC timestamps; store paired CLOCK_BOOTTIME/CLOCK_REALTIME
  samples for clock mapping and to detect wall-clock jumps.
- Watch known readiness-marker parent directories with inotify, recording the
  initial state separately from observed transitions. Already-present markers
  are left-censored, not events at recorder start. Do not consume vendor IPC.
- At 1 Hz sample selected process identities/start ticks, CPU ticks, RSS, process
  I/O counters, `/proc/stat`, `/proc/meminfo`, disk counters and available pressure
  counters. Identify PID reuse by start ticks. Avoid tracing every syscall or
  repeatedly invoking the full systemctl/root collector during boot.
- Record Home/startup/foreground changes through a validated read-only vconf
  client. Capture compositor focus/window mapping changes if a low-overhead API
  is available; otherwise use a bounded, slower query with its latency recorded.
- Stop at 180 seconds since recorder start even if dashboard markers are absent.
  Cap the trace at 4 MiB per boot, retain at most three sessions, and record
  truncation/errors. Buffer writes and flush in small batches; no per-frame I/O,
  network dependency, screenshots loop, startup sleeps or retries of failed units.
- Keep trace data private; collect timing/counters/app IDs, not app content,
  credentials or network payloads. Pull logs after the screen is usable.

Add monotonic spans inside Boot.dll for entry, diagnostic start/end, overlay
start/end and exit. Feature-gate these along with the recorder. Stage matching
helper hashes through the existing installer, retain the current known-good pair,
then validate the next boot. Do not add another global startup service.

### 3. Dashboard markers — proposed implementation

An instrumented dashboard build records a fixed-size in-memory timeline using
`performance.now()`: earliest script entry, model load, initial DOM render,
key-handler attachment, visibility/focus changes and two animation-frame
callbacks after initial rendering. Feature-detect Performance APIs.

The last marker means the page has had a rendering opportunity, not that photons
reached the panel. A page may render while hidden behind Samsung's launch overlay.
Persist this small summary once, under a separate versioned diagnostic key;
never alter favorites or introduce network requests to boot. Retrieve it using
the existing app inspection path after startup. Since app console logs are
currently disabled, validate retrieval on a warm launch before the boot trial.

Treat JS timings as their own relative clock. Correlate them with native time
using a tested timestamp exchange bracketed by monotonic reads, and report the
uncertainty bound. If no reliable bridge is available, retain separate timelines
rather than aligning `performance.timeOrigin` to a wall clock that jumped.

### 4. Physical visibility and responsiveness

Record one external video showing the power action and TV screen. Mark Samsung
logo, first dashboard frame and the first response to a single direction key.
A compositor capture alone cannot detect every panel-level overlay, as the
screensaver investigation already demonstrated. Record the key-test time; don't
mix it with passive render milestones. A 60 fps recording bounds frame selection
to roughly 17 ms, while power-action/kernel alignment has separate uncertainty.

Distinguish mains restoration, remote full restart and ordinary standby wake.
Confirm a changed boot ID for actual restarts; ordinary wake may keep the same ID.
The external recording supplies the firmware/panel portion before kernel time 0.

## Trial and analysis sequence

1. Save current boot helper, dashboard artifact, startup settings and their hashes.
   Record network, HDMI devices, power method and settings; keep them fixed.
2. Validate the recorder deadline/output cap and dashboard marker retrieval without
   a boot-policy change. Confirm trace code cannot wait on the dashboard.
3. Collect three runs of the owner's slow boot method. Report each run plus median
   and range. Keep software restart and standby controls in separate groups.
4. Construct a timeline: power → kernel → prerequisites → actual app launch →
   page ready → foreground/window visible → physical image → key response.
5. Attribute each gap to evidence: prerequisite wait, queued launch, runtime/page
   work, overlay/foreground delay, or panel presentation. Mark unexplained gaps.
   Correlate CPU/I/O pressure with waits; correlation alone is not causation.
6. Only then test one implicated change against the same baseline. In particular,
   compare enabled versus disabled instrumentation to measure its own overhead;
   do not disable arbitrary services merely because they have long lifetimes.

Rollback removes the recorder marker, restores the exact known-good helper/hash
pair and uninstrumented dashboard artifact, and removes only diagnostic files.
No service cache restructuring, firmware changes, panel-care changes or log-policy
changes are needed for this proposed first pass.

## Private baseline evidence

Under `~/.local/share/samsung-tv-research/`:
`dumps/20260920T164321Z` (identity, selected units, current log),
`dumps/20260920T164403Z` (log availability), and
`dumps/20260920T164452Z` (915 unit records and preserved boot log).
The early generic unit-query attempts produced empty output; the final query is
corrected and validated. Original account/key hashes and temporary-root cleanup
passed after every read-only collection. Full raw logs remain outside Git.

## Implemented diagnostic variant

The implementation uses the existing signed .NET host. A warm native executable
probe was denied and loading an unsigned native sampling library was also denied;
no execution or security policy was changed. The managed Recorder.dll runs on a
foreground thread inside the opt-in Boot.dll variant, avoiding a second runtime.
AT-HUB remains Type=simple and becomes active immediately. Its instrumented process
lifetime intentionally extends through the trace; `helper-work-complete` records
when the actual diagnostic/overlay work finished. Do not rank that extended
service lifetime as a boot delay. The normal screensaver helper source/artifact
is unchanged; build-helper.py produces a separate variant under ignored bin/.

The recorder samples at approximately 1 Hz for 180 seconds, with a 185-second
hard exit guard and a shared 4 MiB output budget. The original signed diagnostic
has its own existing 8-second timeout. FileSystemWatcher records selected marker
events; initial state is explicitly left-censored. File reads capture counters
and selected process stats, and read-only vconf access records foreground changes.
It captures the preserved kernel log at entry and around 60 seconds, and keeps at
most three ordinary session directories. An exclusive per-boot directory prevents
duplicate recording. Root-owned directories and no-follow exclusive file opens
protect output. The recorder does not run shell commands or launch subprocesses.

`sign.py --boot-trace` adds the optional timing script only to a private diagnostic
package. Normal packages do not contain it. Three small boot summaries and the
latest ASCII record use separate localStorage keys; favorites are never edited.
A 5-second validation build proved a normal, non-debug launch saves a readable
summary. The boot build captures 120 seconds after script entry. `read-trace.py`
reassembles fragmented LevelDB log records and reads saved summaries offline,
without enabling the remote debugger. A late stable wall/monotonic anchor aligns
relative performance timestamps, avoiding the early epoch-to-real-time jump.
It refuses alignment without nearby agreeing anchors and reports an uncertainty
allowance. This is still not a physical-panel timestamp.

Private pre-trace backup: `dumps/20260920T164933Z/before.tar.gz`, SHA256
`148d979c1aea45887c730b72ee69115895106a0f30253579abe1d0a14351caef`.
It contains the exact original helper, renderer, installed widget and app storage.
The installed widget was 0.3.8; repository 0.3.9 adds a flex-gap compatibility probe.
The diagnostic widget is version 0.3.10. A same-version signed rollback built from
exact pre-trace widget sources is saved at `signing/boot-trace-rollback/MinimalHub.wgt`,
SHA256 `40c482d06db40b61e1e50a740c0ca2a7f83db8caf47614a1b2e734f574b38ca9`.

Build: `python3 research/s90d-boot-inventory/build-helper.py`.
The reviewed install-helper.sh/restore-helper.sh guard exact old/new hashes.
They record this specific trial deployment, not a general installer: the warm
probe had already created the root-owned directory and Recorder.dll, and a repeat
install deliberately refuses an existing Boot.before.dll backup. Review/stage
new artifact hashes and preserve the backup before another deployment.
Run only through the existing root collector. collect-trial.json gathers the
private trace and storage archive after completion. No credentials or raw private
logs are committed. A normal signed reinstall of the rollback package removes
page instrumentation without uninstalling or clearing preferences.

Warm validation: the recorder stopped after five seconds with an explicit
`deadline` end record. Dashboard initial DOM render was 581 ms after script entry,
window focus 639 ms, and the second post-render frame 641 ms. These warm-launch
figures are not the cold-boot result. All 37 existing UI/behavior tests and two
new timing/storage-bound tests pass. LevelDB full/fragmented/partial record checks
also pass. Private evidence: `dumps/20260920T165555Z`, `dumps/20260920T165748Z`.

## Measured full-restart results (2026-09-20)

The dominant identified delay is `/usr/bin/app_resume` waiting for
`/tmp/boot_splash_resumed` with `timeout=40000`. In both instrumented restarts,
this wait expires with `ret=0`; it then signals `/tmp/root_app_resume_requested`.
The same sequence exists in the earlier, uninstrumented boot log. These are
vendor IPC event names in the preserved kernel log, not a recommendation to
create files with those names.

All numbers below are seconds since kernel boot. Dashboard estimates use a late
stable clock anchor (±0.1-second allowance); foreground is sampled at about 1 Hz.

| Milestone | Earlier normal boot | Trace 1 | Trace 2 |
| --- | ---: | ---: | ---: |
| Boot-splash wait starts | 2.890 | 2.657 | 2.805 |
| Boot-splash wait expires | 43.007 | 43.007 | 43.011 |
| Root-app resume requested | 43.010 | 43.013 | 43.014 |
| Dashboard script begins | Not measured | 7.482 | 7.947 |
| Initial dashboard DOM rendered | Not measured | 7.753 | 9.180 |
| Second frame after dashboard render | Not measured | 7.848 | 9.586 |
| Dashboard first observed as system foreground | Not sampled | 43.377 | 43.370 |
| Managed helper entry | Not measured | 17.640 | 18.719 |
| Helper's diagnostic/overlay work complete | Not measured | 19.246 | 20.020 |

the owner observed approximately **42 seconds until the dashboard appeared**. This
is an approximate physical observation, not synchronized video; it supports the
43-second kernel timeline without establishing exact power-to-kernel alignment.
Browser focus and rendering events occur much earlier and do not establish that
the panel was already showing the dashboard. The traced dashboard's initial DOM
work took about 0.27 and 1.23 seconds after script entry, respectively.

The identified wait dominates the gap between page readiness and system resume.
Why the expected splash acknowledgement is absent remains unproven. The next
focused investigation is the producer/consumer handoff between `boot_splashscreen`,
`app_resume` and the configured root application. Do not shorten the timeout,
signal readiness artificially, or remove unrelated services based on this trace.
No boot policy, panel-care behavior or vendor readiness event was changed.

### Recorder cost and coverage

Both instrumented runs ended with `deadline`, around 199.36 and 200.17 seconds
since boot. Their complete session output was 2,913,167 and 2,923,096 bytes,
respectively, below the shared 4 MiB cap. The existing helper process intentionally
remained alive until recording ended; its actual startup work finished around
19–20 seconds. The first run's sampled helper CPU counters increased by about
15.1 CPU-seconds over 179 seconds and its maximum sampled RSS was about 26.8 MiB.
Those counters include the helper and recorder together. Instrumentation is not
free, and there is no isolated CPU-cost estimate for the recorder alone.

SDB access started late and inconsistently (about 105 seconds in trace 1; its
service was observed starting at 303 seconds in trace 2 after reconnection).
Remote connection availability is therefore not a proxy for dashboard readiness.
The recorder independently preserves earlier evidence. Kernel log coverage is
partial, and these are software full restarts, not measured mains-disconnect
boots. This experiment does not supply a distribution of physical cold-boot time.

Private trace 1: `dumps/20260920T170333Z`, boot ID
`00000000-0000-4000-8000-000000000008`.
Private trace 2: `dumps/20260920T171001Z`, boot ID
`00000000-0000-4000-8000-000000000009`.
Offline summaries are in `analysis/boot-inventory/trial1.json` and `trial2.json`.
All collection operations returned zero with empty stderr and verified transport
hashes. The LevelDB reader handles complete/fragmented `.log` records and skips
partial trailing records; it is not a general SST/LevelDB recovery utility.

The normal helper was restored from its hash-verified backup and the opt-in marker
removed (`dumps/20260920T171030Z`). The pre-trace dashboard source was reinstalled
in place using the signed rollback package, preserving app storage. The installed
version remains 0.3.10 because the rollback is a same-version update. Dormant trace
files remain private on the TV for evidence; the normal helper has no recorder
hook and the normal dashboard contains no timing script.

### Final control and restored state

The third restart in this experiment used the original helper and uninstrumented
pre-trace dashboard. Boot ID `00000000-0000-4000-8000-000000000010`, private evidence
`dumps/20260920T171246Z`. The splash wait began at 2.730 seconds, expired at 43.007,
and requested root-app resume at 43.012. The three newly captured resume requests
therefore fall within 43.012–43.014 seconds (median about 43.013), including the
control. These are internal milestones, not three physical stopwatch results.

The control helper finished normally at 19.452 seconds; its boot log confirms the
custom screensaver overlay active with diagnostic exit zero. The dashboard was
the current system foreground application when collected. Helper, renderer,
signed diagnostic and systemd cache hashes match their pre-trace values. Every
installed JS/CSS/HTML/icon asset exactly matches the pre-trace backup; no
boot-trace.js remains in the installed widget. The recorder marker is absent.
Original account/key hashes and temporary root-file cleanup also passed. The
collector's final cleanup verification was interrupted during two reboot requests;
it was rerun successfully after reconnection, including this final control.

This completes the inventory and identifies a repeatable startup wait. It does
not yet change the TV's boot duration or prove why the splash event is missing.

## Follow-up: missing native splash resource

The [acknowledgement investigation](samsung-s90d-splash-acknowledgement.md) traced
the producer to Samsung's splash-window visibility callback and found the
Home-ID-derived native resource missing. It documents the exact code path,
read-only evidence and a reversible experiment to validate the suspected cause.

The implemented follow-up uses Samsung's native splash with an explicit resource
path through the existing boot helper. A controlled reboot advanced root-app
resume from 43.012 to 22.468 seconds. The acknowledgement record corrects the
initial writable-path inference and distinguishes internal timing from physical
visibility. The compatibility helper is now installed; normal helper restoration
above describes the end of the earlier inventory experiment.
