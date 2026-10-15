# Persistent worker capabilities

These changes require rebuilding the service and worker together. Existing installed
0.1.x workers do not expose the new operations. Source validation is separate from
TV installation and firmware-specific acceptance; no deployment is implicit.

All examples use the existing enrolled, certificate-pinned client:

```sh
python3 research/autonomous-root/client.py --config /private/client.json status
```


## Held native rehearsal (migration candidate)

`POST /v1/native/rehearse` accepts exactly `{id, manifest_sha256,
runtime_sha256}`. It requires a ready managed worker and a fallback runtime digest
matching the enrolled `/usr/bin/dotnet` pin. Firmware preflight and a read-only hash check through the existing managed worker
run before the migration controller starts. The response must come from the same
worker generation. A mismatch, timeout or unconfirmed check refuses the rehearsal
without stopping the source; managed launch independently rechecks runtime bytes.
The request is durably journaled before dispatch and returns HTTP 202 with
`state: submitted` and `status_url: /v1/native/status`. This acknowledgement does
not mean migration succeeded. The controller performs a held managed → native →
managed rehearsal. Administrative writes are refused while it runs; status and
request-journal reads remain available.

Use `native-rehearse --request-id UNIQUE_REQUEST_ID --manifest-sha256
CANDIDATE_MANIFEST_SHA256 --runtime-sha256 ENROLLED_RUNTIME_SHA256` with the client.
Use `native-status` to inspect the operation and migration phase. IDs must be
persisted before submission; neither the client nor service retries a submission.

`POST /v1/native/resume-managed` accepts exactly `{id, rehearsal_id}`. The new ID
must differ from the original rehearsal ID and bind to the live coordinator's
unknown rehearsal. The controller permits only its final managed-activation
recovery boundary; this is not general rollback or restart recovery. The client
command is `native-resume-managed --request-id NEW_REQUEST_ID --rehearsal-id
ORIGINAL_REQUEST_ID`. Recovery has a separate journal entry, and a successful
recovery does not rewrite an unknown original request as completed.

Only one rehearsal is admitted per live coordinator. A service restart retains
request replay protection but does not reconstruct in-memory recovery handles.
These routes are locally qualified and are not yet deployed to either TV.

## Results and readiness

The migration candidate adds `POST /v1/observer/probe`, using the same enrolled
client and serialized administrative admission as other mutations. Its body is
exactly `{id, manifest_sha256}`: no PID, path or command is accepted. The manifest
must match the installed native candidate. The service journals the request before
staging permission on the fixed observer package member, then launches it in the
service context. S90D binds/cancels a pidfd observation after fresh worker identity
confirmation; QN90A uses proc-stat and checks executable launch separately. Neither
path submits worker shutdown or selects native.

```sh
python3 research/autonomous-root/client.py --config /private/client.json \
  observer-probe --manifest-sha256 CANDIDATE_MANIFEST_SHA256 \
  --request-id UNIQUE_REQUEST_ID
```

Success reports `verified`, `method`, manifest/observer digests, boot/worker IDs
and `worker_stopped: false`. It establishes observation setup and cancellation,
not target exit, native selection or cleanup parity. The HTTPS idle response
budget is 120 seconds and client timeout 130 seconds; underlying request and
observer deadlines remain bounded separately. Request IDs are not replayed after
success or uncertainty. Confirmed executable failures are `failed`; uncertain
staging or observer state retains the admission hold for inspection. Known probe
failure after confirmed staging/child completion can release the hold while
preserving the executable mode change. These behaviors have local tests only;
actual TV service execution is not yet qualified.

`exec` returns `exit_code`, `timed_out`, `stdout`, and `stderr`, including on a
nonzero exit. A received timeout result is a known result. HTTP failures include
`outcome`: `rejected` means admission failed, `failed` means the worker returned an
operation failure, and `unknown` means a submitted operation's result could not be
confirmed. An operation failure does not imply rollback of its intermediate work.
The client never automatically replays commands or writes. Consult the request
journal and operation status after a lost response.

Operation response budgets in the migration candidate are 120 seconds for
`file.open`, `file.commit` and `helper.prepare`, 60 seconds for `file.read` and
`file.write`, and 30 seconds for other worker operations. HTTPS allows a further
five seconds and the bundled client ten seconds for the response. These fixed
budgets cannot be extended by request fields. They do not change command/job
execution deadlines, the native progress watchdog, request-body admission, or the
five-second keep-alive idle limit. Expiry closes the worker connection, returns an
unknown outcome and leaves a submitted mutation in the journal; it never retries
it. Older deployed clients retain their earlier timeout until updated. These
budgets have local transport validation and are not yet deployed to either TV.

`AgentTransport.execute_result()` returns the complete result. Existing setup
callers retain checked execution; `_execute(..., check=False)` is available when
only stdout is needed and a nonzero exit is expected.

The migration service accepts worker readiness only after matching the current
local boot ID, a valid worker identity, the expected implementation's complete
capability set, and launcher metadata. The existing managed status format without
an `implementation` field remains supported; an explicit mismatched implementation
is rejected. Native readiness validation additionally requires a pinned launcher
digest, independent staging, a guardian identity and production lifetime mode.
That validation path does not itself enable native selection.

Commands and operations are rejected while a connection is still being checked.
Disconnect and stop clear current worker status. Late replies or errors from an
old connection cannot restore readiness or overwrite a replacement's status.
Boot-launch inspection waits for worker validation. These checks require device
qualification, including service access to the local boot ID, before deployment.

The migration candidate reports `selected_implementation` (managed by default),
`worker_selection` and `native_candidate`. Candidate state is `absent`, `invalid`, or `verified`, with a
`checked_at` timestamp and a bounded reason code on failure. Verification reports
the native manifest digest and `device_qualified: false`; it does not establish
worker readiness, verify device libraries, or select native. Checks run at service
creation and before an acquisition attempt. Legacy packages remain supported, and
invalid optional candidate files do not disable managed fallback. These fields
are local migration work and are not yet deployed to either TV.

The optional private `worker-selection.json` record is an internal migration
journal, not an exposed switching API. Its absence preserves legacy managed
startup. Pending transitions, uncertain writes and mismatched managed package
versions block acquisition and new command admission with `selection-required`.
Existing work is not silently killed by a metadata change. A recorded native
selection is currently blocked with `native-runtime-not-integrated`; it is not a
working native launch switch. Record mutation requires the future controller to
quiesce workers and verify artifact/state/readiness evidence. Do not create or
edit this file as a shortcut to native deployment.

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

## HTTPS connection reuse

Agent service 0.6.0 honors an explicit `Connection: keep-alive` on successful
responses. JSON and binary responses carry exact content lengths. Each socket
serves at most 128 requests and has a five-second idle timeout; errors close the
connection. Mutual TLS enrollment and browser-origin checks still run on every
request. The existing eight-connection bound and serialized administrative
operations remain in force.

The Python client's `upload` and `download` each own a sequential `Session`.
They reuse one TLS connection across transfer setup, chunks and completion,
rotating before a new request after 128 requests or four seconds idle. The session
closes when the transfer scope exits. Every new socket undergoes certificate-pin
verification before submission, and implicit HTTP-library reconnection is disabled.
One-off `request`/`operation` calls still close their connections unless given an
explicit session; sessions must not be shared concurrently or across configurations.

A transport failure, invalid response, HTTP error or digest mismatch closes and
invalidates the session. No request is automatically replayed, including a request
that encounters a stale keep-alive socket. Diagnose the outcome before explicitly
resuming an upload. A successful response that explicitly closes the socket permits
a new, re-pinned connection for the next request; this also supports older services.
HTTPS reuse does not change the .NET worker or native app-user launcher.

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
per-chunk SHA-256 and a complete-file digest. Agent 0.5.0 adds
`binary-download-v1`: the .NET worker sends a small HMAC-authenticated `OPDATA`
header binding the request sequence, offset, byte length and SHA-256, followed by
at most 1 MiB of raw bytes. The service verifies the pending read, range and digest
before returning any bytes over HTTPS. It rejects malformed, oversized, truncated
or corrupted responses by closing the worker channel; it never retries the request.
The worker and service must be upgraded together. HTTPS clients are unchanged,
and the new service still accepts the earlier JSON/base64 worker responses.

Agent 0.7.0 adds `binary-upload-v1`: the service sends an HMAC-authenticated
`OPWRITE` header binding the sequence, transfer ID, offset, byte length and SHA-256,
then at most 1 MiB of raw bytes. Chunk payloads are no longer encoded in JSON or
base64 between the service and the retained .NET worker. HTTPS clients are unchanged.
The journal binds the upload metadata, actual body length and verified digest.
The worker authenticates and bounds the header, reads the entire chunk before any
write, then verifies its digest and expected offset. Malformed framing or truncated
bodies close the channel; known operation failures leave it aligned. Durable chunk
flushes, final-file verification, conditional replacement and no-retry behavior are
preserved. Upgrade service and worker together; legacy JSON operations remain
available internally for compatibility, without automatic fallback after failure.

The worker holds at most eight
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

## Binary download benchmark — 2026-10-13

Owner-authorized trials compared agent 0.4.0 with signed 0.5.0 built from
`faaa6e2`, retaining the .NET worker and native app-user launcher. Each TV ran
three uploads/downloads of the same 8 MiB random payload per version, using the
unchanged client, 1 MiB chunks and complete SHA-256 verification. Download times
include opening/hashing the source, HTTPS requests, local file synchronization,
publication and transfer close.

| TV | Median download before | Median download after | Observed speedup | Download after | Median chunk read before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| QN90A | 5.84 s | 3.64 s | 1.61× | 2.20 MiB/s | 656 → 346 ms |
| S90D | 4.99 s | 2.03 s | 2.46× | 3.94 MiB/s | 558 → 228 ms |

QN90A download trials ranged from 5.76–5.89 s before and 3.03–3.65 s after;
S90D ranged from 4.78–5.26 s before and 2.01–2.22 s after. Per-chunk medians use
all 24 full-size reads in each set. Both TVs collected baselines concurrently;
updated-TV trials ran separately. These are small samples over the owner's
network, without isolated CPU/load controls, and are not throughput guarantees.

Upload medians in those same trials were 4.75 → 5.17 s on QN90A and
4.05 → 4.93 s on S90D. Upload framing was unchanged; these samples do not
establish an upload improvement or a cause for that variation. Fresh TLS
connections per request remain part of both versions' measured cost.

The download change removes both base64 layers and JSON serialization for chunk
responses on the local worker connection. Its receiver accumulates text frames
with bounded geometric buffer growth and copies binary bodies into a buffer
sized only after authenticating and validating their header. Other operations
retain authenticated text responses, including known failures; a partial binary
write cannot be followed by a misleading success or failure frame.

### Binary download hardware acceptance

Both signed 0.5.0 deployments completed through the shared setup engine after
full software reboot and post-boot verification. All 22 installed inventory
entries, enrollment certificates, protected file hashes, enabled boot flags and
restored loopback SDK setting verified. Previous signed recovery packages and
raw evidence remain private.

Both TVs passed resumed 8 MiB + 123 byte transfers, complete-file digests,
unaligned ranges, bad-chunk rejection, and conditional replacement with wrong
and matching current hashes. App-user commands, native launcher protections,
unsigned helper staging/execution/release, nonzero results, bounded logs, long
jobs, timeouts, cancellation and stopped descendants also passed.

After reboot, the new binary-download capability and root readiness were observed
with different boot IDs at approximately 51 seconds uptime on QN90A and 88 seconds
on S90D. A fresh 1 MiB + 17 byte upload/download matched its digest on each TV;
a direct read at EOF returned a valid zero-byte binary response. Post-boot app,
quoting, timeout, digest rejection and native-view checks passed. Both deployment
journals were then finalized. This does not claim physical power-loss testing.

Local validation passed: 220 Python tests, 116 Node tests, 20 telemetry tests,
the production .NET wire-format/transfer harness and Linux root job harness.
Protocol tests cover fragmented headers/bodies, adjacent text responses, zero
and maximum-length bodies, authentication/digest failures, wrong sequences and
ranges, oversized input, truncation, and legacy JSON/base64 compatibility. Mutual
TLS tests verify raw HTTP response bytes/headers and reject a bad worker digest.
Both embedded TV builds and all 42 source-only native assemblies plus the unsigned
Hub package reproduced across build paths. Public-tree and outgoing-commit
privacy/secret scans passed.

## HTTPS reuse benchmark — 2026-10-13

Signed agent 0.6.0 was built from `105d020`. Both TV builds contain a .NET worker
byte-for-byte identical to 0.5.0; this change is confined to the HTTPS service and
Python client. The native app-user launcher remains in place.

After collecting three 0.5.0 baseline trials per TV, the 0.6.0 comparison alternated
fresh connections and reuse on the same installed version. Each mode ran three
8 MiB uploads/downloads per TV using the same random payload and 1 MiB chunks.
Every download matched the original SHA-256. Timings include transfer controls,
chunk requests, hashing and local publication; actual TLS connects were counted.

| TV | Download median, fresh → reuse | Download time reduction | Upload median, fresh → reuse | TLS connections per transfer, fresh → reuse |
| --- | ---: | ---: | ---: | ---: |
| QN90A | 2.85 → 2.48 s | 13% | 4.57 → 5.17 s | 10 → 1 |
| S90D | 2.19 → 1.39 s | 36% | 4.96 → 4.90 s | 10 → 1 |

Download trial ranges were 2.78–2.86 s fresh versus 2.45–2.77 s reused on QN90A,
and 2.07–2.46 s fresh versus 1.28–2.54 s reused on S90D. Upload timings varied
substantially: QN90A reuse ranged from 3.62–5.62 s and S90D from 3.37–4.91 s.
These small samples demonstrate fewer TLS connections and lower median download
times; they do not establish a consistent upload speedup or a throughput guarantee.
Network, runtime and storage load were not isolated.

The earlier 0.5.0 baseline medians were 3.10 s download / 4.03 s upload on QN90A
and 3.12 s download / 3.94 s upload on S90D, also with ten connections per transfer.
Those baselines ran concurrently across TVs. The reported reuse gains above use
the stronger alternating, same-version comparison instead of attributing all
before/after variation to this change.

### HTTPS reuse hardware acceptance

Both signed 0.6.0 updates completed through the shared setup engine after software
reboot and post-boot acceptance. All 22 installed inventory entries, existing
enrollment certificates, protected file hashes, enabled boot flags and restored
loopback SDK setting verified. Prior signed packages and raw evidence remain private.

Both TVs passed resumed transfers, complete-file digests, arbitrary ranges, EOF,
corrupt-chunk rejection and conditional replacement. App-user identity, native
launcher protections, unsigned helper staging/execution/release, nonzero results,
long jobs, bounded output, cancellation, timeouts and stopped descendants passed.
Root readiness with a new boot ID was observed around 46 seconds uptime on QN90A
and 93 seconds on S90D, followed by another SHA-256-verified multi-chunk transfer.
These are software reboot observations, not physical power-loss tests.

Post-boot connection tests on each TV confirmed three status requests on one TLS
connection, rotation after 4.2 seconds idle, two connections across 129 sequential
requests, closure at scope exit, and rejection of an incorrect server pin before
an HTTP request could be sent. All deployment journals were finalized afterward.
Before S90D's update, the new client also verified safe compatibility with its
older service: two successful requests used two connections as instructed by the
service's close responses.

Local validation passed: 226 Python tests, 116 Node tests and 20 telemetry tests.
The Python and Node service were tested together over real local mutual TLS for
reused JSON and binary requests. Tests cover server request-limit closure, origin
checks on a reused socket, per-connection pinning, client rotation, stale sockets,
timeouts, truncated/invalid responses, failed-session closure and no replay.
Both embedded TV builds and all 42 native assemblies plus the unsigned Hub package
reproduced across build paths. Public-tree and outgoing-commit privacy/secret scans
passed; raw device data, credentials and signed packages were excluded.

## Binary upload benchmark — 2026-10-13

Agent 0.7.0, built from source commit `54f2182`, removes nested base64/JSON
encoding of upload chunk bodies between the HTTPS service and the .NET worker.
The worker remains .NET; the native app-user launcher is unchanged. A full 1 MiB
chunk now travels as raw bytes plus a small authenticated header, eliminating
approximately 44% of the previous loopback request bytes.

The same client uploaded an 8 MiB random file three times per TV before and after
the update, with 1 MiB chunks, durable flushes, complete-file SHA-256 verification
and one pinned TLS connection per transfer. Each upload was downloaded and verified.
Numbers include setup, chunks and commit; they are medians of complete transfers.

| TV | 0.6.0 upload | 0.7.0 upload | Less time | Throughput change |
| --- | ---: | ---: | ---: | ---: |
| QN90A | 4.22 s | 2.68 s | 37% | 1.58× |
| S90D | 5.28 s | 2.84 s | 46% | 1.86× |

These are small before/after samples on a live wireless network, not an isolated
CPU benchmark or a throughput guarantee. Individual upload times varied:
QN90A 4.14–5.30 s before and 2.39–4.04 s after; S90D 3.80–6.59 s before and
1.95–4.44 s after. Downloads were unchanged in code; their median timings were
2.64 → 2.73 s on QN90A and 1.18 → 1.24 s on S90D.

Both installed packages passed file inventory and enrollment checks, retained the
protected system-file hashes, restored SDK loopback access, and preserved existing
boot settings. Live acceptance covered maximum-sized binary chunks, unknown
transfers, wrong/replayed offsets, digest rejection without offset advancement,
resume, byte ranges, EOF, final hashes and conditional replacement. It also covered
app UID 5001 and Smack `User`, quoted commands, runtime environment, native launcher
integrity/read-only mounting, unsigned helper staging/execution/release, nonzero
results, long jobs, cancellation, timeouts and bounded logs. HTTPS reuse, idle/count
rotation and certificate-pin rejection passed on both TVs.

**Neither TV was rebooted, at the owner's request.** Both boot IDs remained
unchanged through acceptance. Reboot persistence was not tested for this version.

Local validation passed 226 Python tests, 118 Node tests, 20 telemetry tests,
the legacy protocol checks, the .NET harness on macOS and Linux (including process
supervision on Linux), reproducible ARM launcher/embedded-worker checks and
cross-path source-only builds. Upload protocol tests cover authenticated metadata,
raw byte preservation, fragmented/coalesced reads, bounds, truncation, digest and
offset failures, channel alignment and no replay after disconnect. Private device
identities, signed artifacts and raw evidence remain outside the repository.

## Native worker experiment

A separate [C worker prototype](native-worker/README.md) was compared with temporary
copies of the deployed .NET worker on both TVs. It reduces startup and memory cost,
but lacks production job, helper lifecycle and root-acquisition/recovery parity.
It is not selected or packaged by the service. The deployed .NET 0.7.0 workers
remain unchanged; neither TV was rebooted. See the experiment's aggregate metrics,
capability matrix and limitations before considering a replacement.

## Worker handoff inventory

Workers advertising `resource-inventory-v1` add `resources` to their fresh wire
`status` result. Schema 1 has scope `worker-owned`, up to eight transfers
(`id`, `direction`), sixteen in-memory jobs (`id`, `state`, `monitor_finished`),
and eight helper IDs. Array order is unspecified. Completed in-memory jobs remain
listed until forgotten. Disk-only records and old helper directories are excluded.
No paths, command text or output are included. `monitor_finished` means that job's
monitor finished; it does not prove descendant cleanup, output draining or durable
state reconciliation. Empty arrays alone do not establish quiescence.

The service has an internal `holdAdmission()` interface for the upcoming handoff
controller, with no HTTP route or CLI switch. It immediately blocks new requests,
reports `admission_held`, `in_flight_requests`, phase `draining` and
`worker_ready: false`. Its `snapshot()` waits for already-admitted requests, then
requests and validates fresh inventory from the same connection, generation,
boot and worker identity. An uncertain drained result, missing inventory capability,
invalid inventory or changed connection refuses the snapshot and leaves the hold
in place. An explicit `release()` resumes that same worker; stop invalidates old
handles. The hold never cancels jobs, closes transfers, releases helpers, migrates
records or commits selection. It is process-local; the selection journal is required
to prevent admission after a service restart.

The controller must separately reconcile prior unknown journal outcomes, saved
records and resource ownership, then verify shutdown before state installation.
The ordinary readiness path continues to accept older managed workers without
this capability; those workers cannot provide a handoff inventory.

Workers advertising `worker-process-identity-v1` also report `processes.worker`
and `processes.guardian`: each identity contains a PID and decimal `start_ticks`
string. The managed guardian is null. Native reports its supervising guardian.
These identities are bound to boot and worker ID and checked against the
authenticated worker PID. Start ticks remain strings to avoid integer rounding.

An internal hold's `shutdown(transactionId)` supports the current managed selection.
Initialize the selection journal before creating the hold. After inspection, bind
the fresh snapshot's JSON SHA-256 to the pending prepared transaction's
`quiescence_sha256` field. This field binds the pre-shutdown inventory; it is not
itself proof of process exit or filesystem cleanup. Shutdown repeats the snapshot,
requires its hash and source version to match that transaction, refuses open
transfers/helpers and unfinished or uncertain jobs, and verifies current process
identities before sending the existing authenticated `SHUTDOWN` frame once.

The wire client requires a matching `BYE` and disconnect within ten seconds.
Because `BYE` precedes cleanup, the hold then observes `/proc` for up to ten seconds
to establish that the original process identities have gone. A different start
time means that PID was reused; it is never signalled. A matching zombie remains
present. Permission errors, malformed observations, boot changes and deadline
expiry fail the check. Both worker and guardian must be gone for native process
observations. No automatic reacquisition occurs while admission is held; a
replacement connection during submitted shutdown is refused. The hold cannot be
released after submission, including an uncertain result.

The result binds transaction ID, source manifest, inventory hash, acknowledgement
and process-exit observations. It does not advance selection, install data or prove
that every detached managed descendant, mount or retained record is reconciled.
Those are separate gates before state installation. Focused hardware probes found
that QN90A's service identity can read the required proc-stat fields, whereas
S90D's package-labelled identity receives EACCES. The direct observer remains
unavailable on S90D; permission denial must never count as absence. S90D's kernel
supports unprivileged pidfd binding and exit polling, verified across an ordinary
native sidecar's shutdown. A production pidfd bridge and actual wrt-service
integration remain required. The probes match service credentials in separate
processes; they do not update or exercise new code inside the installed service.
