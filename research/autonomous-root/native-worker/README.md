# Native worker experiment

This C prototype is a measurement sidecar, **not a production replacement**. It
is not referenced by the package builder, service selection or boot configuration.
The installed .NET worker remains active throughout a comparison. No SDK changes,
service replacement, root reacquisition or TV reboot is needed.

The prototype uses the existing HMAC protocol with strict sequence ordering,
bounded binary chunks and structured failure responses. It implements status,
root commands, bounded output and process-group timeouts, app commands through a
independently staged, digest-verified native launcher, and file begin/write/status/read/commit/close with
per-chunk/full-file hashes and conditional replacement. File access is deliberately
restricted to direct children of a private, root-owned experiment directory.
It loads the TV's libcrypto and json-c APIs, rather than implementing cryptography
or a complete JSON parser itself. This is still experimental C with a substantially
smaller test history than the managed worker.

The lifecycle extension adds `job.start/status/output/cancel/forget` with a
supervisor thread, root/app profiles, exclusive durable launch intents, bounded
1 MiB rings per stream and 64 KiB cursor windows. Sixteen jobs can be retained in
memory and 64 records on disk. Records live under the experiment's private `.jobs`
directory, locked to one native worker. Restarted workers report saved outcomes
and refuse to replay starts. Logs are in-memory only. Cancellation of a saved,
previous-worker job is deliberately refused on these older kernels: process-group
ownership cannot be established atomically from a saved PID. Unknown records
require inspection, rather than being treated as safe to forget.

`helper.prepare/release` copies a digest-checked source from the experiment file
scope into an exclusively owned `/opt/couchroot-agent/native-helpers` directory,
sets Smack `User`, and creates a read-only, nosuid/nodev bind view. The native worker
unshares its mount namespace before starting threads. It owns at most eight views;
release is refused while any of its jobs are active. A separate native guardian kills/reaps remaining descendants before unmounting
helpers and its independently staged launcher. Failed unmounts retain their backing files.
Worker SIGKILL/crashes are recovered by that guardian; loss of the guardian itself
leaves its journal for explicit inspection. There is no durable log recovery. The
controller and deployed .NET worker retain their original namespace.

Missing parity still includes autonomous root acquisition and production
packaging/recovery integration and the broader production file
access policy. Legacy READFILE/WRITEFILE and JSON file.write are omitted. Unsupported
operations fail explicitly; there is no automatic fallback or replay. The build also produces the existing native `app-launcher` source as a separate
binary. The worker accepts its source path inside the canonical file scope and an
expected SHA-256; it validates ARM ELF32, stages a private root-only copy, applies
Smack and a read-only bind mount, and verifies the staged digest before use. It no
longer accepts a borrowed .NET execution view. Root acquisition and transport
service integration are still borrowed, so startup is not complete service startup. The worker's five-minute
experiment lifetime remains bounded; jobs cannot outlive that worker. Disconnect,
SIGTERM and graceful shutdown clean up owned active jobs and helper views.

The worker executable starts a small guardian before the protocol worker and its
threads. The guardian is a Linux child subreaper and holds the scope lock, runtime
mount namespace and durable ownership journal. After a worker dies, it kills and
reaps its actual children, including adopted detached descendants, before changing
its own nonterminal job records to `interrupted` and deleting owned execution views.
It never signals a PID from a saved job file. Completed records remain unchanged;
crash records have an unknown exit code and unavailable in-memory output. A new
worker invocation reads those records and refuses duplicate starts. It does not
automatically restart or replay commands.

Failure to finish recovery retains the ownership journal and blocks replacement.
Loss of both worker and guardian, storage corruption, power loss and uninterruptible
processes remain fail-closed/manual-inspection cases. This prototype does not
replace the deployed service's root acquisition, enrollment or restart machinery.

`accept.c` exercises the native job/helper lifecycle on the TV via a private
loopback controller. It checks an over-25-second job, simultaneous foreground and
background execution, app-user helper execution, read-only mounts, output limits,
cancellation, retention, disconnect cleanup and saved status after a native restart.
These checks do not restart the production worker or TV.

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
kernel clock-tick resolution. Warm-cache worker startup is not boot readiness. The updated harness includes
guardian CPU and reports its memory separately; old measurements below predate
the guardian and must not be attributed to the current implementation.

Build outside the source checkout with the project's cached ARMv7 soft-float
Bullseye toolchain:

```sh
sh research/autonomous-root/native-worker/build.sh /private/native-worker-build
```

On Linux, compile `worker.c` with `-DNATIVE_WORKER_TEST` only for the host tests,
which substitute the unavailable host Smack label and explicitly disable helper
staging when the real Smack/mount guards cannot run. Link with `-pthread -ldl`. Use address/undefined-behavior
sanitizers and set `NATIVE_WORKER` to that executable when running
`tests/native_worker_test.py`. The normal ARM build never enables this test mode.
Tests cover authentication, replay, corrupted/truncated transfers, bounds, path
and symlink rejection, conditional replacement, bounded output and timeouts.
Job tests also cover duplicate intents, cursor truncation, retention, signal and
disconnect cleanup, and saved-record handling.

Device execution must use the enrolled .NET client's existing verified upload,
helper and job APIs with firmware guards, per-device locks, durable private
intent/results, unique staging names and a bounded run. Prepare the controller and worker as private read-only helpers. Upload the freshly
built launcher as a regular file inside the native file scope; do not supply the
deployed launcher path. Use a token/status directory below the SDK staging root so the existing managed
worker can run unchanged. Set `COUCHROOT_BENCH_FILES` to a separate canonical,
private directory below `/opt/couchroot-agent/files` for both workers’ transfers.
The SDK staging path may have symlinked ancestors on the TV; it is not suitable
for the native prototype’s strict canonical file scope. Pass the actual
installed DLL for that device and the new launcher source/digest, never another
model's runtime paths.
Inspect results before releasing helper views and deleting only owned experiment
files. Preserve credentials, raw measurements and signed artifacts outside Git.

## Historical lifecycle validation before independent staging — 2026-10-13

The extended worker at `ffe97f3` passed **12 acceptance groups on QN90A and S90D**.
Each controller exited zero. [lifecycle-results.json](lifecycle-results.json)
contains the source revision, worker digest and sanitized per-device results.

- A 27-second background job completed while other requests ran and the connection
  sat idle. Duplicate starts and forgetting active jobs were rejected.
- Root and app jobs returned actual exit codes and cursor-based stdout/stderr.
  A 1,200,004-byte output verified ring truncation, the 64 KiB response window,
  retained tail bytes and invalid-cursor rejection.
- Timeout and cancellation killed owned process groups while a foreground command
  was busy. A shell that exited before its descendants retained a waitable PID
  until group cleanup, preventing cancellation from targeting a reused PID.
- Native-prepared unsigned helpers ran with UID/EUID 5001, GID 100 and Smack `User`.
  Wrong digests were rejected, writes to the mounted executable failed even as
  root, and native mounts were absent from the controller's original namespace.
- Helper release, duplicate release rejection and the eight-view retention limit
  passed. Active jobs prevented helper release.
- Disconnect, graceful shutdown and SIGTERM cleaned up active jobs and helper
  views. Fresh native processes read saved terminal/interrupted records, refused
  duplicate starts, and forgot completed records without replaying them.

Local validation passed 226 repository tests plus 16 native tests under address
and undefined-behavior sanitizers. The latter were run explicitly in the Linux
container; normal repository discovery skips them without a native executable.
The real helper lifecycle was validated on the TVs, not simulated by host tests.
Intentional disconnect/signal tests produce the expected transport-closure
message from the prototype; controller success requires the subsequent cleanup
and saved-state checks to pass.

Both original .NET workers stayed ready with unchanged worker IDs, PIDs and boot
IDs. Their launcher hashes, execution mounts and protected-file hashes matched
baseline. All experiment jobs, helper views, sources and owned storage were removed.
Neither TV was rebooted. The initial lifecycle build also passed ten groups on
each TV before the foreground-process hardening and expanded final acceptance run.

This closes the basic job API and native helper-view gaps. It does **not** qualify
full production parity: the five-minute experimental lifetime, in-memory logs,
conservative refusal of previous-worker cancellation, abrupt-crash recovery,
independent launcher staging and autonomous acquisition remain differences.
The .NET worker remains the deployed implementation and fallback. These lifecycle
runs do not update the earlier CPU, memory or startup measurements below.

## Historical comparison before the lifecycle extension — 2026-10-13

The native worker built from `8d8e195` completed eight measured pairs per TV after
two warmup pairs. The follow-up harness `fb5bcc4` used the **identical native worker
bytes**, two measured pairs per TV, a 20-second idle window and three subsequent
transfers per process. The production .NET 0.7.0 worker remained running; temporary
managed workers used that TV's installed DLL. All samples finished successfully.
Aggregate metrics, ranges and sample counts are in [results.json](results.json).
The native worker executable was 37,788 bytes, unstripped, excluding shared libraries.

| Median metric | QN90A .NET | QN90A C | S90D .NET | S90D C |
| --- | ---: | ---: | ---: | ---: |
| Worker readiness | 457.6 ms | 11.1 ms | 748.4 ms | 12.3 ms |
| Worker CPU through readiness | 366 ms | 8 ms | 704 ms | 8 ms |
| Freshly ready RSS | 21.15 MiB | 1.26 MiB | 22.14 MiB | 1.27 MiB |
| Freshly ready PSS | 8.36 MiB | 0.32 MiB | 8.18 MiB | 0.33 MiB |
| Freshly ready private resident memory | 6.19 MiB | 0.31 MiB | 6.94 MiB | 0.32 MiB |
| PSS immediately after initial workload | 9.76 MiB | 0.24 MiB | 11.47 MiB | 0.37 MiB |

PSS apportions shared resident pages; private memory excludes shared mappings.
These freshly ready samples had no swap. They are warm-cache launches and include
app-launcher preparation for .NET, while C verifies and borrows an existing launcher.
**They do not establish a 41–61× improvement in complete service/root acquisition.**
The prototype does less lifecycle work and has fewer capabilities.

The follow-up used 8 MiB + 17-byte files and reports six warmed-up transfers per
implementation per TV after a 20-second pause. These are TV-local protocol costs,
not HTTPS upload/download timings; disk flushing remains enabled.

| Warm transfer median | QN90A .NET | QN90A C | S90D .NET | S90D C |
| --- | ---: | ---: | ---: | ---: |
| Upload worker CPU | 160 ms | 134 ms | 342 ms | 134 ms |
| Upload elapsed | 394 ms | 384 ms | 461 ms | 360 ms |
| Download worker CPU | 58 ms | 56 ms | 70 ms | 50 ms |
| Download elapsed | 84 ms | 87 ms | 89 ms | 83 ms |

Upload CPU fell by about 16% on QN90A and 61% on S90D in this small follow-up;
elapsed upload time fell only about 3% and 22%. Initial transfer medians were even
closer: C uploads were slightly slower on both TVs. CPU measurements include the
worker's hashing, protocol handling, runtime/GC work and kernel time, but exclude
controller and shell-child CPU. They do not isolate cryptographic throughput.

S90D's managed process consumed 420–492 ms of CPU during the first second of the
long idle follow-up, then only 4–8 ms over the remaining 19 seconds. QN90A's .NET
workers used 8–12 ms over those 19 seconds; native workers registered zero clock
ticks. This shows transient activity after the workload, consistent with runtime
warmup/JIT, rather than sustained idle CPU use. CPU accounting resolution was 4 ms.

Both TVs aggressively reclaim/swap idle pages. After 20 seconds, native PSS could
fall to 11–12 KiB while roughly 332–336 KiB was in swap; managed PSS fell to roughly
2.6–3.6 MiB while another 7.0–7.5 MiB was swapped. Reporting resident memory alone
at that point would hide memory commitment. `results.json` retains RSS, PSS,
private resident memory, swap and proportional swap for each measurement stage.

### Capability comparison at the original measured revision

| Capability | Native result on both TVs | Remaining difference |
| --- | --- | --- |
| Authentication/readiness | HMAC handshake and status passed | Existing root acquisition is borrowed; no autonomous acquisition/recovery |
| Root command results | Exit 7, stdout/stderr and process-group timeout passed | Long-lived production supervision remains unqualified |
| App execution | UID 5001, Smack `User`, runtime environment and quoted Unicode passed | Uses the deployed worker's verified native launcher view |
| Binary transfer | 1 MiB chunks, byte/digest verification, ranges, EOF, wrong/replayed offset and conditional replacement passed | Files restricted to one canonical private directory; legacy transfer frames omitted |
| Unsigned helper execution | Existing staged helper ran correctly as the app user | `helper.prepare`/`helper.release` explicitly unsupported; .NET owns those views |
| Background jobs | Explicitly unsupported | No start/status/output/cancel/forget or durable job recovery |
| Packaging/lifecycle | Deliberately absent | No signed production integration, boot readiness or rollback replacement |

The host tests additionally reject bad MACs, replayed sequences, malformed JSON,
symlink/out-of-scope paths, oversized frames and truncated/corrupt uploads; they
check bounded output, offsets and conditional replacement under address and
undefined-behavior sanitizers. They do not establish production-grade C memory
safety or complete .NET error-semantic parity. Arbitrary binary app-command output,
long-duration soak/failure recovery and the wider filesystem policy remain unqualified.

The first two smoke attempts stopped before samples: QN90A exposes
`json_object_is_type` but lacks the usual public `json_object_get_type`, and the SDK
staging directory has symlinked ancestors. The implementation now uses the common
JSON API and separates SDK token staging from canonical transfer storage. Failed
attempts were inspected and cleaned before retrying under fresh experiment IDs.

**Recommendation:** the footprint and startup improvements justify continuing a
native implementation if those costs matter, but this prototype is not a drop-in
replacement. Keep .NET deployed until complete launcher lifecycle, acquisition, recovery,
long-running behavior and failure-path parity are implemented and tested. The
original measurements above predate the new job supervisor and helper management;
they must not be presented as measurements of the extended worker.
The measured steady transfer gains alone do not require switching workers.

No TV was rebooted or had its installed package, SDK host setting, enrollment or
boot configuration changed. Original worker IDs and boot IDs were unchanged at
completion. Helpers, benchmark jobs and owned test files were removed; original
execution mounts and protected-file hashes were verified. Reboot behavior was not
tested. Raw logs, credentials and copied system libraries remain private.
