# QN90A boot performance: from ~118 s to ~10 s

QN85QN90AAFXZA, firmware T-NKM2AKUC-2301.1, ARMv7 (4 cores, 1.7 GHz). All times below are
**software milestones in seconds since kernel boot**. For the web Hub that milestone is
the Hub observed in the foreground; for the native Hub it is the first Ecore/Evas
post-render callback. Neither is a panel-photon measurement. Single boots vary by
0.5–1.5 s, so the table lists individual samples rather than averages. The web rows are
historical cohorts summarised from earlier research records, measured with different hooks
and scripts. The last row is the hook/card cohort for this change; later re-arm and visual
runs, including one visual boot at 9.26 s, are recorded in the native Hub README.

## Progression

| Stage | Launcher | Time to Hub | What changed |
| --- | --- | ---: | --- |
| First autonomous quiet boot | Web | 117.7 | ISP source role + root-agent relay; blank for ~2 min |
| Relay priority | Web | 109.6 | Earlier relay scheduling |
| Completion repair | Web | 61.5 / 64.7 / 66.0 | Fixed failing vendor completion producers |
| Launch on app readiness | Web | 46.4 / 47.3 | Direct launch, no late root relay |
| Faster guards and launch interval | Web | 36.9 / 40.5 | Native source reads, earlier preparation |
| Native launcher, early dispatch | Native | 14.3 / 14.8 | Ecore/Evas window from the boot hook |
| Native-only, in-process admission | Native | 13.1–15.0 | Web autolaunch suppressed, admission in-process |
| **Normal CPU policy + dispatch first** | **Native** | **8.83 / 10.01 / 10.05 / 9.02 / 10.04** | This change |

## Finding 1: the native process ran at idle priority

A profile of the retained build showed the main thread used about **0.35 s of CPU**
between exec and its first frame, but took **2.7–5.8 s**. It sat runnable while all
four cores were 100 % busy with 9–20 runnable tasks. That points to CPU scheduling
rather than EGL, fonts or disk I/O as the main cost. The Live TV viewer maps the same
libraries at 1.3 s, so they were probably cached; residency was inferred from shared
mappings, not measured, and the profile still recorded some D-state samples and major
faults, so other costs are not excluded.

A per-thread `/proc` sampler during boot showed why: `native-hub` had scheduling
policy 5, **`SCHED_IDLE`**. Static analysis of the firmware's systemd matches that
observation:

- `exec_child` calls `sched_setscheduler(0, SCHED_IDLE)` before `execve` for services
  started while a vendor boot-idle flag is set and `starter.target` is loaded. That
  happens from about 7.3 s.
- A unit that sets `CPUSchedulingPolicy` takes an earlier branch and skips the demotion
  (the decompiled code has other exemptions too).
  Samsung's own boot-relevant units use exactly that (sensord, mbr-daemon, adagent,
  pisa, Bluetooth).
- The decompiled vendor boot helper sleeps 50 s after app readiness before ending the
  mode. That timing is static; it was not observed at runtime.

Earlier `nice -5` and autogroup `-5` trials could not help, because neither changes an
idle-class policy. The fix is `systemd-run -p CPUSchedulingPolicy=other`: normal nice-0
scheduling, not real-time or elevated. Main-to-first-frame dropped to **0.8–1.1 s** in
the three pre-card boots (1.07 / 1.58 s in the two card-binary boots).
The vendor flag is deliberately left enabled for every other service.

## Finding 2: hook layering delayed dispatch by ~1.8 s

The vendor hook (`AT-HUB.service` → `/opt/etc/parseinfo.sh`) starts at 5.8–7.0 s.
Earlier experiments had stacked hash-checked wrapper layers for casting deferral,
service masks and voice activation in front of the native dispatch. Each layer forks
`sha256sum` and shells while the starter batch saturates the CPU.

The dispatch block now moves verbatim to the outermost layer. The other layers still
run afterwards, in the same order, before the services they gate start. Native `main`
moved from about 9.2 s to 7.2–9.2 s.

## What did not help

| Experiment | Result |
| --- | --- |
| `wayland_shm` software renderer | 14.8 / 14.2 s, no gain |
| `nice -5` (process) | 13.8 / 14.8 s, no gain |
| Autogroup nice -5 | 15.2 s, no gain (autogroup weight cannot lift `SCHED_IDLE`) |
| Shutdown-time source repair via systemd `ExecStop` | Never runs: deviced reboots without stopping units |

## Remaining limits

- **Before `main`:** the vendor hook fires at 5.8–7.0 s, after a systemd dispatch stall
  around 4.7–6.8 s whose cause is not established. The dispatch `systemd-run` call can
  wait 0.2–1.5 s while PID 1 starts the starter batch. Those two costs now dominate the
  remaining spread.
- **Physical observation:** the panel and audio were not observed for these boots.
  Earlier owner observations reported blank, silent native boots on earlier builds; they
  do not measure these boots, and no boot is guaranteed silent.
- **Scope:** the measurements come from one firmware on one TV.

## Reproducing the profile

The native launcher has an opt-in profiler (`COUCHROOT_NATIVE_PROFILE=1`, see
[the native Hub README](../../../../native-hub/README.md#opt-in-profiler)). It reports
per-milestone thread CPU, faults, a 4 ms sample of the main thread's state and
syscall, and system-wide busy/iowait and runnable counts. It reads the process's own
`/proc` entries plus system-wide `/proc/stat` and `/proc/diskstats`, and stops at the
first frame.
