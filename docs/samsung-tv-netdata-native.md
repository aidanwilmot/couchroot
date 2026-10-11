# Native Netdata feasibility

Verified on **S90D / T-PTMDAKUC-0090-2130.0**, 2026-09-21.

**Upstream Netdata runs natively on the S90D and streams real metrics over TLS.**
The [official ARM static distribution](https://learn.netdata.cloud/docs/netdata-agent/installation/linux/static-binary-linux-packages)
from [release v2.11.1](https://github.com/netdata/netdata/releases/tag/v2.11.1)
worked without a Tizen source port or resident .NET host. This establishes feasibility;
production telemetry remains the existing managed collector on both TVs.

## What passed

- Extracted and checksum-verified upstream **v2.11.1 ARMv7**; never ran its installer
  on the TV. The self-contained ELF needs no Tizen shared-library substitutions.
- Ran under the system manager as UID 5001, without capabilities or a CLR mapping,
  using the same read-only VDFS execution view as our C collector.
- Collected CPU, memory, disk, network and uptime every **10 seconds**. ML, alerts,
  external plugins and anonymous analytics were disabled.
- Streamed **121 charts** to an isolated parent on the management computer, using
  a temporary key and TLS with certificate verification enabled. CPU samples at
  the parent advanced across the observation window.
- Kept production ingestion fresh. Removed the TV trial and stopped the temporary
  parent afterward; NAS configuration, credentials and history were unchanged.

The parent was an isolated Docker instance of Netdata v2.11.1, not the production
NAS. The existing NAS receiver and Hub dashboard use our custom telemetry format;
production adoption would also need an explicit identity/dashboard migration.

## Measurements

Seven samples span **97.34 seconds** while streaming. These are short-run
observations, not peak bounds or proof of remote/playback responsiveness.

| Measurement | S90D streaming trial |
| --- | --- |
| CPU, agent plus spawn helper | **0.69% of one core** |
| Resident proportional memory, PSS | **1.43–6.62 MiB** |
| Proportional swapped memory | **1.33–5.28 MiB** |
| PSS plus proportional swap, paired per sample | **6.61–8.07 MiB** |
| Agent/helper threads | **23 + 1** |
| Stripped executable | **21.78 MiB** |

CPU uses the TV's measured `CLK_TCK=250`, not an assumed 100 Hz. The preliminary
local-only estimate was revised after verifying this clock rate. The earlier C
collector trial measured about 0.085% of one core and 3.00–3.04 MiB RSS on S90D;
its RSS-only memory measure is not directly comparable with PSS plus swap here.

Both process memory maps were measured. `/proc/status` RSS alone understated
residency and varied sharply as memory was paged out. Runtime files included about
1.3 MiB of SQLite metadata/logs on tmpfs; file sizes overlap some mapped memory and
must not simply be added to PSS. The binary's full file size is also distinct from
resident memory. No long-term flash-write claim is made: this kernel omits
`/proc/PID/io`. Observed writable database/log files were under the private `/tmp`
trial directory.

## Firmware details that mattered

Netdata needs `NETDATA_RUN_DIR` set to its private writable RAM directory. Its
normal Linux runtime paths were unavailable to the confined owner process. It
also requires at least eight libuv worker threads in this version.

Accepted systemd properties are not proof of enforcement. The memory controller
was absent, accounting returned unavailable, and the process remained in the
firmware's default CPU cgroup. The successful streaming trial therefore used
verified process limits of **256 MiB address space** and **20 CPU seconds**, plus
a **180-second unit deadline** and `Nice=10`. Address space is not an RSS limit;
the CPU limit is accumulated time, not a guaranteed scheduling percentage.

`ProtectSystem=strict` left a vendor-created writable home bind in the first trial.
The later trial hid `/opt/usr/home`; mount evidence confirmed the inaccessible
view, read-only code and writable tmpfs runtime. No vendor file, policy, boot
configuration or production package was replaced.

## Decision and remaining work

A maintained Tizen fork is unnecessary for this tested build. Keep the small C
collector as the lean option; retain Netdata as a viable richer-metrics candidate.
Its measured footprint is much smaller than generic default-agent estimates, but
its CPU cost and background threads are higher than our purpose-built sampler.

The immediate blocker is **automatic startup**, shared by both native options.
The [startup investigation](samsung-tv-native-service-research.md#startup-capability-boundary-follow-up)
confirmed that normal apps and the owner manager cannot prepare the required
mount view. The working system-manager trials still use an administrative launch.
The [decompilation follow-up](samsung-tv-native-autostart.md) records the rejected
boot paths and the standalone versus management-host bootstrap choices.
QN90A native Netdata, cold reboot, standby/wake and physical remote/playback
acceptance remain unverified. No permanent cutover was made.

Source, pinned preparation and recovery commands are in
[`research/native-telemetry/netdata`](../research/native-telemetry/netdata/README.md).
Private journals retain:

- `20260921T171925Z-3b90a9cf`: runtime-directory startup failure, cleaned.
- `20260921T172106Z-e547f30b`: local collection; observation adapted to missing
  kernel I/O counters; cleaned.
- `20260921T172726Z-540fcd64`: complete TLS streaming benchmark and cleanup.

All three are terminal `rolled-back` journals. The project Python suite passes
153 tests, including configuration, proc parsing and cleanup path validation.
