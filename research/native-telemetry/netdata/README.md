# Native Netdata trial

S90D-only feasibility experiment using upstream **Netdata v2.11.1 ARMv7**.
See [results and limits](../../../docs/lab/research/netdata-native.md).
The original installer is never run on the TV. No normal setup defaults change.

## Prepare

`upstream.json` pins the archive and the extracted, stripped ELF. Keep all outputs
in the private toolkit, outside Git. Use the collector's existing bullseye build
container (binutils 2.35.2); `prepare.py` verifies both hashes and extracts only the
agent executable, with no installer execution or archive path extraction.

```sh
python3 research/native-telemetry/netdata/prepare.py \
  --output /private/netdata-build --strip arm-linux-gnueabi-strip
```

On macOS, run this inside the collector's build container with the checkout mounted
read-only and a private output directory mounted separately. A checksum mismatch
requires reviewing the artifact; there is no force option.

## Run and recover

```sh
python3 -m tvsetup.netdata_trial --binary /private/netdata-build/netdata-arm
python3 -m tvsetup.netdata_trial --recover RUN_ID
```

The runner uses the S90D profile, signing-host/firmware guards, shared device lock
and pending-run journal. It stages a unique root-owned code directory and runs as
UID 5001 with a read-only execution view. Its API binds only to TV localhost:21999.
Logs, SQLite metadata and retained samples go to a private directory on `/tmp`.
Normal Hub telemetry remains active. A failed run retains evidence and blocks
another run until recovery removes its known files and units.

The TV unit expires after 180 seconds. `LimitAS=256M` and `LimitCPU=20` constrain
each process; `Nice=10` reduces scheduling priority. Generic systemd memory/CPU
cgroup settings were **not enforced** by this firmware's controller layout, so
those settings alone are not adequate bounds. The later trial verified actual
process limits. `ProtectSystem` alone also left a writable home bind; the later
trial additionally hides `/opt/usr/home`. Do not infer filesystem isolation merely
from an accepted unit property.

Configuration enables only CPU, uptime, memory, disk and interface collection at
10-second intervals. External plugins, ML, alerts, anonymous analytics, exporting
and ordinary streaming are disabled. `proc-modules.json` is the explicit module
list from the pinned upstream `plugin_proc.c`; new upstream versions need review.

An optional `--parent-config /private/parent.json` enables TLS streaming to a
separate test parent. The private JSON contains `host` (IPv4), `port`, `api_key`
(UUID), and `ca` (public PEM path). Certificate verification stays enabled. The
parent must be ready, accept that temporary key and retain the `s90d-native-trial`
child. Keep this separate from NAS production; stop the temporary parent afterward.
The runner verifies live CPU values at the parent before cleanup.

Memory samples include both agent and spawn helper, recording `smaps` RSS, PSS,
swap and proportional swap. `/proc/status` RSS alone understated residency on this
firmware. Runtime tmpfs metadata and executable storage are additional costs.
The TV lacks `/proc/PID/io`; missing I/O counters are recorded as unavailable,
never as zero flash writes. Physical remote latency, playback and standby require
separate hardware acceptance.
