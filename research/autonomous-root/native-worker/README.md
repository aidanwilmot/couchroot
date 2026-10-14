# Native worker experiment

This C prototype is a measurement sidecar, **not a production replacement**. It
is not referenced by the package builder, service selection or boot configuration.
The installed .NET worker remains active throughout a comparison. No SDK changes,
service replacement, root reacquisition or TV reboot is needed.

The prototype uses the existing HMAC protocol with strict sequence ordering,
bounded binary chunks and structured failure responses. It implements status,
root commands, bounded output and process-group timeouts, app commands through an
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
directory, locked to one native worker. Initial intents are written and synced to
an exclusive temporary file, then published with a non-replacing hard link and
directory fsync before a child can execute. Failed writes cannot publish partial
initial records. Initial temporary names include the generated worker identity.
After same-boot ownership reconciliation, an unpublished intent becomes an
interrupted record with unknown exit status and `launch_started=false`; its ID
stays reserved until explicitly forgotten. Recovery resumes interrupted repair
writes and preserves existing final records and foreign-owner intents. Invalid
owned metadata fails closed. Legacy orphan `.json.next` files without a final
record lack this ownership proof and remain preserved for inspection.
Terminal-result save failures remain visible as
`persistence_failed`; the supervisor retries the known result at most once per
second per retained job, without rerunning commands. Restarted workers report saved outcomes
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
After descendants are drained, metadata-save failures no longer skip execution-view
and cgroup cleanup: each cleanup is attempted, and the journal remains for a later
metadata reconciliation.
Worker SIGKILL/crashes are recovered by that guardian. Guardian loss terminates
its traced descendants; the next launch can reconcile a same-boot ownership journal
with durable resource bindings before starting a new worker. Ambiguous state remains blocked. There is no durable log recovery. The
controller and deployed .NET worker retain their original namespace.

Missing parity still includes autonomous root acquisition and production
packaging/recovery integration and the broader production file
access policy. Legacy READFILE/WRITEFILE and JSON file.write are omitted. Unsupported
operations fail explicitly; there is no automatic fallback or replay. The build also produces the existing native `app-launcher` source as a separate
binary. The worker accepts its source path inside the canonical file scope and an
expected SHA-256; it validates ARM ELF32, stages a private root-only copy, applies
Smack and a read-only bind mount, and verifies the staged digest before use. It no
longer accepts a borrowed .NET execution view. Root acquisition and transport
service integration are still borrowed, so startup is not complete service startup. The worker defaults to a five-minute experiment lifetime. An explicit
`COUCHROOT_NATIVE_LIFETIME_SECONDS` value from 300 to 86400 permits longer bounded
experiments; jobs cannot outlive that worker. Disconnect,
SIGTERM and graceful shutdown clean up owned active jobs and helper views.

The worker executable starts a small guardian before the protocol worker and its
threads. The guardian is a Linux child subreaper and holds the scope lock, runtime
mount namespace and durable ownership journal. After a worker dies, it kills and
reaps its actual children, including adopted detached descendants, before changing
its own nonterminal job records to `interrupted` and deleting owned execution views.
It never signals a PID from a saved job file. Completed records remain unchanged;
crash records have an unknown exit code and unavailable in-memory output. A new
worker invocation reads those records and refuses duplicate starts. It does not
automatically restart or replay commands. The protocol worker is non-dumpable.
Before allowing that child to create threads, the guardian attaches with
`PTRACE_SEIZE` and follows clone, fork, vfork and exec events with
`PTRACE_O_EXITKILL`. This covers the owned worker, command descendants and their
threads. SIGSEGV, SIGBUS, SIGILL, SIGFPE and SIGABRT delivery stops terminate the
faulting thread group before the TV's default crash collector. A command fault
does not kill the healthy worker: its parent receives the actual SIGKILL exit
status, 137. Native status exposes `command_fault_policy` and a bounded
`command_faults` history of the latest 64 events: sequence, process/thread IDs,
original signal and signal code, actual termination signal, action and monotonic
time. The guardian writes a small shared-memory ring; the worker and its children
have read-only mappings. Overwrites, concurrent snapshot omissions and counter
saturation are explicit. These are session diagnostics, not durable per-job
metadata, and reset when a new worker starts. PIDs in these historical events
must never be used as authority to signal a process. Supervision intentionally
prevents handlers for these signals from running in commands; software that uses them for its own recovery
needs a separate compatibility decision before production adoption. The original signal is saved separately as
`worker_fault_signal`; interrupted jobs still have an unknown exit code. Normal
signals are forwarded, group stops remain stopped for the heartbeat watchdog,
and unavailable tracing fails startup closed. No process is selected from a
saved PID, and no system-wide crash setting is changed. See the Linux
[ptrace interface](https://man7.org/linux/man-pages/man2/ptrace.2.html) for the
signal-delivery and clone-stop semantics used here.

The guardian also uses a heartbeat watchdog and an isolated freezer cgroup for
an unresponsive worker. The controller waits for recovery and does not force-kill
a guardian merely because its wait expires. The pulse thread also checks separate
30-second progress leases for an active protocol request and the job monitor.
Foreground command polling refreshes the request lease; waiting for a new protocol
frame is idle and remains bounded by socket/lifetime limits. File operations and
blocked writes must complete within the progress grace. The job monitor wakes
periodically even with an empty queue. A stalled lease triggers the same isolated
cleanup, recording `active-request-stalled` or `job-monitor-stalled`; a missing
pulse records `heartbeat-lost`. This does not supervise a stalled guardian.

Each native run exclusively creates `/sys/fs/cgroup/freezer/couchroot-native-ID`.
Only the protocol worker joins it before spawning threads or commands; its root
and app descendants inherit membership. The guardian and deployed .NET processes
stay outside. A dedicated worker thread sends a heartbeat every 100 ms. After a
one-second heartbeat gap, the guardian freezes only that group, waits until its
members cannot fork, and queues SIGKILL to every member. Before waiting for full
freezing, it kills its own unreaped protocol child and moves that dying process
back to the parent freezer group; this avoids a multithreaded exit deadlock on
older kernels. Descendants stay in the private leaf. It then thaws the group
so older kernels can finish process exit. Once the worker exits, the guardian proves child
ownership with `waitid(..., WNOWAIT)` before killing/reaping adopted descendants.
It removes the empty cgroup along with owned runtime views. It never changes the
state of an existing system cgroup. Host tests bypass unavailable freezer support;
actual membership, freezing and removal are exercised by the TV acceptance suite.

Failure to finish recovery retains the ownership journal. The next launch retries
only when its ownership checks permit it. Storage corruption, unbound partial resource creation,
legacy or different-boot journals and uninterruptible processes remain
fail-closed/manual-inspection cases. This prototype does not
replace the deployed service's root acquisition, enrollment or restart machinery.

`accept.c` exercises the native job/helper lifecycle on the TV via a private
loopback controller. It checks an over-25-second job, simultaneous foreground and
background execution, app-user helper execution, read-only mounts, output limits,
cancellation, retention, disconnect cleanup and saved status after a native restart.
These checks do not restart the production worker or TV. Set
`COUCHROOT_NATIVE_SOAK_SECONDS` to 60..3600 for an additional bounded run. It
repeatedly uploads/stages/releases a helper, runs root and app jobs, verifies app
identity, forgets records and checks stable worker/guardian descriptor counts,
worker thread counts and mount counts. It reports RSS ranges as observations,
not a full PSS/swap or CPU comparison. The controller grants the worker an explicit
soak-duration-plus-300-second lifetime and keeps its own deadline bounded.

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
`tests/native_worker_test.py`. The normal ARM build never enables this test mode. Guardian tracing tests require
native Linux execution and ptrace permission (for example, `--cap-add SYS_PTRACE`
in a dedicated container); an emulated x86 userspace is not a substitute.
`worker-fault-test` and `accept-fault-test` are separately named builds with
`NATIVE_WORKER_FAULT_TEST`. Only that worker build contains the authenticated
`test.fault` operation, which writes a PROT_NONE page on the main thread or a new
worker thread. That binary also supports isolated helper memory faults and a
`test.stall` operation: it deliberately stops a selected progress path and ages
its lease beyond the grace while leaving the pulse thread alive. Thus the test
checks stale-progress detection and cleanup without waiting 30 seconds each time.
The acceptance soak separately checks a healthy 32-second foreground command.
Do not use this fault-injection build as a production worker.
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

## Guardian loss and stale journals

The guardian alone holds the scope lock. Before releasing its traced worker it
persists a schema-4 journal with namespace, runtime-reserved, runtime,
freezer-reserved, contained and ready phases.
Each checkpoint binds the boot, scope and mount namespace, plus runtime and
freezer inodes as those resources are created. Before each resource is created,
a reservation binds its parent and generated worker-specific name. An unbound
runtime reservation must be empty; an unbound freezer reservation must have no
processes or tasks and is never thawed. Populated, busy or mismatched reservations
remain blocked. Runtime ownership is persisted before launcher content is copied.
Empty managed helper parents are removed only after their named inode matches the
opened directory; nonempty shared parents are left alone.

The initial journal is written to `guardian.initial`, synced, renamed and directory
synced before any runtime resources can be created. An abandoned initial temporary
can be removed under the scope lock only when neither a published nor successor
journal exists and its ownership, type, links, mode and size are valid. Conflicting
or unsafe initial files remain blocked. Updates also use atomic rename and directory fsync.
A complete `guardian.next` can recover an interrupted rename only when it advances
the same owner's phase by exactly one step and preserves all existing identity
and inode bindings. Foreign or non-advancing complete temporaries block startup. A truncated update
can be discarded only after the committed base independently proves resource
cleanup through its bindings and empty-only reservations. Schema-3 contained
checkpoints have sufficient bindings for this too; ambiguous older checkpoints
and a temporary after ready remain blocked. Fully prepared schema-2 journals and
supported schema-3 checkpoints remain readable.

An interrupted launcher copy or mount can be swept using the durable runtime
binding after its old execution views disappear. Resource-creation-before-binding
windows now have empty-only reservations. A malformed published journal still
requires inspection, and cross-boot recovery remains unqualified. Ordinary
journal-write errors clean only this startup's owned temporary after owned runtime
cleanup succeeds; abrupt exits leave recoverable checkpoints. Startup fault injection exists
only in the separate fault-test binary; the ordinary binary ignores its test
environment variable.

On a later launch, reconciliation runs under the exclusive scope lock in a
bounded child process, before staging a new launcher or accepting commands. It
refuses a still-present guardian identity, mismatched directory/device bindings,
legacy/different-boot journals, symlinks, hard-linked or permissive journals,
unexpected mounts, inaccessible namespace evidence and retained namespace pins.
Saved PIDs are inspected only: reconciliation never signals them. Namespace inode
numbers can be reused on these kernels. If a live process has the saved number,
recovery checks its mount table for the old worker's owned execution views before
treating it as a retained old namespace. Both mount roots and targets are checked,
including moved bind views. Descriptor-only matches, unclassifiable pins and
unreadable evidence remain conservative refusals. No unrelated process is signaled
or moved into another namespace.

Guardian death applies `PTRACE_O_EXITKILL` to the worker and its traced descendants.
If the guardian died while its private group was frozen, recovery thaws only the
journal-bound cgroup so pending kills can finish on older kernels. It waits for
both process and task membership to empty, then checks process namespace handles,
open namespace descriptors and namespace bind mounts before removing backing
files. It never enters or detaches a retained namespace. The scan is bounded to
256 distinct visible mount namespaces and recovery sets a 15-second alarm.
Older nsfs mount metadata can omit a namespace identity; those ambiguous pins
block reconciliation conservatively. Compare the upstream
[Linux 4.1 nsfs implementation](https://github.com/torvalds/linux/blob/v4.1/fs/nsfs.c)
with [Linux 4.9's namespace mount-path reporting](https://github.com/torvalds/linux/blob/v4.9/fs/nsfs.c).

Once absence and ownership are established, recovery marks only that worker's
nonterminal jobs `interrupted`, with unknown exit codes and
`recovery: stale-guardian-reconciled`. Completed results and foreign records stay
unchanged. Strictly recognized owned runtime files and the empty cgroup are
removed before deleting the journal. Missing resources permit an interrupted
cleanup to resume; mismatched existing resources do not. A new native worker then
stages its own launcher and reports `stale_guardian_reconciled: true`. Duplicate
job IDs still cannot replay commands. This is recovery on the next explicit
launch, not a new service restart mechanism or a replacement for .NET.

## Storage-failure and namespace-reuse validation — 2026-10-13

The worker in `f9ae182` passed 43 distinct extended checks (47 rows) on each TV.
A private 2 MiB tmpfs reached actual ENOSPC without filling TV storage. Failed
initial intents neither published partial records nor released a command. A job
that completed while full exposed `persistence_failed`, then persisted its original
exit code after space returned; an external execution counter remained exactly
one. A read-only remount of only this test filesystem rejected a new job; restored
writes permitted fresh app-user execution. A worker crash while full removed its
runtime views, retained the journal and reconciled interrupted jobs after space
returned. Final verification confirmed no prototype freezer groups remained.
The immediate freezer-absence assertion was subsequently tightened to use its
absolute cgroup path; its additional validation is part of the pending endurance run.

An earlier QN90A run observed a saved namespace inode reused by a newer Samsung
framework process. Its mount table had no owned native execution views. Corrected
reconciliation recovered the old resources while preserving that unrelated process.
The suite also simulates this case on both TVs and retains its namespace descriptor
and bind-pin refusal tests. Earlier fixture failures and their verified cleanup
are recorded in [storage-recovery-results.json](storage-recovery-results.json).

All 35 native host tests passed under AddressSanitizer and
UndefinedBehaviorSanitizer on Linux ARM64; the repository suite passed 226 tests
with 35 native tests skipped by that runner. The final TV runs exited zero, showed
no observed crash-collector waits or worker executable dumps, and passed original
.NET worker, boot, protected-file, mount and cgroup preservation checks. No TV was
rebooted. One-hour endurance tests have started separately; they are not yet
qualified results. Production integration and the other remaining work below
remain open.

## Startup-checkpoint validation — 2026-10-13

Revision `1f5d770` passed 38 distinct extended acceptance checks (42 rows) on
both QN90A and S90D. Eleven new scenarios exit abruptly before opening a command
channel: namespace and runtime checkpoints; empty, first-write and fully copied
launcher files; staged launcher; contained and ready checkpoints; and each of the
three complete journal updates before rename. The next launch recovered each
case, removed the old runtime/freezer resources and successfully ran an app-user
job. The ordinary build excludes the startup fault-control environment variable.

All 34 native host tests passed under AddressSanitizer and
UndefinedBehaviorSanitizer on Linux ARM64, including schema-2 compatibility and
rejection of mismatched successor identities and bindings. The repository suite
passed 226 tests with 34 native tests skipped by that runner. The native source
manifest matches the on-TV builds. Both observed kernel windows had zero
crash-collector wait or worker executable dump lines. Final cleanup verified the
original .NET workers, boot identities, protected files, mounts and cgroup
memberships unchanged, with all owned test resources removed. Neither TV was
rebooted. Sanitized evidence is in
[startup-recovery-results.json](startup-recovery-results.json).

This covers durable checkpoints and complete interrupted journal updates.
Creation-before-binding windows and truncated journals still require inspection;
production integration, storage-failure qualification, longer endurance runs,
compatibility decisions and updated whole-process performance measurements remain
open. Cross-boot testing remains deferred under the no-reboot constraint.

## Guardian-loss validation — 2026-10-13

The worker and acceptance harness from `5a4f69c` passed on QN90A and S90D.
Each TV completed the normal suite with 22 distinct checks (25 result rows) and
the extended memory-fault/progress-watchdog suite with 27 distinct checks
(31 result rows), all passing with exit code zero. Repeated rows exercise both
running and frozen guardian-loss scenarios. Sanitized build hashes, check names
and cleanup evidence are in [guardian-loss-results.json](guardian-loss-results.json).

The controller killed its own guardian child while root and app jobs were active,
including a detached delayed writer. EXITKILL prevented that writer from running;
the next launch reconciled interrupted records without replay and preserved the
completed exit-7 record. The frozen case verified that thawing the bound private
freezer lets pending kills finish. Fresh app-user execution then succeeded.

Recovery refused retained namespace descriptors and namespace bind mounts,
wrong schema, unprepared state, different boot, mismatched scope/runtime/freezer
bindings and a still-live owner identity. A simulated reused PID referenced the
live controller with a different process start time: reconciliation succeeded
without signaling it. Host tests additionally cover unsafe journal permissions,
hard links, symlinks, a leftover temporary journal, completed/foreign record
preservation and retry after interrupted resource cleanup.

All 31 native host tests passed under AddressSanitizer and
UndefinedBehaviorSanitizer on Linux ARM64. The repository suite passed 226 tests
with those 31 native tests skipped by its ordinary runner. Neither device's
observed kernel window contained a crash-collector wait or worker executable dump.
Both final cleanup checks verified unchanged deployed .NET worker/PID, boot,
launcher/protected-file hashes, original execution mounts and cgroup membership;
owned test files, helpers and prototype freezer groups were removed. No TV was
rebooted, and no installed package, enrollment, SDK or boot configuration changed.

These tests qualify fully prepared, same-boot schema-2 reconciliation only.
Recovery requires a subsequent explicit launch; production restart integration,
partial-preparation and cross-boot recovery remain open. This is not a new CPU,
memory or startup comparison, and .NET remains the deployed implementation.

## Descendant faults, progress watchdogs and soak — 2026-10-13

Revision `76a9649` passed **17 normal acceptance checks and 23 distinct extended
checks on each TV**, including a ten-minute soak. All controller exits were zero.
[progress-results.json](progress-results.json) records the build hashes, individual
recovery observations, soak measurements and final invariants. Local validation
passed 226 repository tests plus 27 native tests under address/undefined-behavior
sanitizers on native ARM64 Linux.

Root and app shell faults returned actual exit 137 while the worker remained
responsive. Independently staged helpers deliberately faulted both their main
thread and a newly created thread under root and UID 5001 / Smack `User` profiles.
Every helper fault completed within the two-second acceptance bound; their native
views released normally. Original signal details remain diagnostic output rather
than per-job metadata.

The extended suite stopped active-request and job-monitor progress independently
while the heartbeat thread remained alive. It checked the saved watchdog reason,
interrupted records with unknown exit codes, descendant containment, normal mount
cleanup, duplicate-start rejection and app execution after a fresh native launch.
These tests deliberately age a lease beyond its 30-second grace: their 142–214 ms
observations measure detection/cleanup after expiry, not the production grace.
A healthy 32-second foreground command completed on both TVs without a watchdog
termination; idle protocol connections also remained usable.

| Ten-minute soak observation | QN90A | S90D |
| --- | ---: | ---: |
| Elapsed workload loop | 605.4 s | 601.1 s |
| Transfer/stage/job/release cycles | 57 | 57 |
| Worker RSS range | 860–916 KiB | 892–1,064 KiB |
| Maximum observed guardian RSS | 1,092 KiB | 1,152 KiB |
| Worker threads | 3, stable | 3, stable |

Worker and guardian descriptor counts and worker mount counts remained stable.
Each cycle verified app identity, completed root/app jobs, forgot their records
and released its helper normally. These are bounded workload observations, not
proof against all leaks or a fresh PSS/swap/CPU comparison with .NET.

Both the normal and extended suites cleaned up through the regular helper APIs;
no lazy unmount or detach/rebind repair was needed. Captured kernel windows had
no crash-collector messages. All experiment files, jobs, native runtime views and
private freezer groups were removed. The original .NET process/worker and boot
identities, launcher hashes, protected files, cgroup membership and execution
mount sets were unchanged. Neither TV was rebooted; .NET remains deployed.

## Remaining production work

- Validate the schema-4 initial-journal, resource-reservation and partial-update
  recovery and owner-tagged orphan job-intent recovery on both TVs. All 46 native
  sanitizer host tests and ARM builds pass; the repository suite passes 226 tests
  with the 46 native tests skipped by that runner. The expanded device suite is
  prepared while the prior build's endurance run continues.
  Cross-boot, reboot and power-loss recovery remain unqualified.
- Integrate acquisition, enrollment, service selection and rollback through the
  existing production machinery; the experiment still borrows those services.
- Qualify resource exhaustion, further storage failures and substantially longer
  runs. Host tests now cover the 64-record saved-job limit, explicit-forget
  capacity recovery, and launch-pipe descriptor exhaustion. The latter preserves
  the unlaunched intent, refuses reuse, keeps the worker responsive and reconciles
  the record as interrupted after restart. Matching device probes are now included
  in the acceptance controller but remain unqualified until both TVs pass. The
  descriptor probe uses `prlimit64` on its live authenticated native child only;
  the controller, guardian and deployed fallback retain their original limits. Preserve bounded, in-memory output as the public contract, matching the
  deployed .NET implementation; durable output is not required for parity.
  Job outcomes remain durable metadata and must recover after transient failures.
- Decide command signal-handler compatibility. The current strict policy is now
  explicit in native status. Original command-fault diagnostics are exposed
  separately from actual termination status and pass host tests; the matching
  device probe remains pending.
- Reconcile the narrower file policy and omitted legacy operations with the
  desired public API, then repeat whole-process CPU/memory/startup comparisons.
  The guardian's polling and the job monitor's periodic wakeups need measurement.

## Historical crash delay and test-mount cleanup fix — 2026-10-13

Revision `6b41b6d` passed the normal **16-group suite and extended 18-group suite
on each TV**. The extended suite deliberately writes an inaccessible memory page
on both the protocol thread and a newly created worker thread. All fault recoveries
finished within the suite's two-second limit, removed detached descendants and
owned execution views, preserved interrupted records without replay, and allowed
app-user execution after restart. Local validation passed 226 repository tests
and 24 native tests under address/undefined-behavior sanitizers on native ARM64 Linux.
[crash-delay-results.json](crash-delay-results.json) retains the build identities,
individual observations and cleanup checks.

| Recovery observation | QN90A | S90D |
| --- | ---: | ---: |
| Previous SIGSEGV path | 20,573 ms | 20,890 ms |
| SIGSEGV, normal build | 192 ms | 101 ms |
| SIGSEGV, extended test build | 172 ms | 874 ms |
| Actual main-thread memory fault | 194 ms | 92 ms |
| Actual new-thread memory fault | 215 ms | 103 ms |

These are individual fault-to-guardian-exit observations, not a latency distribution
or a new CPU/memory benchmark. The higher S90D injected-signal sample is retained;
all real-memory-fault samples were 92–215 ms.

The earlier delay was in Samsung's kernel crash collector: kernel logs repeatedly
reported `Extended-Mincore` waiting for `get_coredump_config` for about 20 seconds.
On **both TVs**, isolated probes showed that installing handlers for SIGSEGV,
SIGABRT, SIGBUS and SIGILL returned success but read back as the default disposition.
SIGUSR1 and SIGFPE handlers installed normally. The same result occurred through
libc and direct `rt_sigaction`, with dumpability both disabled and enabled. Removing
SA_RESETHAND and using SA_SIGINFO did not solve it. The guardian now intercepts
worker faults at the kernel signal-delivery stop; it no longer depends on a fatal
handler running in the damaged worker. It does not change global crash settings.

The original non-traced signal probe also reproduced the busy executable mount.
With supervision, **all helper releases succeeded through the normal .NET API on
both TVs in both suites**, including after real memory faults: no lazy unmount,
detach/rebind or manual mount repair was needed. Captured kernel windows contained
no crash-collector wait messages. Avoiding the vendor crash path eliminated both
symptoms in these controlled runs; the exact retained kernel mount reference was
not identified.

All test files, jobs, helper/launcher views and private freezer groups were removed.
Original .NET worker/process and boot identities, launcher hashes, protected files,
cgroup memberships and execution mount sets were verified unchanged. Neither TV
was rebooted; .NET remained deployed. That revision did not trace forked
command/helper processes or qualify their own fatal-fault behavior. Production
root acquisition and service recovery remain outside the prototype.

## Historical independent launcher and crash recovery validation — 2026-10-13

Revision `d6fe00e` passed **16 acceptance groups on each TV**, with zero controller
exit codes. [recovery-results.json](recovery-results.json) records the sanitized
build hashes, checks, timings and cleanup verification. Local validation passed
226 repository tests and 22 native tests under address/undefined-behavior sanitizers.

Both TVs independently staged the uploaded launcher, enforced its digest and
read-only view, and ran helpers as UID 5001 with Smack `User`. The suite retained
the job/helper lifecycle checks and added SIGKILL, SIGSEGV and stopped-worker
recovery. Detached descendants could not create their delayed marker. Restarted
native workers restaged their own launcher, ran app commands, reported interrupted
jobs without invented exit codes, and rejected duplicate starts without replay.
Root and app commands inherited the private freezer group.

| Worker fault | QN90A recovery | S90D recovery |
| --- | ---: | ---: |
| SIGKILL | 162 ms | 81 ms |
| SIGSEGV | 20,573 ms | 20,890 ms |
| SIGSTOP / heartbeat watchdog | 1,078 ms | 1,024 ms |

These are single acceptance observations, from fault injection through guardian
exit, not performance distributions. Fatal-signal teardown still takes roughly
21 seconds; the watchdog contains descendants during that delay. Earlier attempts
exposed delayed teardown and freezer completion/exit interactions. Those failed
runs were inspected and cleaned before retrying. The final sequence excludes only
the already-killed protocol child from freezer completion, terminates the frozen
descendants, and thaws them so old kernels can finish exit.

Native launcher/helper views and private cgroups were removed by the guardian.
On both TVs the outer test worker's **.NET-managed executable view** remained busy
after the crash tests despite no matching process maps or open descriptors. It
required an inspected, experiment-only detach/rebind before registered release.
That harness cleanup limitation remains unresolved; it is not evidence of fully
automatic production recovery. No deployed launcher view was detached or replaced.

Both original .NET workers stayed active with unchanged process/worker and boot
identities, launcher hashes, cgroup memberships, protected files and execution
mount sets. Owned experiment files, jobs, views and freezer groups were removed.
Neither TV was rebooted. Production integration, guardian loss and power/storage
failure recovery remain outside this validation; keep .NET deployed.

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
