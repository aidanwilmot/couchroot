# Production files and retained job compatibility

This phase implements the file-access and retained-record portions of the
[migration plan](MIGRATION.md), with a [machine-readable contract](../../../tests/worker-parity/contract.json)
and [differential harness](../../../tests/worker-parity/README.md). It does not
select native in the installed service, remove .NET, or remove the prototype's
bounded lifetime. A subsequent local lifetime change adds the explicit
`--production` mode described in the README; it has not been deployed or
qualified on either TV. Default experiments keep their original narrow file policy.

## Opt-in production file policy

Append `--production-files` to the existing worker arguments to enable the policy.
The supplied private scope remains the worker's runtime/state root; its `.jobs`
directory must be stable across replacement workers if records are to survive.
A future deployment should select a dedicated persistent native state directory,
not reuse the managed job directory. Scope selection and migration installation
belong to the later service-selection transaction.

The policy accepts canonical absolute paths, traverses parents using directory
descriptors without following symlinks, and opens regular files without following
the final component. Downloads can read disk files beyond the experiment scope,
but refuse `/proc`, `/sys`, `/dev`, and non-regular files. Uploads permit the
worker's own runtime/state scope, its token's staging directory, the SDK staging
root and `/opt/couchroot-agent/files`. Only the fixed managed files directory may
be created; caller-selected parent directories must exist. The native scope's
`.jobs` and `.views` metadata remain inaccessible through file operations.

Uploads retain their parent descriptor until commit/close. Commit revalidates
that the pathname still resolves to that parent. If it was moved, replaced or
changed into a symlink, publication fails and cleanup removes the temporary file
through the original descriptor. This is not a filesystem-wide compare-and-swap;
independent writers must still be quiesced. A parent can change after validation,
so no stronger concurrency guarantee is claimed. Create-only and current-hash
replacement retain the existing publication semantics.

Production traversal needs two spare descriptors at its peak, plus the monitor's
reserved slot. Persistent upload parent descriptors are included in subsequent
admission scans. Host tests exercise the rejecting and admitting thresholds and
verify unchanged descriptor sets after close. Helper sources use the same parent
traversal and, in this mode, must be managed uploads. The ordinary launcher still
comes from its separately supplied, digest-bound source within the private scope.

Two response discrepancies were corrected: `file.open` initially returns offset
zero, while download `file.status` returns file length and a null expected digest,
matching managed behavior. Job admission now rejects whitespace-only commands,
including the Unicode whitespace accepted by managed `IsNullOrWhiteSpace`.

## Retained records and offline migration

`python3 -m tvsetup.native_job_migration` imports a quiesced managed snapshot into
a private native `.jobs` directory. It has no TV transport and never signals a
process or launches a recorded command. Do not point it at a live managed job
directory: the old worker does not honor the native lock. The caller must stop
mutations, establish a quiesced snapshot and arrange rollback before a real
service transition. Those production transitions are not performed in this phase.

Example using canonical, private, local snapshot directories:

```sh
python3 -m tvsetup.native_job_migration \
  --source /absolute/private/managed-snapshot \
  --target /absolute/private/native-state/.jobs --offline-snapshot
```

Both directories must exist and belong to the current effective user with private
permissions. Records must be bounded, singly linked regular files with matching
IDs, valid metadata and unique JSON fields. The tool refuses malformed records,
partial `.next` files, unresolved guardian/intent state and a combined count over
64. An existing identical record is retained; a differing ID collision stops the
transaction without overwriting either version.

The source is unchanged. A durable `.import-pending` manifest binds source hashes
and direction before records are published. Each new record is synced through a
scratch file and renamed; final manifest publication commits the transaction.
Native startup refuses a destination with `.import-pending`. Retry the same command
with the same source bytes to resume a completed pending manifest and partial
record publication. A torn/unreadable pending manifest, unexpected file or changed
source is preserved for inspection rather than guessed or deleted. Do not remove
the pending marker merely to make a worker start.

Records are copied byte-for-byte, with no invented native ownership. The guardian
therefore does not claim it reaped the old managed job. Same-boot running/unknown
records remain unknown; old-boot nonterminal records report interrupted. Completed
results remain available without logs. Imported IDs participate in duplicate-start
refusal and the 64-record limit. Native saved-job cancellation remains refused.
Unknown same-boot records cannot be forgotten through the API. This is an explicit
compatibility difference, not a reason to restore saved-PID signalling.

For rollback, export a quiesced native snapshot to a fresh private managed rollback
snapshot with `--direction rollback --offline-snapshot`. This preserves native-created
IDs/outcomes as well as imported records; the original managed archive stays
unchanged. Install that verified snapshot only within the later rollback transaction,
never by replacing a running worker's files. In-memory output cannot be migrated.
Forgotten legacy records may reappear if an older archive is restored; use the
exported current snapshot when selecting rollback data. Changed-ID collisions
require inspection, not last-writer-wins merging.

## Qualification and remaining gates

Local verification comprises 49 existing native ASAN/UBSAN tests, six new native
production-policy/record tests, six differential groups and ten offline migration
tests. The repository runner passes 236 tests and skips the 61 Linux native and
differential tests that run separately. The existing loopback protocol tests pass.

A short acceptance run on QN90A and S90D used the ordinary ARM worker, not the
fault-test build. It exercised nested uploads and managed helper sources, reads
outside the old scope, path refusals, app-user helper identity/release, synthetic
legacy unknown records across sidecar restart, duplicate/cancel/forget refusal,
mixed JSON/binary upload and owned cleanup. No deployed managed job records were
read, imported or changed. Both original .NET identities and boot IDs were preserved.
See [phase results](parity-results.json) for build hashes and evidence limitations.

This closes the implemented file policy and offline retained-record compatibility
work, not the entire migration. A live state-installation/rollback transaction,
production packaging and capability advertisement, HTTPS worker selection,
production lifetime, acquisition/recovery ports, signal-policy decision and
cross-boot qualification remain the subsequent gates in `MIGRATION.md`. Do not
claim full .NET replacement readiness from these tests.

## Subsequent local lifetime validation — 2026-10-14

The explicit `--production` mode removes the worker and guardian lifetime alarms,
retains production file policy, and separates an idle connection from an active
frame. It does not select native in the service. Default and `--production-files`
experiments remain bounded. A conflicting experiment-lifetime environment value
is rejected, and status reports the mode and zero seconds for no lifetime expiry.

All 61 existing native/file/differential tests passed with ASAN/UBSAN. Six distinct
lifetime checks passed across ordinary host and sanitizer builds: production
status and job deadlines, conflicting configuration refusal, buffered requests,
default bounded mode with 32 seconds of idle time, 315 seconds of uninterrupted
production idle time with a running job, and partial-frame expiry with owned-job
cleanup. The two extended checks ran in the ordinary host build without fault
controls. Both old lifetime thresholds (300 and 310 seconds) were crossed without
replacing the worker or guardian. ARMv7 worker/controller and fault-test builds
compiled successfully. These are local tests, not TV qualification.

A 24-hour job deadline was accepted and the job explicitly cancelled; no claim is
made that a job completed 24 hours of execution. Slow-storage progress, integrated
service selection, both-TV lifetime/endurance checks and power lifecycle remain
open. No TV was contacted, restarted or switched during this follow-up.

## Subsequent local storage-progress validation — 2026-10-14

Successful request-side storage reads, writes, digest blocks and flushes refresh
the main-thread progress lease. Transfers and helper/launcher copy paths use
these notifications; the monitor and guardian never refresh the main lease on
behalf of blocked I/O. Failed operations, EOF and repeated EINTR do not count as
progress. A single blocked syscall still expires under the existing watchdog.
Hashing stops at the initial regular-file size (at most 2 GiB) and refuses changed
sizes, rather than following a growing file indefinitely. This does not detect
all same-size external writes or provide a filesystem snapshot; writers still
must be quiesced. The contract records the size-change behavior explicitly.

The final ordinary host build passed seven isolated storage tests in 197.639
seconds: slow hashing and byte-range download, partial slow upload followed by
exact publication, blocked hash read, blocked flush without publication,
repeated EINTR, file growth/shrink during hashing, and sparse 2 GiB hashing plus
boundary range reads and oversize refusal. Slow successful operations crossed
30 seconds; stalled cases terminated the worker and its owned job within the
38-second test bound. The delay fixture is a separate host-only shared library,
not compiled into any TV artifact.

The final source also passed all 61 existing native/file/differential tests under
ASAN/UBSAN and ordinary/fault-test ARMv7 builds. Four short lifetime checks passed
during this change; the earlier 315-second lifetime qualification was not repeated.
No TV was contacted or modified, and .NET remains deployed.

This closes the worker-side file progress gap, not integrated storage qualification.
The service's 30-second OP response budget, client deadlines, job-record flush
latency under its mutex, startup before guardian activation, actual TV storage,
Smack helper staging and long-running endurance remain separate integration and
qualification work. No request is automatically replayed after a timeout.

## Subsequent local transport-deadline validation — 2026-10-14

The service and bundled client now use fixed, operation-specific response budgets:
120 seconds for open/commit/helper preparation, 60 seconds for file chunks, and
30 seconds otherwise. The API adds five seconds of transport margin and the client
ten seconds. New requests reset the HTTPS inactivity budget so reused connections
do not inherit a previous operation's allowance. Command/job execution deadlines,
body admission and keep-alive limits are unchanged. A request field cannot extend
its response budget. The operation journal keeps its existing admission envelope;
response budgets are not job execution timeouts.

Expiry explicitly reports an unknown outcome and closes the worker connection.
A submitted mutation remains in the journal, and replay of its request ID is
rejected before another worker submission. Confirmed responses clear their timer.
Both JavaScript and Python budgets are checked against the parity contract.

Four new Node tests passed, including a real 42-second request through the pinned
Python client, mutual-TLS API and authenticated loopback protocol server. That
check uses a scripted peer, not a native worker or TV, and crosses the old 30/35/40
second wire/API/client limits. Twenty existing service/protocol tests also passed,
including additional unknown-operation journal/no-replay assertions. Repository
Python discovery passed 238 tests with 74 native fixture tests skipped. The client
reuse test confirms per-operation socket budgets of 130, 70 and 40 seconds on the
same pinned connection. No TV was contacted, rebooted or switched.

These budgets are candidate defaults, not throughput guarantees. Qualification
must still run the ordinary packaged native worker through this service on both
TVs, reconcile observed operation tails, and verify deployment and rollback with
retained state. Older separately copied clients need updating to use the longer
budgets. Native packaging, implementation selection and later lifecycle gates in
`MIGRATION.md` remain open.

## Subsequent ordinary candidate packaging — 2026-10-14

The package preparer accepts `--native-candidate`. It builds the ordinary native
worker and launcher, copies them and their manifest into the existing package,
and retains both managed payloads. Managed selection and disabled provisioning
remain unchanged. No signing, package installation, selection change or device
access was performed during this follow-up.

The build snapshots source inputs, pins the compiler image by immutable local
identity, runs without networking, checks two identical builds, and verifies the
published files against the measured digests. The candidate manifest records
source/artifact hashes, compiler version/image identity, ARM ABI, interpreter,
ELF dependencies and runtime-loaded library alternatives. Fault-test/controller
outputs are excluded. Nonempty output directories, symlink artifacts, unexpected
outputs, mismatched repeated builds, incompatible ABI/dependencies and recognized
test-control markers are refused without publishing a manifest.

Actual repeated ARM builds produced:

| Artifact | Bytes | Highest required GLIBC | SHA-256 |
| --- | ---: | --- | --- |
| native-worker | 107568 | 2.28 | `ab3f37813ca3254303f0be015d12c2bec077878114c093684615846e886fd28c` |
| native-app-launcher | 13296 | 2.4 | `4ba756c8b725ba2e375ca02608c9ca7579f6d6275c4ed96348ba93bf5b8a6d55` |

The worker's requirement includes `fcntl64@GLIBC_2.28`; it is not appropriate to
apply the launcher's 2.17 ceiling to that artifact. Existing native-service
research records libc 2.30 on the TVs, but candidate qualification must still
verify the currently deployed libraries on each device. Both artifacts use
`/lib/ld-linux.so.3`; the worker additionally needs libc, libdl and libpthread,
plus the runtime json-c/crypto alternatives recorded in its manifest.

Five new build/package tests passed. Repository Python discovery passed 243 tests
with 74 native fixture tests skipped. The package-boundary fixture verifies both
managed DLLs, candidate hashes in the package manifest and unchanged managed
selection. Shell syntax and CLI-help checks passed. This evidence qualifies local
artifact preparation, not an installed package or a native-only agent build.
Service selection, state migration and rollback remain open.

## Subsequent service candidate validation — 2026-10-14

The service now validates optional native candidate package contents at creation
and before an acquisition attempt. It checks the package index's native-manifest
digest, exact candidate schema, supported profile declaration, managed selection,
unqualified status, repeated-build declaration, source/toolchain metadata, artifact
set, declared ABI/dependency limits and runtime-library alternatives. Bounded
no-follow reads verify final artifact size/digests and ELF headers, and refuse
known test-control markers. All referenced artifact names are fixed; manifest
source paths are metadata and are never opened by this validator.

`selected_implementation` remains `managed`. Candidate diagnostics distinguish
absent, invalid and verified packages and include when they were checked. An
invalid candidate has a bounded reason code and does not suppress managed launch.
Successful candidate verification does not set `worker_ready`, select native or
mark the device qualified. A later staging/selection transaction must freshly
validate its expected manifest digest and copied bytes.

Seven new Node tests passed, covering both profile declarations, legacy absence,
invalid metadata, digest failures, incomplete packages, symlinks, oversized input,
wrong ELF headers, test-control markers, refresh-before-launch, and the actual
ordinary binaries built in the preceding step. Fourteen candidate/service tests
passed in total; sixteen additional protocol/deadline tests passed, with the
previously completed 42-second test skipped in this run. Five candidate-builder
Python tests passed. No TV access or deployment occurred.

This is package consistency validation within the existing signed-package trust
boundary. It does not independently rebuild source, rerun readelf, prove compiler
provenance or probe device libraries. ABI dependency/version declarations are
bound to the package's artifact hashes; live compatibility still requires device
qualification. Journaled implementation selection, retained-state installation,
rollback, and integrated native readiness remain open.
