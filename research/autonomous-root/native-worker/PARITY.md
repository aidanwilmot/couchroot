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
