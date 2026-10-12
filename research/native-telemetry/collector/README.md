# Native collector

One C implementation for the verified QN90A and S90D firmwares. It preserves the
existing HTTPS receiver schema, certificate SHA-256 pin, per-device bearer token,
ten-second sampling, three-second deadline, connection reuse and capped backoff.
Periodic status stays in RAM. Missing/oversized counters become JSON null; there
is no offline queue or periodic flash logging.

The worker runs as UID 5001 with `User::Pkg::MiniTelemetry`, preserving access to
the existing private pairing and public preferences without relabeling them.
It shares the managed collector's `flock` lease. `enabled` controls its lifetime;
preferences control sampling. Invalid preferences disable transmission. SIGTERM
stops the loop and cancels an outstanding request.

**This is a tested collector candidate, not the default deployment.** Permanent
privileged bootstrap and the short-lived Hub control adapter remain separate work.
The managed service remains the production/rollback path. See
[hardware findings](../../../docs/research/native-service-research.md).

## Build and test

Keep outputs and firmware libraries outside Git. Extract the three libraries in
[`tv-libraries.json`](tv-libraries.json) through the guarded QN90A operations
transport into `PRIVATE_BUILD/tv-libs`, using the listed local filenames. The
build refuses mismatched hashes. Firmware libraries are link inputs only; they
are not redistributed or copied onto either TV.

From the repository root, with an absolute `PRIVATE_BUILD` directory:

```sh
docker build --platform linux/amd64 -t samsung-native-collector:bullseye research/native-telemetry/collector
docker run --rm --platform linux/amd64 \
  -v "$PWD:/src:ro" -v "$PRIVATE_BUILD:/out" \
  -e OUTPUT_DIR=/out -e TV_LIB_DIR=/out/tv-libs \
  samsung-native-collector:bullseye sh research/native-telemetry/collector/build.sh
docker run --rm --platform linux/amd64 \
  -v "$PWD:/src:ro" -v "$PRIVATE_BUILD:/out:ro" \
  samsung-native-collector:bullseye python3 research/native-telemetry/collector/test_collector.py
python3 -m unittest discover -s tests -p native_trial_test.py
```

Outputs include the ARM executable, Linux host test executable, ELF dependency
report, package checksums and the statically linked json-c license. The archived
toolchain is isolated in Docker. Only json-c is linked statically; curl and
OpenSSL use the TV's verified libraries. Both TVs expose curl with OpenSSL 1.1.1
and asynchronous DNS. The worker rejects unsupported backends.

The host build bypasses only firmware/ARM identity checks and must never be
deployed. Tests exercise real TLS pin acceptance/rejection, authentication headers,
connection reuse, receiver parsing, request deadlines, redirect refusal, backoff,
settings changes, singleton locking, signals, malformed configuration and symlinks.

## Bounded device trial

```sh
python3 -m tvsetup.native_trial --device qn90a --binary "$PRIVATE_BUILD/collector-arm"
python3 -m tvsetup.native_trial --device s90d --binary "$PRIVATE_BUILD/collector-arm"
```

Add `--watchdog` to let the TV-side recovery timers perform restoration while the
host only observes, exercising recovery from a host disconnect without disconnecting.

This is a live handoff: it stages immutable code, rehearses private-file access and
restoration, arms TV-side recovery timers, drains the managed worker, then observes
native ingestion for about 80 seconds. The native worker has a 110-second deadline
and a 120-second systemd cap. Restoration returns the original enable marker and
briefly closes/reopens Hub to restart its normal service chain. Credentials and
preferences are preserved; the NAS and boot configuration are not changed.

Recovery uses separate package-labeled file access and `User`-labeled app launch
units. The shell script also needs the read-only execution view. A timer restores
the marker after 179 seconds; an ordered launch unit restarts Hub after 180 seconds
if the host disconnects. These transient timers do **not** survive power loss;
do not reboot during a trial. The private journal retains the recovery paths.

If a started trial is interrupted, inspect its journal and use:

```sh
python3 -m tvsetup.native_trial --device qn90a --recover RUN_ID
```

A successfully prepared run can use `--resume RUN_ID`. A failed preparation needs
inspection of the exact staged artifacts before cleanup; do not rerun over it.
Trials share the setup device lock and pending-run guard. Successful cleanup is
recorded as `rolled-back`, with native samples and restored receiver evidence.

`collector.service.in` is a future installation template, not an enabled boot unit.
Creating a service still requires privileged setup. Application launch acknowledgement,
a short trial, and unit restart tests do not establish cold boot or standby behavior.
