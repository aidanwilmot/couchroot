# QN90A navigation performance

Hub **0.4.5** was installed and verified on QN90A on 2026-09-21. The owner
confirmed physical-remote navigation is **“Much faster now.”**

## Changes

- Keep all Home background gradients in one static, viewport-sized compositor
  layer. Selection no longer changes the backdrop or invalidates body painting.
- Give the footer a separate small paint surface, including its idle fade.
- Use solid backgrounds on Edit apps and Settings.
- Batch scroll-edge geometry reads before class updates; refresh edge markers
  on actual scrolling instead of scanning the list on every arrow.

Artwork, rounded focus rings, navigation sounds, saved preferences and launch
behavior remain. The implementation does not create a permanent layer per tile.
The shared UI source benefits both targets; this rollout updated QN90A only.

## Measured result

Each paired sample submitted four native arrows one second apart, with Hub
running normally (`debug 0`). Values below are accumulated CPU-seconds in
Chromium's `CompositorTileW` raster workers, **not** remote-to-screen latency.

| Navigation | Original 0.4.3 | Optimized 0.4.5 | Reduction |
| --- | ---: | ---: | ---: |
| Home tiles | 7.820 s | 0.164 s | 97.9% |
| Footer buttons | 3.644 s | 0.664 s | 81.8% |

The samples lasted roughly 4.3–4.6 seconds. The original Home test kept two
raster workers each near 89% of a core, while the JavaScript renderer used only
0.036 CPU-seconds. This identified painting as the dominant bottleneck. An idle
CPU average hid these input-triggered bursts; the collector's earlier sample
was only 0.08% of one core and about 25.8 MiB RSS.

The first backdrop-only optimization already achieved 0.160 s for Home and
0.652 s for the footer. The additional footer layer did not produce a further
measurable gain in this short TV sample; it provides an explicit paint boundary,
verified by the browser regression.

A subsequent 20-arrow rapid-input sequence used 0.488 raster CPU-seconds over
5.24 seconds including a one-second settling period. Four editor arrows used
0.284 raster CPU-seconds over 2.92 seconds. These are bounded observations, not
FPS guarantees or a sustained-load benchmark. The paired Home/footer samples
had no new major page faults; the rapid/editor checks recorded 2 and 8.

## Validation and recovery

All **60 automated tests passed**, including a new browser regression that
checks completed frame painting: arrow navigation reuses the backdrop surface,
and footer arrows do not repaint the app tiles. Local screenshots were reviewed
at 1920×1080 and 960×540. These browser checks complement the native TV CPU
measurements and owner confirmation; they do not emulate Tizen.

The signed UI-only update preserved app data and required no reboot, service
restart, telemetry change or native integration change. Installed content
readback matched the final source. The immediate launch check ran before the
foreground transition completed; follow-up inspection confirmed Hub foreground
without another installation or launch attempt. The journal is complete and a
matching previous signed WGT is retained for rollback.

Private final deployment run: `20260921T153044Z-972594b0`.
Private measurements: `~/.local/share/samsung-tv-research/performance/ui-optimization/`
(`final-summary.json`, `final-extra-summary.json` and raw thread captures).
Original evidence: `performance/20260921T151139Z/`, with full native-arrow
sessions `20260921T151908.346235Z-setup-root-operation` and
`20260921T152007.380499Z-setup-root-operation`.

## Separate background-return cost

Before the optimization, returning from the screensaver produced 2,495 major
page faults and 9.880 CPU-seconds over 15.52 seconds, then settled. This is
consistent with restoring swapped or file-backed memory and is separate from
the repeated focus-painting bottleneck. This update does not claim to eliminate
that restoration cost. The firmware omits the usual swap/scan counters from
`/proc/vmstat`; absent counters must not be reported as zero swapping.

The [earlier memory cleanup](samsung-qn90a-overhead.md) had no owner-confirmed
responsiveness benefit. Its Hub 0.3.9 synthetic event/rAF timings also did not
measure completed display presentation. Future performance changes should use
native input, raster-thread measurements and physical-remote confirmation.

## 2026-09-22 local return-path refinement

The current source now retains unchanged Home tile nodes on visibility return
and subsequent discovery, indexes the catalog by app ID, and delays the return
discovery request by 150 ms. Changed names, artwork, availability, layout or
shortcut order still rebuild the grid. Launch-motion cleanup avoids scanning
every tile when no motion is active. Grid editing also moves the existing tile
node per arrow rather than rebuilding the screen.

Browser regressions verify node identity across an unchanged return/refresh,
no immediate discovery request, correct changed metadata, and preserved footer
focus. The existing backdrop/footer paint-reuse regression still passes. These
are UI work reductions, not measured remote-to-screen latency improvements.

The current read-only QN90A identity request timed out. S90D was playing native
YouTube, with Hub backgrounded; its process reported 56,064 kB RSS and 17,064 kB
swap. That single snapshot does not establish a cause or quantify return delay.
No app was launched, no standby transition forced and no TV package installed.
Native saver/standby return and physical remote acceptance remained outstanding
at that point; the subsequent hardware session is recorded below.

## 2026-09-22 hardware return baseline

After reconnecting the developer transport, native Back returned from the
dashboard screensaver to Hub before and after the UI update. Both controlled
samples followed at least 30 seconds in the saver. Each sample includes about
10.7 seconds of observation and foreground readback, not just the transition.

| Measurement | 0.4.5 baseline | 0.4.6 UI refinements |
| --- | ---: | ---: |
| Hub process CPU | 6.104 s | 5.576 s |
| Raster-worker CPU | 2.428 s | 2.148 s |
| Major page faults | 881 | 4,199 |

The differing memory conditions and single samples do not establish a speed
improvement. Substantial restoration work remains. Neither CPU time nor the
foreground check measures remote-to-pixel latency; physical-remote acceptance
and repeated measurements remain necessary for a performance claim.

A separate native power-key trial entered standby and lost the developer
connection. One recovery wake packet did not restore access. The owner powered
the TV on, after which it had a new boot session and TV viewer foreground, with
no Hub boot-helper status. This was not a successful same-boot wake test.
Read-only setup inspection found Hub, Home routing and startup configuration
correct. Native Home subsequently reached Hub. The interrupted diagnostic was
removed and protected system-file hashes verified unchanged. No startup rules
were reapplied and no further automated standby cycle was attempted.

Private evidence: `~/.local/share/samsung-tv-research/hub-validation/20260922T140842Z/`.
See [the hardware validation record](hub-hardware-validation-20260922.md) for
installed versions, UI checks and remaining acceptance work.
