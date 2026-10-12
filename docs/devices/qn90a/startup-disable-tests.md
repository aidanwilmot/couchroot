# QN90A startup-disable comparisons — 2026-09-22

The owner authorized startup-disable tests after the read-only audit. Tests use
one service family at a time and the existing vendor condition guards, retaining
installed packages. The TV is QN85QN90AAFXZA on T-NKM2AKUC-2301.1. The baseline
package is Hub 0.4.7 with startup relay 0.2.0.
Each trial requests one native DeviceD full reboot and observes without launching
Hub or pressing a key after boot. This is not an unplug/power-on measurement.

Private pre-change configuration, unit definitions/hashes, exact absent-marker
state, a target-bound journal and all raw evidence are under
`~/.local/share/samsung-tv-research/qn90a/startup-disable-tests/20260922T150320Z/`.

## Method and boundaries

- Advertising uses `/opt/usr/share/systemd/system/pisa-service`, the negative
  `ConditionPathExists` shared by `adagent-service` and `pisa-service`.
- The separate canalysis trial uses
  `/opt/usr/share/systemd/system/canalysis-daemon`. This covers that daemon only,
  not all content-recognition or media-analysis components.
- Each marker is created exclusively after confirming absence and the original
  unit hashes. Its unique trial content is recorded before mutation. Rollback
  checks the exact content hash and removes only that owned file.
- Reboots are recorded before submission and never blindly repeated. The shared
  device/root locks, firmware/identity checks and guarded root transport are used.
- Passive HTTP checks run equally across trials. SDK/root inspection begins
  after the observation period. Relay timestamps are primary; the first HTTP
  response can lag actual foreground because the API is unavailable early in boot.
- Service exclusion must be proven after reboot by condition result, process
  absence and native state. A created marker alone is not a successful trial.
- Native app-launch/Home checks are separate from boot measurements. They do not
  prove streaming playback, physical remote behavior or a real casting session.

## Baseline

The unchanged full restart reached Hub automatically. Relay entry was 20.89 s,
readiness began at 22.12 s, Hub was requested at 28.13 s, and foreground was
confirmed at 45.87 s. The first successful HTTP visibility observation was at
approximately 50.93 s. One Hub launch request was accepted.

The web-app service's D-Bus readiness timestamp was 62.76 s, later than Hub
foreground. It must not be treated as a mandatory Hub startup barrier. See the
correction in the [audit](startup-audit.md).

## Advertising trial

The vendor marker successfully prevented both `adagent-service` and
`pisa-service` from starting: each had `ConditionResult=no`, no main PID and no
start timestamp. Hub's relay confirmed foreground at 38.47 s. Relay entry was
18.61 s and the final accepted launch request was at 35.43 s after two unsuccessful
attempts. The baseline accepted its first request. A single faster run does not
establish a repeatable benefit.

Native Plex launch, Home return, Samsung Home overlay and final Hub return
passed. Networking, the context manager and the AirPlay service remained active.
These checks do not establish playback or actual casting acceptance. The owned
marker was hash-verified and removed before the control restart.

The intervening control restored both services and reached Hub at 41.73 s on
its first launch attempt. Repeating advertising exclusion reached Hub at 39.17 s,
again with both services skipped and three launch attempts. Both disabled runs
were faster than the first two controls, but the extra attempts consume the
startup relay's entire retry budget. The earlier error codes and failure stages
are not retained in the final status record, so the cause and whether an earlier
request had already started work are unresolved. Do not treat these two
successful trials as proof of long-term startup reliability.

## Canalysis trial

With advertising restored, the canalysis marker prevented only that daemon from
starting (`ConditionResult=no`, no PID/start timestamp). The advertising and
separate content-recognition services remained active. Hub foreground was
confirmed at 36.99 s, after three launch attempts; the accepted request was at
34.17 s. Native Plex launch, Home return, Samsung Home overlay and final Hub return
passed with this marker present.

The repeat reached Hub at 37.39 s, again on the third launch attempt, with the
final accepted request at 34.60 s. Canalysis remained excluded while advertising
and the separate content-recognition service were active.

The initial baseline reboot began while the Hub screensaver was foreground;
later control/treatment requests began with Hub visible. The restored controls
are therefore particularly important when judging a few seconds of difference.

## Service health observations

The advertising repeat and canalysis repeat had the same eight failed units,
all already present in the pre-test audit: the tracing mount, secondary AirPlay
service, AOV service, Knox browser, motion sensor, default/delayed target completion
services and VDCA update. The main AirPlay service was active.

The first canalysis run additionally showed failed notification-serviceapp and
voice-app units. Neither appeared in its repeat. Their cause is unresolved; the
successful Plex/Home checks do not establish voice or notification health. This
is another reason to keep the timing findings separate from approval for a
permanent exclusion.

## Completed restart comparison

All seven reboots changed boot ID and reached Hub autonomously. Times below are
TV kernel uptime at the relay's native foreground confirmation, not physical
power-button-to-pixel measurements.

| Trial | Startup exclusion | Hub foreground (s) | Launch attempts |
| --- | --- | ---: | ---: |
| Baseline | None | 45.87 | 1 |
| Advertising | Adagent and PISA | 38.47 | 3 |
| Intervening control | None | 41.73 | 1 |
| Advertising repeat | Adagent and PISA | 39.17 | 3 |
| Canalysis | Canalysis daemon only | 36.99 | 3 |
| Canalysis repeat | Canalysis daemon only | 37.39 | 3 |
| Final restored control | None | 43.19 | 1 |

Compared with the two controls begun with Hub visible (41.73 and 43.19 s), the
advertising results were 2.56–4.72 s faster and canalysis results 4.34–6.20 s
faster. This small, sequential sample supports further investigation, not a
precise long-term speedup estimate. The two exclusions were never combined;
their apparent gains must not be added together.

Every exclusion run needed all three launch attempts, whereas every control
accepted the first. Before permanent adoption, record each startup attempt's
time, readiness signals and native result/stage so the early nonzero results can
be explained. A nonzero result does not prove no work began: the advertising boot
log shows Hub starting before the final accepted request. Retrying more rapidly
or simply shortening the readiness delay is not justified by this evidence.

The final restored control had the same eight previously observed failed units
as both repeat trials; the additional voice and notification failures did not
recur. Native Plex launch, Home return, Samsung Home overlay and final Hub return
all passed after restoration.

## Final state and recommendation

Both owned marker files were removed with exact-hash guards. Privileged readback
after the final restart confirmed their absence and all three tested services
active with successful startup conditions. The final verification matched the
pre-test snapshot for recorded installed-file hashes, package records,
persistent settings, telemetry preferences and Home/app routing. Temporary root
staging was absent and the private trial journal is complete. No permanent
startup exclusion remains; the TV was left in Hub with no partial overlay.

Keep the restored policy while investigating the launch retry behavior. Canalysis
is the stronger timing candidate in this sample, but its transient service
failures and the three-attempt pattern need explanation before making it a
normal startup setting. A later combined trial would need separate measurements
and recovery checks. Actual AC cold-start time, playback and casting remain
outside these results.

The [sanitized inventory](../../../inventory/qn90a-startup-disable-tests-20260922.json)
contains each trial's relay timing, startup conditions, failed-unit observations
and final restoration checks. Raw device identities and logs remain private.

## Follow-up: launch rejection captured

The [instrumented follow-up](startup-launch-diagnostics.md) captured
Samsung `LaunchRejected` while Hub's process had already started, and identified
an immediate-retry bug caused by timing the pause from call entry. Relay 0.2.2
times the pause from call completion. Further advertising-excluded measurements
overlapped the normal-startup range, so this original small sample does not
establish a dependable advertising-exclusion speedup.
