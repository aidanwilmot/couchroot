# Persistent worker capabilities

These changes require rebuilding the service and worker together. Existing installed
0.1.x workers do not expose the new operations. Source validation is separate from
TV installation and firmware-specific acceptance; no deployment is implicit.

All examples use the existing enrolled, certificate-pinned client:

```sh
python3 research/autonomous-root/client.py --config /private/client.json status
```

## Results and readiness

`exec` returns `exit_code`, `timed_out`, `stdout`, and `stderr`, including on a
nonzero exit. A received timeout result is a known result. HTTP failures include
`outcome`: `rejected` means admission failed, `failed` means the worker returned an
operation failure, and `unknown` means a submitted operation's result could not be
confirmed. An operation failure does not imply rollback of its intermediate work.
The client never automatically replays commands or writes. Consult the request
journal and operation status after a lost response.

`AgentTransport.execute_result()` returns the complete result. Existing setup
callers retain checked execution; `_execute(..., check=False)` is available when
only stdout is needed and a nonzero exit is expected.

`/v1/status` now includes `boot_id`, `uptime_seconds`, `worker_ready`, `worker_id`,
`last_root_acquired_at`, and capability names. Readiness requires root authentication
and a completed worker operation. The HTTPS listener may be available earlier.
Acquisition timestamps describe this service lifetime. A disconnected worker's
last identity/boot observation is not readiness.

After recording the current boot ID and separately requesting an authorized reboot:

```sh
python3 research/autonomous-root/client.py --config /private/client.json \
  wait-ready --previous-boot-id OLD_BOOT_ID --wait-seconds 240
```

This requires a different boot ID, a root identity, and worker readiness. It never
requests a reboot itself.

## File transfer

```sh
python3 research/autonomous-root/client.py --config /private/client.json \
  download --source /usr/lib/example.so --target ./example.so
python3 research/autonomous-root/client.py --config /private/client.json \
  upload --source ./helper --target /opt/couchroot-agent/files/helper
python3 research/autonomous-root/client.py --config /private/client.json \
  upload --source ./helper-new --target /opt/couchroot-agent/files/helper \
  --expected-sha256 CURRENT_TARGET_SHA256
```

Transfers use 1 MiB binary HTTPS chunks, authenticated bounded loopback frames,
per-chunk SHA-256 and a complete-file digest. The worker holds at most eight
transfers, each limited to 2 GiB. Downloads support arbitrary byte offsets and
lengths up to 1 MiB. The client verifies the complete download before publishing
it and refuses to overwrite a local destination. In-place source changes fail
final verification; replacing the pathname does not change an already-open file.

Uploads are permitted in the worker's staging/runtime directories, the SDK staging
root `/home/owner/share/tmp/sdk_tools/`, and `/opt/couchroot-agent/files/`.
Canonical paths are required; symlink components are refused. Downloads permit
seekable disk files outside those write roots, but refuse `/proc`, `/sys`, `/dev`
and symlinks. Parent directories must exist, except the fixed managed files root.

Uploads stage beside the destination with mode 0600. Publication is create-only
by default (`expected_sha256: "absent"`), or replaces an existing destination only
when its current digest matches the supplied digest. Replacement uses rename;
create-only publication uses an exclusive hard link. Agent operations serialize
these checks. **Independent writers must be quiesced**: this is not a filesystem-wide
compare-and-swap guarantee. Replacement publishes mode 0600; metadata preservation
and executable installation are separate operations.

An interrupted upload prints its transfer ID. Explicitly resume the same source,
target and precondition using `upload --transfer-id ID ...`; the client first
checks the server offset and metadata. An uncertain chunk is never blindly resent.
Transfers belong to one worker lifetime. Reacquisition invalidates their IDs.
Abandoned sessions can be closed through `file.close`; a clean worker shutdown
removes incomplete staging files. A crash can leave staging files for inspection.
Partial downloads remain beside the requested local target and are never published.

The API uses `POST /v1/op` with `{ "id": "unique-request-id", "operation": {...} }`
for controls. `file.open`, `file.begin`, `file.status`, `file.commit` and `file.close`
return JSON. `POST /v1/files/read` accepts that envelope with `file.read`,
`transfer_id`, `offset`, and `length`, returning bytes with `X-SHA256` and `X-Offset`.
`POST /v1/files/write` accepts bytes and the JSON envelope in `X-Operation`, with
`file.write`, `transfer_id`, `offset`, and the chunk `sha256`. Each write response
returns the next offset. Mutations retain request-ID replay protection.

## Background jobs

```sh
python3 research/autonomous-root/client.py --config /private/client.json \
  job-start --job-id stress-example-0001 --command-file ./stress.sh \
  --timeout-ms 300000 --profile app
python3 research/autonomous-root/client.py --config /private/client.json \
  job-status --job-id stress-example-0001
python3 research/autonomous-root/client.py --config /private/client.json \
  job-tail --job-id stress-example-0001 --stdout-cursor 0 --stderr-cursor 0
python3 research/autonomous-root/client.py --config /private/client.json \
  job-cancel --job-id stress-example-0001
python3 research/autonomous-root/client.py --config /private/client.json \
  job-forget --job-id stress-example-0001
```

Job start returns promptly; it does not occupy the command request until completion.
Timeouts range from 100 ms to 24 hours. At most 16 jobs are retained in the worker,
with at most 64 durable records. `job-forget` removes a finished job and its record;
keep IDs unique even after forgetting. Intent is persisted before spawning.
Duplicate retained job IDs are refused. Root and app profiles are explicit.

Each stdout/stderr stream retains its latest 1 MiB in memory. Tail responses contain
base64 bytes, `next_cursor`, `end_cursor`, and `truncated`; each read returns up to
64 KiB per stream. Advance each cursor independently. Consumers should decode bytes
incrementally because a UTF-8 character can cross a chunk boundary.

Cancellation sends SIGKILL to the job's process group. Jobs should remain in that
group; deliberately daemonized descendants are outside this supervision contract.
A clean worker shutdown cancels jobs. Metadata survives worker/service restart and
reboot, but in-memory output does not. Old-boot running records become `interrupted`.
Same-boot records whose supervisor disappeared become `unknown`, not completed or
restarted. Cancellation of a retained process checks both boot and process start
identity before signaling. No job is automatically rerun after reconnect or reboot.

## App-user execution and unsigned helpers

```sh
python3 research/autonomous-root/client.py --config /private/client.json \
  app-exec --command-file ./app-check.sh --timeout-ms 20000
python3 research/autonomous-root/client.py --config /private/client.json \
  helper-prepare --source /opt/couchroot-agent/files/helper --sha256 HELPER_SHA256
# Put the returned helper path in the app-exec or job-start command file.
python3 research/autonomous-root/client.py --config /private/client.json \
  helper-release --helper-id RETURNED_HELPER_ID
```

The app profile drops supplementary groups, uses UID/EUID 5001 and GID 100,
requires the `User` Smack label, sets HOME/USER/LOGNAME, PATH, the owner runtime
directory, Wayland display and D-Bus addresses, then runs in `/home/owner`.
A failed identity/label transition fails the command; it does not fall back to root.

Helper preparation copies a digest-verified managed upload into a dedicated,
root-owned `/opt/couchroot-agent/helpers/ID/helper`, applies mode 0555 and `User`
labels, and creates a private read-only bind view. It refuses the initial mount
namespace and never changes a Samsung resource or disables signature enforcement.
This encapsulates the previously investigated execution-view technique; **the new
implementation requires verification on each TV/firmware**. The two existing
profiles passed the hardware checks below; desktop tests alone cannot certify
app-user Smack or D-Bus behavior on other firmware.

There are at most eight active helper views and 64 retained helper directories.
Release explicitly after jobs finish. Clean shutdown attempts cleanup; crashes or
busy mounts can leave directories requiring inspection. Only worker-owned helper
IDs can be released automatically; unknown directories are not recursively deleted.

## Local validation

```sh
python3 -m unittest discover -s tests -p '*_test.py'
node --test tests/autonomous-root/protocol.test.cjs
npm test
dotnet build research/autonomous-root/payload/SamsungTvRootAgent.csproj
dotnet run --project tests/root-agent-harness/Harness.csproj
```

The harness exercises the production file operations and log ring on macOS/Linux.
When run as root in a disposable Linux container, it also tests real job execution,
nonzero exits, duplicate-start refusal, group cancellation, timeouts and reboot
records. It never contacts a TV. For that check, mount only the built harness output
into the SDK container; do not mount host `/opt` or device credentials.

Validation recorded on 2026-10-13: 217 Python tests, 104 Node tests with sequential
file execution, 20 telemetry tests, three protocol scenarios, and the Linux
root job harness passed. The first parallel Node run failed an unchanged native-Hub
process-group assertion; its isolated rerun and the complete sequential suite passed.
Both worker target frameworks compile. All 42 native assemblies and the unsigned
Hub package match across source paths. Privacy and whitespace checks passed.
Hardware acceptance followed separately, as recorded below.

## Hardware acceptance — 2026-10-13

Owner-authorized signed version 0.2.0, built from source commit `389ead8`, was
installed on both existing QN90A and S90D profiles through the shared setup engine.
The prior signed packages, enrollment backups and raw evidence remain private.
Both deployment journals completed after installed-content and post-reboot checks.

Both TVs passed:

- An 8 MiB + 123 byte upload with explicit resume after the first 1 MiB chunk,
  full SHA-256-verified download, and a 12,345-byte read spanning a chunk boundary.
- Rejection of a wrong current-file hash without changing the target, followed by
  successful replacement using the matching hash. A malformed binary chunk digest
  was rejected with the upload offset still zero.
- A 32-second app-profile job returning exit code 7 and retained output, explicit
  cancellation of a running job, and bounded output after producing 1,200,000 bytes.
  The latter reported cursor truncation and returned at most 64 KiB per tail read.
- App commands reporting UID/EUID 5001, GID 100, Smack `User`, the owner runtime
  directory, Wayland display and kernel D-Bus addresses.
- Upload, preparation and execution of an unsigned ARM helper as that app user.
  Mount readback confirmed the private helper view was read-only; release succeeded.
- A no-match `grep` returning exit code 1 and stdout normally, and a command timeout
  returning exit code 124 with `timed_out: true`.
- Automatic root-worker acquisition after a full software reboot, with a different
  boot ID and `worker_ready: true`. Readiness was first observed at approximately
  51 seconds of uptime on QN90A and 84 seconds on S90D; these are observations,
  not startup guarantees. App execution and digest/timeout checks passed afterward.

All 22 installed package inventory entries, enrollment certificates, protected
file hashes and enabled service boot flags verified after reboot. Developer Mode
was restored to loopback. Temporary SDK admission initially used a saved host
address while the administrator's Mac was on another network; access recovered
after correcting the Mac's network connection. No router change was required.
Samsung's HTTP Developer Mode address remained cached during live maintenance;
admission was instead checked against the live SDK setting while retaining model,
physical-device and firmware guards. Samsung's device-service reboot API was used
after S90D rejected the generic systemd reboot target.

The large-file check used an 8 MiB payload, not the 88 MiB Chromium library.
No power-loss, firmware-upgrade or long-duration stress acceptance is claimed.
