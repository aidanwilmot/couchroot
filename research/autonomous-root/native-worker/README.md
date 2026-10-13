# Native worker experiment

This C prototype is a measurement sidecar, **not a production replacement**. It
is not referenced by the package builder, service selection or boot configuration.
The installed .NET worker remains active throughout a comparison. No SDK changes,
service replacement, root reacquisition or TV reboot is needed.

The prototype uses the existing HMAC protocol with strict sequence ordering,
bounded binary chunks and structured failure responses. It implements status,
root commands, bounded output and process-group timeouts, app commands through a
verified existing launcher, and file begin/write/status/read/commit/close with
per-chunk/full-file hashes and conditional replacement. File access is deliberately
restricted to direct children of a private, root-owned experiment directory.
It loads the TV's libcrypto and json-c APIs, rather than implementing cryptography
or a complete JSON parser itself. This is still experimental C with a substantially
smaller test history than the managed worker.

Missing parity includes background jobs and durable job recovery, managed helper
view creation/release, autonomous root acquisition, independent launcher staging,
production packaging/recovery integration and the broader production file access
policy. Legacy READFILE/WRITEFILE and JSON file.write are also omitted. Unsupported
operations fail explicitly; there is no automatic fallback or replay. The app
launcher and any executable helper views are borrowed from the deployed worker.
Thus startup numbers are not a comparison of complete independent service startup.

`bench.c` runs on the TV as an authenticated root job. It alternates freshly
executed copies of the installed .NET DLL and the C worker on independent loopback
connections, with two warmup pairs. It measures fork-to-authenticated-status
readiness, worker CPU from `/proc/PID/stat`, memory from `smaps`, and peak RSS from
`wait4`. Transfer timings exclude begin/open but include chunk I/O and upload
commit. Every transfer is verified byte-for-byte and by SHA-256. It also exercises
root failures/timeouts, app identity/environment/quoting, ranges/EOF, offset rejection
and conditional replacement. Neither HTTP nor the deployed service's request
queue is in this benchmark path. The existing fallback and controller remain alive,
so PSS depends on their shared mappings. Idle CPU uses one-second windows and the
kernel clock-tick resolution. Warm-cache worker startup is not boot readiness.

Build outside the source checkout with the project's cached ARMv7 soft-float
Bullseye toolchain:

```sh
sh research/autonomous-root/native-worker/build.sh /private/native-worker-build
```

On Linux, compile `worker.c` with `-DNATIVE_WORKER_TEST` only for the host tests,
which substitute the unavailable host Smack label. Use address/undefined-behavior
sanitizers and set `NATIVE_WORKER` to that executable when running
`tests/native_worker_test.py`. The normal ARM build never enables this test mode.
Tests cover authentication, replay, corrupted/truncated transfers, bounds, path
and symlink rejection, conditional replacement, bounded output and timeouts.

Device execution must use the enrolled .NET client's existing verified upload,
helper and job APIs with firmware guards, per-device locks, durable private
intent/results, unique staging names and a bounded run. Prepare the benchmark and
worker as private read-only helpers. Use a token/status directory below the SDK staging root so the existing managed
worker can run unchanged. Set `COUCHROOT_BENCH_FILES` to a separate canonical,
private directory below `/opt/couchroot-agent/files` for both workers’ transfers.
The SDK staging path may have symlinked ancestors on the TV; it is not suitable
for the native prototype’s strict canonical file scope. Pass the actual
installed DLL and verified launcher for that device, never another model's paths.
Inspect results before releasing helper views and deleting only owned experiment
files. Preserve credentials, raw measurements and signed artifacts outside Git.
