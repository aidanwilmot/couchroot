# QN90A startup launch diagnostics — 2026-09-22

Follow-up to the [startup exclusion tests](startup-disable-tests.md),
authorized by the owner to investigate the three-attempt pattern before adopting
permanent service exclusions. Exact target: QN85QN90AAFXZA,
T-NKM2AKUC-2301.1, Hub 0.4.7.

## Diagnostic change

Startup relay 0.2.1 adds `launchHistory` to its existing RAM-only status record.
Each of at most three attempts records the API stage, return code, kernel uptime
before/after the call, foreground before/after, and post-call readiness. The
five-second settle requirement, retry spacing, maximum attempts, foreground and
power guards, accepted-request deduplication, and overall deadline are unchanged.
The record survives the helper's exit but not a reboot. No polling daemon or
persistent per-boot log is added.

The package was updated through the shared setup engine, run
`20260922T154837Z-c1eaa5e6`; the verified previous signed 0.2.0 package was enrolled
for forward-version recovery. Only the boot relay package changed. Host tests
passed 15 production timer scenarios (including failures before send and retained
error history) and 37 QN90A routing/regression tests.

## Method

Use the same vendor advertising exclusion marker and exact-hash recovery as the
preceding tests. Normalize the initial foreground to Hub before each reboot,
using a native Home event when needed. Then request one native DeviceD reboot and observe passively;
no application or key assistance is sent after reboot until evidence collection.
SDK/root collection follows the observation window. Measurement is kernel uptime,
not physical AC power-to-pixel timing.

Private evidence is in
`~/.local/share/samsung-tv-research/qn90a/startup-launch-diagnostics/20260922T154816Z/`.
The first unchanged-policy run reached Hub at 41.88 seconds: its launch call
began at 25.71 seconds, returned success at 30.86 seconds, and needed no retry.
The call took 5.15 seconds; native foreground confirmation followed 11.02 seconds
later. The attempted bounded dlog dump returned no content, so it provides no
additional explanation.

## Reproduced failure and correction

The first advertising-excluded run reached Hub at 44.75 s with one successful
request. The repeat reached Hub at 37.54 s with the original three-attempt
pattern, now retaining the individual results:

| Attempt | Start (s) | Return (s) | Stage | Result |
| --- | ---: | ---: | --- | ---: |
| 1 | 26.76 | 32.19 | send | -17825757 |
| 2 | 32.28 | 33.31 | send | -17825757 |
| 3 | 35.34 | 36.08 | send | 0 |

`-17825757` is `LaunchRejected` (`-0x01100000 | 0x23`) in Samsung's
[AppControl binding](https://github.com/Samsung/TizenFX/blob/master/src/Tizen.Applications.Common/Interop/Interop.AppControl.cs).
The [Tizen 6.0 API reference](https://docs.tizen.org/application/native/api/mobile/6.0/group__CAPI__APP__CONTROL__MODULE.html)
describes rejection in the current launch context, distinct from its timeout and
internal-launch-failure codes. The exact lower-level Samsung rejection reason
remains unknown; this error is not evidence that no launch work began.

The preserved kernel log shows the Hub process at uptime 30.952670 s, while the
first call was still running. Its first error returned at 32.19 s and the next
request began just 0.09 s later. The relay measured retry spacing from the start
of a potentially blocking native call. Thus a call lasting over three seconds
could consume the entire intended pause, allowing an immediate follow-up request.

Relay 0.2.2 measures the same three-second minimum from call completion. It keeps
observing foreground/power during that interval, so Hub becoming foreground or
another app taking over prevents a retry. The maximum of three attempts, initial
settle period, and overall deadline are retained. Error results are preserved;
rejection is not reclassified as acceptance. Signed setup run
`20260922T160031Z-72c33e54` enrolled the previous signed 0.2.1 package for recovery.
All 18 production timer scenarios and 37 QN90A regression tests passed.

The measured advertising results of 44.75 and 37.54 s overlap normal-startup
variation; the earlier small sample does not establish a dependable speedup.

## Fix validation

Two advertising-excluded boots on 0.2.2 reached Hub at 43.00 and 45.58 s, each
accepting its first request. They establish that normal launch still works;
neither exercised the revised rejection delay. The host scenario reproducing a
5.4-second failed call verifies no next send before three seconds after return,
and separate scenarios verify Hub/user activity wins during that interval. Do
not claim the intermittent Samsung rejection itself has been eliminated.

One preflight stopped before submitting a reboot because a Home event did not
leave the screensaver. Same boot ID, no scheduled reboot and completed diagnostic
cleanup were confirmed before continuing under a new trial label. Normalization
now leaves the saver with a direction key and only sends Home when Hub is absent.
This preflight is not counted as a reboot observation.

## Final result

| Relay | Configuration | Hub foreground (s) | Attempts |
| --- | --- | ---: | ---: |
| 0.2.1 | Normal services | 41.88 | 1 |
| 0.2.1 | Advertising excluded | 44.75 | 1 |
| 0.2.1 | Advertising excluded, repeat | 37.54 | 3 |
| 0.2.2 | Advertising excluded | 43.00 | 1 |
| 0.2.2 | Advertising excluded, repeat | 45.58 | 1 |
| 0.2.2 | Normal services restored | 45.85 | 1 |

All six full reboots reached Hub autonomously. All three on the fixed relay
accepted their first request, so the changed retry branch was verified in the
host harness rather than exercised in these final device boots. The final
normal-service launch call ran from 27.09 to 32.66 s, followed by foreground
confirmation at 45.85 s. This fixes request pacing and preserves diagnostics;
it does not establish a reduction in normal boot time or eliminate Samsung's
underlying intermittent rejection.

Final native Plex launch, Home return, Samsung Home overlay and Hub return all
passed. The TV was left in Hub with no partial overlay. Both test markers were
absent and adagent, PISA and canalysis were active. All six failed-unit captures
contained the same eight pre-existing failures recorded in the preceding audit.

The final snapshot matched pre-install recorded hashes and package records for
every component except the intended boot relay update. Relay 0.2.2 bytes matched
the signed apply record. Persistent settings, telemetry preferences and Home/app
routing were unchanged. Temporary root staging was absent. A setup run with no
device changes (`20260922T161405Z-dd3ad901`) restored the original saved setup
component choices while retaining the updated relay ownership record. The private
diagnostic journal is complete; no service exclusion remains.

The [sanitized inventory](../../inventory/qn90a-startup-launch-diagnostics-20260922.json)
retains every attempt and timing, validation scope, failed-unit list and final
preservation check. AC unplug startup, media playback and actual casting were
not tested.
