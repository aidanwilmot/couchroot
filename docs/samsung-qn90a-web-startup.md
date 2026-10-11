# QN90A web startup profiling — 2026-09-22

The startup changes remove optional platform work from Hub's initial rendering
path, but these measurements **do not establish a consistent total boot-time
reduction**. A three-second relay settle offered no dependable gain over five
seconds, so the final relay 0.2.4 restores five seconds. All Samsung service
exclusion markers remain absent.

## Changes retained

- Initialize saved shortcuts and remote navigation before initial discovery.
  Schedule the first catalog request once the document has focus. An explicit
  editor request takes precedence and cancels that pending startup request.
- Read monitoring preferences after focus plus 1.5 seconds. A hidden or unfocused
  app waits; existing bounded failure retries and visible-return recovery remain.
- Avoid inspecting the native sound fallback when Web Audio is available.
  This does not change the saved sound setting or the local synthesized tones.
- Extend optional research timing hooks and capture bounded Navigation/Paint
  Timing entries. The normal package contains no recorder or diagnostic writes.

Hub 0.4.11 is the normal QN90A package from this pass. The S90D was not updated.

## Method and limits

Exact target: QN85QN90AAFXZA / T-NKM2AKUC-2301.1. The native relay retained its
power/foreground guards, three-attempt limit, once-per-boot claim, 120-second
admission/deadline and corrected three-second pause **after a rejected call
returns**. Only the initial five-second settle was shortened during the 0.2.3
experiment.

Normalize Hub foreground before each native DeviceD full reboot. After reboot,
observe passively without keys or application launches, then collect native
status and the app's storage through the shared guarded transport. A diagnostic
build records one minute of page events, writes only two separate diagnostic
storage keys, and deletes them after three minutes. The final normal build
removes the temporary script and packaging-list additions.

Relative page timings use `performance.now()`. Boot alignment uses late native
whole-second wall-clock/uptime pairs; the rounding interval is approximately
±0.5 seconds and assumes no clock step between trace-end and collection
(16–34 seconds in these runs). Wall/performance offsets within each trace varied
by less than 1.5 ms. Early navigation and frame callbacks are not evidence of
physical panel visibility. The rendered/focused column below is the first
recorded visible, focused event at or after the second post-render frame callback.
It is a software readiness proxy, not a physical remote-response measurement.
These were native full restarts, not AC-unplug or standby/wake tests. Diagnostic
instrumentation itself also adds some work.

## Results

| UI / relay settle | Native foreground (s) | Rendered + focused, estimated (s) | Launch attempts | Initial discovery |
| --- | ---: | ---: | ---: | --- |
| Original scheduling, 5 s | 44.20 | 44.4 | 1 | 8 s deadline |
| Original scheduling, 5 s | 43.27 | 42.6 | 1 | 8 s deadline |
| Fixed monitoring delay, 5 s | 45.79 | 45.6 | 1 | 8 s deadline |
| Focus scheduling, 5 s | 38.62 | 42.3 | 2 | Completed |
| Focus scheduling, 5 s | 46.53 | 47.4 | 1 | Completed |
| Focus scheduling, 3 s | 47.06 | 46.4 | 1 | Completed |
| Focus scheduling, 3 s | 39.61 | 41.6 | 2 | 8 s deadline |

The fixed-delay experiment (Hub 0.4.9) still let monitoring interrupt the focus
handoff. Its preference-load call synchronously occupied 1.192 seconds despite
accepting callbacks. The final approach waits for focus, with successful reads
and dispatch recorded in all four focus-scheduled diagnostic boots. Initial
catalog discovery completed in three of those four boots; the remaining timeout
still uses the existing editor recovery path. This is not proof that Samsung's
early discovery problem is eliminated.

Feedback initialization includes the first localStorage read. Its measured
0.36–2.29-second interval in the revised builds cannot be attributed solely to
native sound capability detection. Avoiding the unused native fallback is a
reduction in unnecessary work; these traces do not isolate its speed benefit.

The first page-level timing hook ran at roughly 35.7–38.7 seconds of kernel
uptime. Much of the delay therefore occurs before the instrumented page begins.
Native foreground alone can also be misleading: the 38.62-second confirmation
preceded the completed Hub render at approximately 42.3 seconds.

Both relay policies had one rejected-first-request case in their two
focus-scheduled runs. In those cases the next request started 3.53 seconds after
the failed call returned, exercising the previous retry correction on real
hardware. The shorter initial settle did not establish a total-time or reliability
improvement, so it was reverted through a forward signed update. Further startup
work should investigate the platform/app-runtime interval with equally careful
measurements, rather than assume another optional service is responsible.

## Evidence and verification

Sanitized timings: [inventory](../inventory/qn90a-web-startup-20260922.json).
Private source snapshots, signed recovery artifacts, journals, native captures,
and storage archives are under
`~/.local/share/samsung-tv-research/qn90a/web-startup-profiling/20260922T164316Z/`.

Signed runs:

- Diagnostic UI 0.4.8: `20260922T164546Z-68dc8c2f`.
- Fixed-delay UI 0.4.9: `20260922T165336Z-f48e124f`.
- Focus-scheduled UI 0.4.10: `20260922T170002Z-f489c735`.
- Three-second relay 0.2.3: `20260922T170748Z-2565f51d`.
- Five-second relay restored as 0.2.4: `20260922T171422Z-79790869`.
- Normal UI 0.4.11, recorder removed: `20260922T171838Z-b5b7166b`.

One preflight stopped before submitting a reboot because Hub was not foreground.
Same boot ID, absent scheduler output and completed transport cleanup were
confirmed before normalizing Hub and starting a new trial. The 0.4.9 update's
foreground check timed out after installation; subsequent readback found Hub
foreground with one process and an empty partial overlay. No launch was repeated.

Final browser checks: 77 passed. Setup Python checks: 169 passed. Production
relay timer harness: 18 scenarios passed at both settle values and again after
restoring five seconds. The accepted-state test fixture now pins current source
revisions while retaining the test that deliberately introduces source drift;
production reviewed hashes were not changed to conceal a mismatch.

The local storage compacted into an SST table during cleanup. Logical current
values were reconstructed from an offline copy using the highest LevelDB sequence
per key and deletion records, with
[CCL's LevelDB reader](https://github.com/cclgroupltd/ccl_chromium_reader).
This confirmed both diagnostic keys were deleted and the saved shortcuts and
selection matched the original snapshot. Raw evidence remains private.

The eighth, final reboot used normal Hub 0.4.11 and five-second relay 0.2.4.
It reached native Hub foreground at 37.08 s after two requests. No web recorder
was present, so this is not a measured rendered/focused improvement. Native-key
checks opened Plex, returned Home, opened Samsung Home as an overlay and returned
to Hub with an empty partial overlay. Monitoring had sent seven samples with
zero failures in the final snapshot. Streaming playback and physical-panel timing
were not inferred from these checks.

Final installed bytes matched current normal Hub source and the signed relay
update. All unrelated package records/hashes, persistent settings, monitoring
preferences, Home/AirPlay routes, saved favorites and selection matched the
initial snapshot. The capture asset, diagnostic keys, exclusion markers and
root staging were absent. Adagent, PISA and canalysis were active. One diagnostic
boot (`focus-one`) additionally reported a failed notification service; it did
not recur in the subsequent boots. The final failed-unit set matched the eight
pre-existing failures, so this does not claim a generally failure-free Samsung
system.

Run `20260922T172302Z-696a3ea5` restored the original saved setup choices with
zero device actions. All shared journals and the private profiling journal are
complete. No service exclusion, alternate monitoring stack, or shorter settle
was retained.
