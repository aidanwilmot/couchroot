# QN90A startup audit — 2026-09-22

Scope: read-only inspection following the owner's report of slow Hub entry after
a full restart or unplug. No service was stopped, disabled, removed or reordered;
no reboot was requested. The inspected firmware is T-NKM2AKUC-2301.1, Hub 0.4.7
and startup relay 0.2.0. Temporary privileged inspection was cleaned up and the
original protected system files were verified unchanged.

## What is measured

The current boot's preserved kernel log, systemd unit timestamps/dependencies,
timer definitions and process counters were collected. `systemd-analyze` is not
installed; manager/unit monotonic timestamps supply the timing evidence instead.
The current boot is the earlier recovery session, not a new reproduction of the
owner's ordinary full restart or AC power-on. Later manual Hub launches mean its
current process cannot establish autonomous startup time.

| Current-boot milestone | Kernel uptime |
| --- | ---: |
| Context manager signals ready | 7.528 s |
| Welcome-mode process starts | 17.352 s |
| App boot manager signals app readiness | 20.375 s |
| Pre-delayed timer activates; configured wait is 10 s | 20.389 s |
| Pre-delayed timer fires | 30.404 s |
| Delayed timer activates; configured wait is 5 s | 30.415 s |
| Delayed timer fires | 35.531 s |
| Web-app service process starts | 35.968 s |
| Web-app service signals `/run/was_ready` | 41.066 s |

`org.tizen.webappservice.service` belongs to `vdtizen-bootseq-delayed.target`.
Its systemd D-Bus readiness timestamp agrees with the kernel readiness event.
The two fixed waits remain even if unrelated services are removed. This is a
concrete scheduling opportunity, but it is not proof that moving this service
earlier would save fifteen seconds: on-demand activation, prerequisites and
resource contention need an instrumented successful Hub boot to establish that.
Do not advance the whole vendor delayed target or forge readiness events.

The systemd manager reports completion at 16.587 s, before these application
milestones. That number is not the time to a usable Hub. Service lifetime,
Type=simple activation and accumulated CPU likewise must not be reported as
visible startup latency.

The [previous two successful full-reboot trials](../research/qn90a-hub-boot/README.md)
show startup relay entry at 18.32–18.38 s, Hub requests at 25.48–25.69 s, and Hub
foreground at 43.67–44.99 s. The relay requires five seconds of stable readiness
plus timer observations, contributing roughly six seconds after the first ready
sample. The additional 18–19 seconds after acceptance remains to be attributed
between framework startup, scheduling and web-app creation. The current boot's
41-second web-app readiness is suggestive, not a same-run causal measurement.

Privileged inspection confirmed that the current boot has no
`/tmp/minimal-hub-boot` directory. This is a real absent record, not merely an
SDK permission failure. Welcome mode did start; the earlier correct persisted
startup rule therefore does not alone establish that the relay was dispatched.
Investigate this missing dispatch separately from the successful boot's latency.

## Service candidates

These are candidates for individually measured, reversible startup trials, not
validated removal targets. Dynamic D-Bus/app dependencies are not exhausted by
the systemd dependency lists.

| Candidate | Current evidence | Assessment |
| --- | --- | --- |
| `adagent-service.service`, `pisa-service.service` | Started at 1.798/20.702 s; no direct `RequiredBy` units. Both honor the absent `/opt/usr/share/systemd/system/pisa-service` condition marker. | First optional service family to evaluate. Preserve installed packages and test the vendor condition guard before considering permanent changes. |
| `canalysis-service.service`, `contents-recognition-service.service`, `contents-ui-detector-service.service` | Started near 20.5 s; descriptions identify content analysis/recognition. No direct `RequiredBy` units. Only canalysis exposes the inspected vendor disable-marker guard. | Second candidate family; inspect callers and dynamic dependencies before disabling. Do not assume all members share one control. |
| Voice and Ambient components | Voice launches around 17–24 s; Ambient agent starts around 7 s and the Ambient app around 16 s. | Consider only if the owner does not use these features. Their removal is a feature tradeoff, not a demonstrated speed improvement. |
| `kpi-logging.service` | Starts at 20.658 s; 0.188 accumulated process CPU-seconds at inspection. | Low priority for startup performance. |

The observed advertising and three content-analysis process CPU totals combined
were below four CPU-seconds across the entire sampled boot, including normal use.
They are not boot-only measurements, but do not support predicting a dramatic
startup improvement from these resident processes alone. I/O, child processes
and contention still need separate measurement.

Avoid `issue_report_agent` as an initial trial: device tracking and abnormal-user-
behavior units declare a requirement on it. Preserve app management, the context
manager, web-app runtime, package mounting, security, networking, Bluetooth/remote,
video/audio, HDMI and casting services. Their names or background presence are
not evidence that Hub can safely run without them.

Several services report `UnitFileState=disabled` yet run because vendor targets,
paths or D-Bus activate them. `systemctl disable` alone is not a demonstrated
startup exclusion on this TV. Its firmware root and system unit definitions are
read-only; S90D's writable boot-cache method is not available here.

## Recommended order

1. Trace one authorized full restart with the current package, separating relay
   dispatch, readiness, Hub request, web-app-service readiness and visible Hub.
   Keep an unplug/power-on trial separate from a software reboot.
2. Fix the missed startup dispatch if it reproduces. Then test starting only the
   necessary web-app service earlier through a verified integration point and
   reducing the relay's conservative settling interval while retaining real
   readiness and foreground checks. Do not promise a timing gain before testing.
3. If desired, test the advertising family first, one change at a time, with an
   exact inverse and before/after boot measurements. Native Samsung Home,
   streaming playback, remote operation and casting acceptance remain required.

No live changes were made. Private evidence is under
`~/.local/share/samsung-tv-research/qn90a/startup-audit/20260922T145300Z/`.

## Follow-up baseline correction

The subsequently authorized startup-disable comparison reproduced automatic Hub
entry on the unchanged 0.4.7 package. Its relay confirmed Hub foreground at
45.87 seconds, while the web-app service's D-Bus readiness timestamp was 62.76
seconds. Full web-app-service readiness is therefore not a demonstrated gate
on Hub foreground. The earlier suggestion to advance that service remains an
unproven hypothesis, not an established fifteen-second opportunity. Compare
actual Hub foreground timing in the [disable tests](samsung-qn90a-startup-disable-tests.md).
