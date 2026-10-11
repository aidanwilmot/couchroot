# QN90A one-time memory cleanup

2026-09-20, QN85QN90AAFXZA at `192.0.2.11`, firmware
`T-NKM2AKUC-2301.1`, boot ID `00000000-0000-4000-8000-000000000005`.

Minimal Hub 0.3.9 is installed. Home/startup routing is still Samsung's original
configuration; see [the integration record](samsung-qn90a.md). This cleanup does
not fix or change routing. It does not need root.

## Applied cleanup and recovery

With Minimal Hub open, these three background applications were terminated once
through Samsung's normal app manager:

- Prime Video: `org.tizen.primevideo`
- YouTube's native runtime: `com.samsung.tv.cobalt-yt`
- Samsung Home: `com.samsung.tv.csfs`

All three were confirmed absent afterward and still absent about 40 seconds
later. Minimal Hub stayed in the foreground. Installed apps, saved accounts,
shortcuts and system settings were not deleted or altered. No recurring task,
process killer, privileged daemon, service mask or boot change was added.

The initial Internet termination caused Samsung to launch a new browser process;
Netflix also remained running after the normal termination request. Neither is
included in the cleanup command. The inspected context-manager configuration has
a browser recovery rule controlled by the firmware feature
`com.samsung/featureconf/broswer_preloading` (Samsung's spelling). It was not
patched or disabled. AirPlay, screen mirroring, Ambient Mode, voice services,
broadcast/HDMI components and shared app runtimes were preserved.

The leftover 31,946-byte SDK installer upload was hash-checked and removed from
the TV's temporary upload directory. The signed package remains privately on the
Mac. This is housekeeping, not a meaningful performance improvement.

Run once from the repository with Minimal Hub open and no system overlay:

```sh
python3 qn90a-trim.py
```

The command guards the model, platform, developer host and exact firmware. It
checks foreground/overlay state before each termination and refuses a different
foreground. If an app remains or relaunches, it reports failure without forcing
a kill. It does not uninstall anything or automatically repeat.

To re-open all three apps and return to Minimal Hub:

```sh
python3 qn90a-trim.py --restore
```

This restore command was run successfully on the TV. It opens Prime Video,
YouTube and Samsung Home in sequence, verifies their foreground/overlay state,
then returns to the hub. Each app can also be opened individually as usual.
Samsung Home's first opening after unloading took **6.79 seconds** in the cold
test; subsequent openings were warm. Apps can reload themselves during normal
use or after reboot, so this is temporary memory recovery.

## Measurements

Values are kernel `MemAvailable` and `SwapFree` readings, not sums of process RSS.
RSS would double-count shared pages. Swap is compressed RAM on this TV; logical
swap capacity is not an equal amount of physical RAM.

| Check | Available RAM, KiB | Free swap, KiB |
| --- | ---: | ---: |
| First streaming-app trial, before | 706520 | 1492 |
| First streaming-app trial, after | 788384 | 129076 |
| Separate Home trial, before | 805796 | 120888 |
| Separate Home trial, after | 888532 | 174160 |
| Final cleanup, all three reopened first | 661504 | 134364 |
| Final cleanup, five seconds after | 904496 | 179848 |
| Follow-up approximately 40 seconds later | 906364 | 180360 |

The final paired sample recovered **237 MiB of available RAM** and **44 MiB of
logical swap capacity**. The follow-up had approximately **885 MiB available**.
The earlier trials began with different app states; do not add their gains to
the final paired sample. Samsung's other background work also changes these
readings over time.

## What was verified

- Normal app-manager termination and absence checks for the three target apps.
- Samsung Home's cold recovery as the current partial app, followed by returning
  to Minimal Hub.
- Prime Video and YouTube reopened as the current fullscreen app through the
  tested restore command. This verifies launch/recovery, not playback or login.
- Minimal Hub remained foreground after cleanup; the three apps stayed absent
  in the follow-up sample.
- All four Home/startup preferences still matched the original values.
- The installer upload and prior root-probe staging directories were absent.

This change adds no launcher UI code. The previously passing 37 launcher tests
were not rerun. The new Python command passed syntax checks and both its trim
and restore paths were exercised on the actual TV. Physical remote latency,
picture/audio quality, input switching and perceived responsiveness require
owner confirmation; lower memory use alone does not establish a latency gain.

the owner subsequently reported that navigation and app switching felt **“About the
same.”** The memory recovery is verified, but this cleanup did not produce a
confirmed responsiveness improvement. Further work should investigate input and
rendering latency rather than assume more process termination will help.

A subsequent signed-app debugger sample compared eight alternating Home arrow
presses per pass: original artwork, a temporary flat-style override, then original
artwork again. Median synchronous event handling was **2.55 / 2.53 / 2.47 ms**.
Two animation-frame callbacks arrived after medians of **16.49 / 12.31 / 15.52 ms**.
These are small synthetic samples inside Chromium, not physical input-to-photon
latency. The temporary styles were removed; no visual/performance change was
deployed from this experiment. The first, longer benchmark exceeded the debugger
response timeout and is not counted as a result.

Eight further synthetic navigation samples on each utility page gave medians of
4.17 ms in Edit apps and 5.18 ms in Settings (maxima 9.40 and 16.94 ms). No app
preferences were changed. The debugger also read the same saved Plex/YouTube
record that had been written before the earlier real restart and signed update.

After profiling, the identical signed 0.3.9 package was reinstalled and started
normally (`debug 0`). Both diagnostic ports were closed. The final check found
all three cleanup targets still absent, Minimal Hub foreground, original routing
preferences intact, and the temporary installer removed. Available RAM was then
868612 KiB (about 848 MiB), with 223452 KiB free swap; these values continue to
vary with Samsung's background work. No additional termination was needed.
Evidence: `20260920T143922.206759Z-qn90a-memory-final`.

Private evidence sessions:

- `20260920T142649.790742Z-qn90a-trim-streaming`
- `20260920T142822.025909Z-qn90a-trim-home-trial`
- `20260920T142842.563428Z-qn90a-home-restore-test`
- `20260920T143004.396277Z-qn90a-memory-restore`
- `20260920T143037.300522Z-qn90a-memory-trim`
- `20260920T143122.940764Z-qn90a-memory-final`
