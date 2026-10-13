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

The app profile uses the signed worker's embedded native launcher. The .NET worker
continues to handle authentication, commands, jobs and transfers. The launcher
drops supplementary groups, uses UID/EUID 5001 and GID/EGID 100,
requires the `User` Smack label, sets HOME/USER/LOGNAME, PATH, the owner runtime
directory, Wayland display and D-Bus addresses, then runs in `/home/owner`.
A failed identity/label transition fails the command; it does not fall back to root
or the old managed launcher. Only standard input/output/error descriptors and an
explicit app environment reach the shell; inherited SDK/loader variables are removed.

During acquisition, the worker extracts its embedded ARM ELF into an exclusively
created, root-only directory under `/opt/couchroot-agent/launchers`, verifies its
digest, and creates a private read-only view. Root readiness requires successful
preparation. Each app invocation verifies the staged digest again. Clean shutdown
attempts to release its view and delete only its own two paths. Crashes or busy
mounts can leave directories for inspection; at 64 retained directories acquisition
refuses further staging. No arbitrary external launcher path is accepted.

`native-app-launcher-v1` in the ready worker's capabilities identifies this path.
The internal worker readiness handshake also returns the embedded launcher's SHA-256.
Build the toolchain image from `research/native-telemetry/collector/Dockerfile`
before preparing signed autonomous-root packages. The shared builder compiles from
source and embeds the result in the worker DLL for each TV framework. Ordinary
standalone .NET builds without the resource are useful for host tests but refuse
worker startup on a TV. `python3 scripts/check-root-launcher.py` verifies both
embedded targets and reproducibility without signing or contacting TVs.

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

The [native app-user launcher measurements](native-launcher/README.md)
compares measured command startup, worker memory, reacquisition and transfer costs
on both TVs motivated this implementation. The public app APIs remain unchanged.

## Native launcher acceptance — 2026-10-13

Signed autonomous-agent version **0.3.1**, built from `8df7949`, passed
owner-authorized deployment and hardware acceptance on both existing TV profiles.
The .NET worker remains installed; app commands and app-profile jobs now use its
embedded native launcher. Both shared deployment journals completed only after
post-reboot verification. Prior signed packages and private enrollment remain retained.

Both TVs passed:

- Verification of the signed build's native digest against the staged executable,
  root ownership, mode 0500 and a private read-only mount. App-user attempts to
  invoke this root-only path were denied before their command could execute.
- UID/EUID/saved UID 5001, GID/EGID/saved GID 100, no supplementary groups, zero
  effective capabilities and Smack `User`. The expected runtime environment was
  present; an injected environment marker and extra descriptor did not reach the shell.
- Exact single/double quotes, apostrophes, backslashes, newlines and post-reboot
  Unicode command output. Stdout, stderr and nonzero exit codes were preserved.
- A 31-second app job with output and exit code 7, app-command timeout, app-job
  timeout, and cancellation. Delayed descendant writes did not survive either
  timeout or cancellation. Unsigned helper upload, preparation, app execution and
  release also passed through the integrated launcher.
- Graceful worker reacquisition with the old launcher directory removed and a
  new native-capable worker ready, followed by quoted app execution.
- Full software reboot and autonomous root readiness with a new boot ID, then
  repeated app, timeout, digest-rejection, quoting and native-view checks. Readiness
  was first observed around 74.5 seconds of uptime on QN90A and 111 seconds on S90D;
  these are individual observations, not startup guarantees.

All 22 installed package inventory entries, enrollment certificates, protected
file hashes, enabled boot flags and restored loopback SDK host verified afterward.
Twenty short `app.exec` calls had median client round trips of 122 ms on QN90A and
110 ms on S90D. Earlier managed-launcher measurements were 303 ms and 455 ms;
these separate runs are indicative, not a paired performance guarantee.

The first QN90A 0.3.0 trial exposed an argument-quoting bug in the old command
runner. That trial's acceptance was cancelled, its evidence and signed package
retained, and 0.3.1 installed as a guarded forward correction. S90D received only
the corrected build. Structured process arguments now preserve the nested command;
the Linux harness covers that exact process boundary.

Local validation: 220 Python tests, 104 Node tests, 20 telemetry tests, native
failure-path tests on macOS and Linux, and the Linux root job/transfer harness
passed. Both embedded TV builds and the source-only cross-path native/unsigned
package builds reproduced. Public-source privacy and secret scans passed.

## Buffered protocol reads

The .NET worker uses one 64 KiB input buffer per connection for both protocol
lines and legacy binary payloads. It scans each block for newlines and retains
read-ahead bytes for the next frame or payload. Responses still write directly
to the duplex socket. The 4 MiB line limit, authentication, transfer chunk size,
digest checks and conditional-replacement rules are unchanged.

The local harness covers single-byte fragmentation, coalesced frames, split UTF-8,
CRLF, empty lines, exact-limit and oversized lines, truncated input, and binary
payloads spanning multiple buffers between text frames. An instrumented stream
rejects unbuffered byte reads and checks the number of block reads.

### Upload benchmark — 2026-10-13

Owner-authorized measurements compare agent 0.3.1 with buffered-reader 0.4.0
(source `1a89d14`) on the existing QN90A and S90D profiles. Each version ran three
8 MiB random-file uploads per TV using the existing client and 1 MiB chunks,
followed by downloads whose SHA-256 matched the source. Timings include the full
client operation, including transfer setup and commit; the same local payload was
reused before and after each TV's update.

| TV | Median upload before | Median upload after | Observed speedup | Upload after | Median download before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| QN90A | 37.93 s | 4.92 s | 7.72× | 1.63 MiB/s | 6.36 → 6.00 s |
| S90D | 41.20 s | 4.70 s | 8.77× | 1.70 MiB/s | 5.05 → 5.64 s |

Upload trial ranges were 35.79–39.05 s before and 4.44–6.05 s after on QN90A.
S90D ranges were 39.44–41.58 s before and 4.00–6.53 s after.
These are small before/after samples over the owner's network, not
isolated CPU measurements or a throughput guarantee. Both TVs collected their
baseline trials concurrently; updated-TV trials ran separately. Downloads did
not show a consistent improvement. No client protocol, chunk-size or native-worker
rewrite was required; the .NET worker and native app-user launcher are retained.

### Buffered-reader hardware acceptance

Signed version 0.4.0 passed the shared deployment and acceptance workflow on both
TVs. All 22 installed package inventory entries, existing enrollment certificates,
protected file hashes, enabled boot flags and restored loopback SDK setting were
verified after full software reboots. Both journals were finalized only after
these checks. Prior signed packages and raw evidence remain in private storage.

Both TVs passed an 8 MiB + 123 byte transfer resumed after its first chunk,
SHA-256-verified download, unaligned byte ranges, corrupt-chunk rejection, and
conditional replacement with both wrong and matching current hashes. Root and
app commands preserved quotes, Unicode, stdout, stderr and nonzero results.
App execution and unsigned helper staging/release retained UID 5001, GID 100 and
Smack `User`. Long jobs, bounded logs, cancellation, timeouts and stopped
descendants also passed.

After reboot, a different boot ID and ready root worker were observed at about
70 seconds uptime on QN90A and 108 seconds on S90D. Post-boot checks repeated
app execution, quoting, timeout and digest rejection, verified the protected
native launcher, and completed another 1 MiB + 17 byte upload/download with a
matching SHA-256. These are software reboot observations, not physical power-loss
or firmware-upgrade acceptance.

Local validation passed: 220 Python tests, 104 Node tests, 20 telemetry tests,
the buffered-reader harness and Linux root job/transfer harness, both embedded
TV build reproducibility checks, and all 42 source-only native assemblies plus
the unsigned Hub package across build paths. Public-tree and outgoing-commit
privacy/secret scans were clean.
