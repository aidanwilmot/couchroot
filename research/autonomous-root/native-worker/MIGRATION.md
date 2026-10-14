# Native agent parity and .NET retirement plan

Status: proposed implementation and acceptance plan, 2026-10-14. Reviewed baseline:
`f3f911e`, including runtime changes `43ec7bc` and `f9e6d0c`. The installed .NET
worker remains the deployed fallback. This plan does not authorize a deployment,
reboot, change to device configuration, or removal of the fallback.

## Decision and scope

Continue from the existing native worker and launcher. Keep the JavaScript HTTPS
service, enrolled Python client and shared setup engine; rewriting those would
increase migration scope without removing a .NET dependency. Complete public
behavior parity before selecting native as the default. Retire the managed worker
first, then remove managed acquisition and recovery dependencies, and only then
remove managed artifacts from the current agent distribution.

There are two separately reportable milestones:

1. **Native worker default:** commands, transfers, jobs and helper management run
   natively. Acquisition or recovery may still invoke a managed component. This
   milestone is not a .NET-free agent.
2. **Agent .NET sunset:** installation, acquisition, ordinary operation, reconnect,
   maintenance, upgrade and recovery no longer require project-owned managed code
   on either supported TV. Normal agent builds no longer need a .NET SDK.

Do not remove the TV manufacturer's .NET installation. Other Couchroot components
such as telemetry, saver and setup utilities need their own dependency inventory;
agent sunset is not a claim that the entire repository or TV is .NET-free. Any
managed setup utility required by the agent's supported fresh-install or recovery
path belongs in this migration, even if it lives outside `autonomous-root`.

## Review of Opus's work

The cleanup is useful and should be retained. The source replaces fixed guardian
polling with signal-aware `ppoll`, uses an eventfd to notify the job monitor, and
waits for foreground output or deadlines. Shared functions consolidate job-slot
release, record reads, directory scans, signal-masked thread starts and wait-status
handling. Descriptor admission now covers protocol allocation paths and reserves
one descriptor for the job monitor. The source still identifies itself as a
prototype and is not wired into the production builder or service launcher.

The recorded before/after device measurements show foreground cost per spawned
process falling from 40.9 to 3.4 ms on QN90A and 40.8 to 3.1 ms on S90D. Idle
guardian context switches fell from approximately 100/s to 10/s. These are
microbenchmark observations, not complete startup or end-to-end speedup claims.
The event-wait revision passed the extended suite on both TVs. The admission
revision subsequently passed one-hour endurance and 76 distinct extended checks
on each TV. See [cleanup results](cleanup-results.json) and
[admission results](admission-results.json).

Evidence qualifications that must survive the migration:

- S90D's first endurance attempt was interrupted by power-off/deep suspend. Its
  later successful rerun does not establish standby or resume parity.
- Kernel ring buffers retained only the final several minutes. Absence of errors
  in those tails does not establish absence throughout the hour.
- An earlier S90D recovery took 2,188 ms against a 2,000 ms gate. Later stopped-worker
  results of 1,069 ms and 1,031 ms do not explain that tail. Keep the threshold and
  investigate it under continuous observation.
- Descriptor admission is not a reservation against external limit changes and
  does not qualify guardian exhaustion or system-wide `ENFILE`.
- Tests commonly use the separately compiled fault-test worker. The final ordinary
  production executable needs its own smoke, parity and endurance qualification.

Local revalidation for this review passed all 49 native ASAN/UBSAN tests. The
repository runner discovered 275 tests: 226 passed and 49 native tests were
skipped there because they ran separately. No TV was contacted during this review.
This is a focused source and migration-readiness review, not an exhaustive audit
of every native code path.

This review inspected source changes and recorded evidence; it does not establish
why Opus paused. No motive should be inferred from the absence of an acquisition port.

## Dependency inventory

| Component | Current responsibility | Migration disposition |
| --- | --- | --- |
| `payload/SamsungTvRootAgent.cs`, `AgentOperations.cs`, `AgentJobs.cs`, `AgentHelpers.cs`, `AgentLauncher.cs` | Managed protocol worker, operations and launcher embedding | Replace with native worker after parity gates; retain managed artifacts during rollback window |
| `payload/SamsungTvArchiveRoot.cs` | Firmware-specific acquisition stage invoked by the service | Separate native acquisition adapter workstream; preserve existing supported behavior and profile restrictions |
| `recovery/Program.cs` | Maintenance setting readback, conditional restoration and delayed recovery | Native utility with equivalent validation, timing, drift refusal and result semantics |
| `service/agent.js` | Acquires workers, stages payloads, owns connection generations, readiness, retry budgets and cleanup | Retain JavaScript; introduce explicit implementation selection and manifests |
| `service/main.js`, `api.js`, `policy.js`, `vendor/root-agent.js` | HTTPS lifecycle, enrollment, request journal, operation routing and wire protocol | Retain; test with each worker through the real service |
| `tvsetup/autonomous_root.py`, artifact builder and launcher builder | Per-profile build, packaging, manifests and verification | Add native artifacts and reproducibility checks; remove managed build only at sunset |
| `tvsetup/root.py`, `transport.py`, `operations.py`, trial/recovery callers | Setup access, firmware/runtime guards, controls and maintenance orchestration | Trace the agent's actual call graph; replace any required managed control/bootstrap path before claiming fresh-install independence |
| `scripts/build-native.py`, `check-root-launcher.py`, `check-dependencies.py`, managed harness | Build and validation dependencies | Split agent-only checks from unrelated projects; replace managed oracle with retained fixtures at sunset |
| `native-launcher/app-launcher.c` | App identity, labels, environment and descriptor cleanup | Reuse as an independently versioned, manifest-bound native artifact |

`tvsetup/native_bootstrap.py` and `native_trial.py` concern a telemetry collector
pilot. Their existence does not establish native root-agent acquisition or production
integration. Reuse applicable journal/rollback patterns, not their qualification claims.

## Feature parity matrix

The public contract is [CAPABILITIES.md](../CAPABILITIES.md), enforced jointly by
the HTTPS service, client and managed worker. Preserve observable fields, limits,
error classification and side effects. Additional native diagnostics may be additive.

| Area | Current native coverage | Required closure before default |
| --- | --- | --- |
| Connection and frames | Existing authenticated sequence protocol, EXEC, OP, OPDATA and OPWRITE | Real service conformance: malformed/truncated frames, replay refusal, connection loss, partial bodies and shutdown; no automatic operation replay |
| HTTPS and enrollment | Supplied by unchanged JavaScript service | Native through real enrolled client: request IDs, request journal, certificate continuity, keep-alive, connection limits and serialized mutations |
| Readiness and identity | Boot, uptime, worker and guardian diagnostics | Production capability names; launcher implementation/digest shape; readiness only after validated worker status and required capabilities; acquisition timestamp and stale-generation behavior |
| Root foreground execution | Output, exit code, timeout, truncation and process cleanup | Compare byte output, nonzero exit, empty output, quoting, Unicode, invalid UTF-8, embedded NUL rejection, exact size limits and timeout boundaries through service |
| App execution | Independent native launcher and profile; 100–25,000 ms timeout | Preserve UID/EUID/GID, groups, label, working directory, environment, descriptor inheritance and result conversion; specify invalid UTF-8 replacement behavior |
| Transfers | Eight transfers, 2 GiB files, 1 MiB chunks, ranges, SHA-256, JSON/binary chunks, conditional commit | Expand beyond direct children of one experiment directory; full public read/write path policy and parent traversal; resume metadata and error parity |
| Transfer publication | Create-only link and digest-conditioned rename | Preserve 0600 publication, no unsolicited parent creation, partial-write offset reporting, worker-lifetime IDs and no blind retries; exercise concurrent external writers and document existing limits |
| Jobs | Sixteen retained jobs, 64 records, 1 MiB stream rings, 64 KiB tails, 100 ms–24 h timeouts | Production storage root, legacy record handling, exact state/nullable-exit/output semantics and same-boot/reboot interpretation |
| Cancellation | Current owned jobs and descendants supervised | Resolve explicit difference: managed code permits some saved-process cancellation; native refuses it. Do not silently advertise exact parity |
| Helpers | Digest-checked copy, app execution view, bounded active views and owned cleanup | Production source roots, retained-directory limits, returned metadata and old-helper cleanup policy; no assumption that IDs survive a worker switch |
| Launcher | Independent staging, digest checks and lifecycle recovery | Bind source and digest to package manifest; production readiness; interrupted update and old-version handling |
| Worker lifetime | Bounded experiment default; explicit `--production` removes worker/guardian expiry and separates idle from frame deadlines (local validation only) | Production lifetime separate from request/job deadlines; long-running idle sessions and 24-hour jobs without lifetime expiry |
| Crash recovery | Guardian, progress watchdog, ownership journals and same-boot reconciliation | Production start/stop/reacquisition integration, interrupted upgrade, prior-version journals, standby/resume and cross-boot qualification |
| Command signals | Core-producing signals intercepted, actual termination reported separately | Approve/document changed behavior or implement compatibility mode; managed command signal handlers may behave differently |
| Resource pressure | Protocol descriptor admission; bounded logs and counts | Guardian/startup descriptor budget, concurrent pressure, memory allocation failure, disk full/read-only, process exhaustion and large-file storage stalls |
| Acquisition and maintenance recovery | Borrowed from managed deployment | Native implementation and independent acceptance on each supported firmware; no hidden managed prerequisite |
| Diagnostics | Native status and fault ring | Service-readable bounded start/stop/failure status, selected implementation/version, fallback reason and actionable recovery state; replace managed status-file assumptions |
| Legacy READFILE/WRITEFILE | Omitted | Current public service/client do not expose them. Keep outside the replacement contract unless consumer inventory finds a supported user |

## Ordered implementation work

Phase-one implementation status is recorded in [PARITY.md](PARITY.md): the
contract and differential harness, opt-in production file access and offline
retained-job import/export are implemented. Live state installation and worker
selection are still gated on the later packaging/rollback work below. Local follow-ups
add explicit production lifetime and request-side storage progress. Service and bundled-client response budgets now distinguish storage operations
from ordinary operations, with local HTTPS/wire qualification using a scripted
peer. Native through the real service, device deployment and measured storage
limits remain unqualified; see `PARITY.md`.

### 1 Freeze the compatibility contract

Create a machine-readable operation/result matrix and differential tests that run
identical requests against managed and native workers. Normalize only generated
IDs, timestamps, process identities and explicitly additive fields. Compare known
failure versus unknown transport outcome, emitted bytes, filesystem side effects
and retained job state, not just exit zero. Include native through the existing
JavaScript service; a standalone controller is insufficient.

Record each intentional difference as a versioned contract decision: command
signals, saved-job cancellation, stronger descendant cleanup, malformed-input
handling, UTF-8 conversion and added status fields. Recommended saved-job policy:
refuse cancellation when ownership is no longer provable and expose that limitation
explicitly. Never recreate saved-PID signaling merely to satisfy a superficial test.

Deliverable: compatibility tests and an approved difference ledger. Gate: every
public operation has success, rejection, interrupted-response and boundary cases.

### 2 Complete paths, retained state and long-running behavior

Replace the single-directory transfer resolver with explicit production read and
write policies. Use component-based traversal suitable for these older kernels;
preserve refusal of symlink components and special-device files. Do not require
new kernel-only APIs without a supported fallback. Recalculate peak descriptor
use after introducing parent directory handles and test exactly at each threshold.

Move job storage from experiment `.jobs` to a versioned production layout. Import
or expose managed `/opt/couchroot-agent/jobs` records without replay. Keep completed
results, preserve ambiguous outcomes, and define behavior for malformed records,
partial `.next` files, duplicate IDs and capacity shared with legacy records.
Do not fabricate a native owner identity for an old managed record.

Use copy-and-verify migration or a read-only legacy view with an atomic manifest
commit. Keep legacy bytes unchanged until the rollback window closes. Test rollback
with native-created records: the managed worker must not misread them or reuse an
ID. Shared writers are prohibited; selection must establish a single owner.

Remove experiment alarms from the production mode while retaining bounded requests,
job deadlines, drain deadlines and watchdogs. A test-only bounded mode remains
available. Audit progress reporting through hashing, copying and durable writes:
a valid large operation must not look like a 30-second deadlock. Test sparse/large
files, slow storage, long idle connections and 24-hour jobs separately.

Deliverable: production-mode worker with public path/state behavior. Gate: full
contract suite and native host tests pass, including downgrade and interrupted
migration fixtures.

### 3 Integrate packaging and service selection

Installed-runtime update: QN90A's proc-stat path remains qualified. S90D's
0.7.11 external observer passed two complete non-stopping service probes,
including exact package-thread credentials, independent copied execution staging,
native termination receipts, non-blocking unit retirement and owned-file cleanup.
Both TVs retained their managed workers and boot identities. Direct WRT
child-process launch remains disabled. See the current
[deployment evidence](../native-observer/DEPLOYMENT.md).

The remaining handoff dependency is cleanup after the source worker exits.
The runtime now distinguishes probe and handoff purposes: a handoff requires an
explicit independent inspection/retirement provider before any launch intent.
Launch and fresh readiness checks still use the held source worker; cleanup gets
only the bound unit, boot and artifact digest, never its departing executor.
The internal shutdown path can use this boundary and keeps the selection pending
and admission held after shutdown. The installed service does not supply such a
provider, so its shutdown guard remains active. Local tests cover disconnect,
changed inventory, missing provider and uncertain cleanup. They do not qualify a
production provider or an on-TV stopping handoff.

The independent provider adapter now uses a separate, authenticated, bounded
native worker with isolated state. Both TVs passed scoped adapter tests against
ordinary native binaries, including real unit inspection/retirement and verified
provider/guardian exit. These were host-orchestrated tests with the managed source
left running, not installed-service handoffs. See the observer deployment record.

Durable provider submission is now implemented locally: exclusive launch and
pending records precede root mutation, candidate/token/source identities are
bound, and uncertain results block all replacement IDs. Readiness publication is also implemented locally: it binds the native guardian
to the running unit, rechecks source/native identities, and publishes a ready
record under an exclusive intent. Real-wire host tests include that transition.
Listener/token coordination and journal-driven teardown remain unintegrated.

Next, integrate the provider listener, submission and teardown into the service, then
exercise the real external observer across managed shutdown with retained records, followed by
live state installation/native trial and managed rollback. Do not substitute a
Mac-only controller for the deployed runtime or use the non-stopping probe as
proof of this gate. No native selection gate has passed.

Local packaging foundation is implemented: `--native-candidate` includes three
reproducibly built ordinary artifacts and a manifest while retaining managed
selection (worker, app launcher and process observer). See `PARITY.md` for build evidence. Service-side candidate manifest validation and diagnostics are also implemented,
without native launch. A durable selection journal and service guards now track
versions, transition phases and evidence hashes. Workers now expose bounded live
resource inventories, and an internal service admission hold drains admitted
requests before obtaining fresh inventory from the same worker connection. These
are locally tested. A journal-bound managed shutdown now waits for authenticated
acknowledgement/disconnect and independently observes original process identities
exiting. It leaves selection pending and admission held. Detached work, retained
resources and state installation still require reconciliation; process exit alone
does not establish the full transition gate.
Focused ordinary-sidecar checks now pass on both TVs, with a discovered integration
constraint: S90D's service identity receives EACCES reading root process stat files.
The direct observer must remain fail-closed there. A matching service-identity
probe successfully bound and polled pidfds across shutdown on S90D; QN90A's older
kernel passed the existing proc-stat approach. See `handoff-results.json` and
`PARITY.md`. Complete deployment integration before enabling S90D handoff.
An internal managed-handoff pidfd bridge now binds the handle before a fresh
authenticated inventory/identity confirmation and requires bounded observer exit
evidence. It is locally tested through the actual service hold and managed wire
session. Schema-2 candidates now package the observer with source/build hashes;
schema-1 candidates remain accepted without it. It is not enabled by the installed service. See
[`native-observer/README.md`](../native-observer/README.md). The staged executable
must still be verified against the package manifest and qualified in the TV service context.
Bind handles before a fresh authenticated identity confirmation; the test controller
owns the guardian child. Native status now checks its original guardian parent
relationship on every request (`guardian-parent-identity-v1`), without allocating
a descriptor. The bridge now binds both handles and requires this fresh confirmation
before arming. Local real-wire native shutdown tests pass with both exits and
separate guardian cleanup checks. Native service selection and TV launch remain
unqualified. A bare PID or an unreadable stat file is insufficient.
The runtime controller, live state installation/rollback and actual service
integration remain required; this is not phase-three completion.

The shared package updater now accepts an explicitly reviewed inventory digest
bound to both signed packages' complete member hashes, with union readback and
absence checks. Local tests pass; this is not hardware update/rollback evidence.
Signed candidates are prepared for both TVs but not installed. Read-only layout
inspection found installer-owned package files and a 2755 app data directory:
provide verified executable staging and a separate private selection-state
directory before service activation. See the observer
[deployment gate](../native-observer/DEPLOYMENT.md).
The private-state bootstrap is now implemented locally, using
`data/worker-state/worker-selection.json` and refusing conflicting legacy state.
Local tests include the unprivileged app UID. It is not yet deployed; rebuild the
previously prepared signed candidates before installation. Observer executable
staging and actual service-context validation remain open.
The subsequent internal handoff now stages the exact manifest-bound installed
observer's execute permission, verifies unchanged bytes/inode/owner, and binds
pidfds only after readback. Unknown outcomes or target drift retain the admission
hold and prepared journal. This is locally tested; actual TV service execution
and native selection remain unqualified.

Package ordinary worker, guardian functionality and app launcher from reproducible
source builds. Do not ship fault-control operations or depend on a copied binary
from a prior experiment. Record per-artifact hashes, ABI, dependencies and profile
compatibility in the manifest. Verify dynamic library availability on both TVs.

Retain the existing service and enrollment data. Add an explicit, durable selection
of managed or native, selected version and last-known-good version. Stage and verify
new artifacts before changing selection. Replace hard-coded managed launch arguments,
file allowlists, status-file assumptions and payload manifests in `service/agent.js`.
Require the expected implementation and capabilities during readiness, not merely
boot ID and a numeric uptime. The local service now implements this gate for
managed status and provides native readiness validation requiring pinned launcher
identity and production lifetime. It also rejects late connection status and
blocks requests before readiness. Native selection/staging and both-TV validation
remain required; the native validator alone does not enable a native launch.

Preserve connection-generation checks, capped acquisition retries and backoff.
On worker failure, reconcile its jobs and owned resources before selecting another
implementation. A fallback may restore availability; it must never replay the last
command, job start, upload chunk or commit. Preserve unknown outcomes in the journal.

Deliverable: opt-in native selection with managed default and tested rollback.
Gate: packaged native works through the unchanged client in a temporary trial;
managed rollback works with retained data and interrupted requests.

### 4 Replace acquisition and maintenance dependencies

Treat acquisition as a separate component with a narrow contract: validate the
supported profile, establish the required process identity and isolated execution
context, hand off the selected worker, report readiness/failure and clean only its
owned temporary resources. Port the existing supported behavior rather than adding
new device coverage or changing the method during the worker migration.

Inventory the complete managed call chain, including fresh installation and access
recovery. Replace `SamsungTvArchiveRoot` and any required managed bootstrap/control
utility with individually testable native components. Preserve profile checks,
one-launch behavior, retry bounds, result reporting and cleanup. A native worker
started by a managed bootstrap is only milestone one.

Replace the maintenance recovery utility's readback, conditional restore and delayed
restore behavior. Test invalid inputs, setting drift, already-restored state,
interrupted execution and failed readback using local fixtures before device trials.
The recovery path must remain usable when the selected worker fails before readiness.

Deliverable: native acquisition/recovery artifacts and agent-only build path.
Gate: each supported TV can start and reacquire native without a managed agent
process; required installation and recovery paths also demonstrate independence.
Actual device-setting changes require a separately authorized, journaled trial.

### 5 Qualify the integrated native agent

Use the exact ordinary packaged build on both TVs, first sequentially, while keeping
the managed fallback available. Record source revision and artifact hashes. Capture
kernel and lifecycle evidence continuously into bounded private logs, with explicit
coverage gaps and clock handling across suspend. A final ring-buffer tail is not
full-run evidence.

| Test group | Required observations |
| --- | --- |
| Public operations | Complete differential suite through HTTPS, app identity/environment, helper stage/execute/release, large transfers and conditional commit |
| Jobs and state | Concurrent quiet/noisy jobs, retention/cursors, cancel/timeout, 24-hour job, persisted outcome, migration and rollback without replay |
| Lifecycle | Graceful stop, worker loss, guardian loss, stalled main/monitor, service loss, reconnect, install interrupted before/after selection, interrupted cleanup |
| Pressure | Descriptor thresholds, guardian budget, ENOSPC/read-only, allocation/process failures and slow storage; no unintended command execution |
| Endurance | Proposed gate: at least 24 hours per TV with mixed work and idle periods; stable descriptor/thread/mount counts and no unexplained sustained memory growth |
| Timing | Preserve the two-second recovery gate where it applies; collect phase timings and tail distributions, including the previously observed S90D outlier |
| Power lifecycle | Separately authorized standby/resume, deep suspend, software reboot, cold start and interrupted-write/power-loss cases; validate old-boot journals and readiness |
| Recovery | Native failure before readiness restores the last-known-good implementation without host-side reconstruction or a managed utility hidden in the native-only path |

No reboot or deliberate power transition is authorized by this plan. Prepare those
fixtures and mark them pending. Native default and sunset remain gated until the
required transitions are actually tested, or the user explicitly approves a narrower
support contract. An accidental interruption is useful evidence, not a planned test.

Repeat full process-tree measurements for managed and native: guardian plus worker
RSS/PSS/private memory/swap, CPU, idle wakeups, peak descriptors, acquisition-to-ready
time, app startup, job latency and transfer throughput. Alternate versions under
comparable conditions; retain sample counts, medians and tails. Distinguish complete
acquisition from a warm worker launch. Propose no blanket speedup target: require
no material regression in supported workflows and quantify the intended benefit.

### 6 Deprecate, switch default and sunset

Use release gates rather than a fixed calendar deadline:

| Release stage | Behavior | Exit criteria |
| --- | --- | --- |
| Candidate | Managed default, explicit native trial | Contract/state/packaging gates and recovery rehearsal pass on both TVs |
| Native default | Native selected; verified managed package retained for rollback | Integrated acquisition and power-lifecycle qualification pass; no unresolved outcome-loss or duplicate-execution issue |
| Managed deprecated | Managed is maintenance-only; notices identify replacement and rollback policy | Proposed minimum 14 days of ordinary native use on each TV, including authorized lifecycle transitions; no unresolved fallback event; owner approves removal |
| Agent .NET sunset | Current package and agent build exclude managed worker/acquisition/recovery | Native-only fresh install, upgrade, reacquisition and recovery demonstrated on both profiles; zero required managed agent process in lifecycle observations |

The 24-hour qualification and 14-day observation periods are proposed minimums,
not already completed tests. A period with either TV unavailable does not count as
an equivalent amount of active observation. Record exceptions explicitly.

Before switching a device, quiesce mutations, inventory active jobs/transfers,
complete or explicitly cancel owned work, snapshot data, verify the rollback
package and recovery access, then commit selection. Never silently discard a
running job or treat an incomplete transfer as committed. Switch one TV first;
validate it before switching the other. A rollback uses the same journaled state
transition and preserves native-created outcomes for inspection.

At sunset remove managed agent artifacts from the package, current build graph and
runtime selection; update manifests, dependency checks, tests and documentation.
Retain the last supported managed release and its verified recovery material in
the private release archive for an explicitly documented retention period. Remove
only known project-owned stale device files after ownership checks. Leave vendor
runtime files and unrelated Couchroot components untouched. Historical source and
result records remain available; retirement does not require rewriting Git history.

## Work packages and dependencies

| Work package | Main files | Depends on | Completion evidence |
| --- | --- | --- | --- |
| Contract and intentional differences | `CAPABILITIES.md`, service/client tests, native and managed harnesses | Reviewed baseline | Differential matrix, accepted differences |
| Production paths and limits | Native `worker.c`, common helpers, transfer tests | Contract | Full path/size/race/descriptor threshold fixtures |
| Job migration and rollback | Native `jobs.h`, reconciliation, setup migration code | Contract | Legacy/native state import and downgrade tests |
| Lifetime and diagnostics | Native worker/guardian/progress, service status | Contract | Long-idle/long-job/slow-storage tests |
| Packaging and selection | `tvsetup/autonomous_root.py`, builders, `service/agent.js` | Contract, paths, state | Reproducible ordinary build and managed/native selection tests |
| Acquisition and maintenance ports | Acquisition payload, recovery utility, required setup callers | Dependency inventory | No managed process required for each lifecycle path |
| Integrated qualification | Acceptance harness, real service tests, private device runner | All above | Both-TV acceptance, continuous evidence and rollback rehearsal |
| Default and retirement | Release metadata, selection, build/dependency cleanup, docs | Qualification and observation window | Per-device approval and sunset checklist |

Start with the contract, path parity and retained-state work. Acquisition can be
specified independently, but default selection must wait for its acceptance. Avoid
another broad cleanup pass until these deliverables are complete.

## Definition of done

.NET is sunset for the agent only when all public features either match or have an
explicitly accepted versioned difference; retained outcomes survive upgrade and
rollback; both supported profiles pass integrated lifecycle acceptance; recovery
works without the managed components being retired; production artifacts contain
no test hooks; the agent-only build has no .NET SDK dependency; and the owner has
approved the final removal after the observation window. Keep .NET available until
then.

### Retirement session coordination (local only)

`retirement-session.js` composes a private loopback listener and fsynced random
token with journaled launch and provider readiness. It exposes only the verified
retirement adapter and transport closure; no generic command channel is returned.
A launch/readiness failure retains ownership material for reconciliation. Closing
the transport does not retire the unit, release the launch marker, or delete
staging. Host tests exercise ordering, token binding, listener failure, disconnect,
readiness rejection and refusal to launch over an existing pending record.

This coordinator is not yet enabled in the installed service. Provider teardown,
interrupted-session reconciliation and integration with the admission hold remain
required before a stopping handoff can be enabled or qualified on either TV.

### Retirement teardown (local only)

`retirement-teardown.js` now journals a verified native shutdown, checks successful
unit completion through an independent executor, verifies worker/guardian exit and
hash-bound staging, and stops the completed unit without blocking. It removes only
the expected worker, launcher and empty job-lock layout. Unexpected artifacts or
uncertain execution retain pending ownership. Service token deletion follows remote
cleanup; only then does completion release the launch marker. The session exposes
this one-shot teardown while preventing further adapter operations.

Linux host validation includes real native shutdown after managed-source exit,
completion of the private token journal, and execution of the cleanup shell against
controlled process/unit/filesystem fixtures. Systemd inspection remains simulated
in these host tests. Neither TV has received this coordinator. Interrupted cleanup
and token-deletion reconciliation, installed-service integration, and both-TV
stopping handoff qualification remain open; .NET remains the deployed fallback.

### Interrupted retirement reconciliation (local only)

`retirement-reconcile.js` handles a journaled shutdown whose reply was lost,
partial remote cleanup, and the local token/completion publication crash windows.
It distinguishes observed process exit from an acknowledged shutdown and never
replays launch or shutdown. A durable cleanup intent permits checking and removing
remaining owned entries after the unit has stopped; missing entries alone do not
prove success. If cleanup had not yet stopped the successfully completed unit,
the full original artifact layout must pass before the nonblocking stop. Live or
replaced processes, unexpected entries, changed hashes and inconsistent unit
snapshots retain pending ownership. Token removal and marker release follow the
persisted remote-cleanup result.

The combined Linux host suite passes 106 tests without skips, including partial
filesystem cleanup, lost responses, token deletion interruptions and real native
shutdown. Shared exact-path fixtures now serialize access to the isolated app
state. Unit state is simulated in reconciliation tests. Uncertain launch/readiness
before a verified provider record, installed-service orchestration and both-TV
handoff validation remain open. No device update or reboot was performed for this
change; the managed fallback remains deployed.

### Installed non-stopping provider integration — 2026-10-14

Both TVs now run service 0.7.13 with managed selection. The service holds admission,
opens a journaled native retirement session, verifies the original managed process,
performs its model-specific observer probe, then shuts down and retires the provider
before releasing admission. Provider probes have a distinct transaction namespace.
Uncertain launch, observation or cleanup retains admission and durable ownership;
WRT child-process execution remains disabled. S90D's independent provider performs
observer unit inspection/retirement; QN90A uses its qualified proc-stat path.

Two probes per TV passed with unchanged source-worker and boot identities; all 45
installed package members and provider cleanup were independently verified. The
initial S90D pilot exposed an immediate guardian-completion assumption after BYE;
the forward update adds bounded observation and passed both repeated probes. See
the observer deployment record for the failed-pilot limits and recovery evidence.

The final Linux rerun passed 109 tests without skips; seven API tests also passed.
An earlier combined run intermittently failed the existing managed retained-job
fixture while reading `/proc/<pid>/stat` for a short-lived job. Its five-test isolated
rerun and the final combined rerun passed. This remains an open short-job identity
capture investigation, not a proved fix or evidence of native parity.

This integration does not enable stopping handoff. Uncertain launch/readiness
reconciliation before provider identity is durably established, production native
startup/state transfer, managed rollback, and the broader lifecycle/sunset gates
remain required. The deployed .NET worker remains the fallback; no reboot was used.

### Service-readable retained state — local follow-up

The independent provider now exposes a dedicated snapshot operation for the stopped
managed source's fixed job directory. It preserves record bytes, validates them
against the supported offline import contract, checks source process/boot identity,
and rejects changed inventory before returning a digest-bound result. It neither
writes destination state nor launches or replays a job. A real native-channel host
test reads the retained fixture after the real managed process exits; shell tests
cover a live source, PID reuse, links, permissions, pending entries and overflow.

The combined Linux suite passes 116 tests without skips. A differential Python/JS
test checks standard JSON record acceptance against the existing offline importer,
including integer types, escaped duplicate keys and UTF-8 BOM preservation. These
are host results; both TVs remain on the previously qualified 0.7.13 packages.
Destination staging, durable installation receipts, production native launch and
rollback still need to consume this snapshot before stopping handoff is enabled.

### Durable retained-state installation — local follow-up

The independent provider can now install its own validated managed snapshot into
an exclusive native state directory. A durable local intent and saved snapshot
bind the selection transaction, source identity and target manifest before remote
writes. A remote pending manifest prevents native startup during copying. Records
are created without replacing differing content, checked against their hashes,
and published with a synced import manifest only after source inventory is
rechecked. The ready receipt retains transition ownership and does not change
selection or launch the worker.

Explicit resume requires the same saved snapshot, selection and remote ownership
manifest. Tests cover lost begin/copy/commit replies, bounded scratch cleanup,
source drift, conflicting destinations and all 64 records with maximum-length
identifiers. Interruption before the remote ownership manifest exists remains a
refusal requiring reconciliation; service restart/provider reacquisition is not
implemented by this operation.

A real native-channel host test now copies retained state after managed exit and
starts a production-mode native worker against the installed directory. Both
ordinary JSON and UTF-8 BOM records survive byte-for-byte through status readback
and shutdown. This exposed and fixed a native saved-record parser discrepancy:
the importer accepted BOM-prefixed JSON while the runtime rejected it. The fix
is confined to saved job records, including guardian reads.

The final combined Linux rerun passes 123 tests without skips, three targeted
native retained-state/recovery tests pass, and the Python/JS importer contract
comparison passes. An earlier combined run again exposed the existing managed
short-job process-identity race; it remains unresolved. The test container also
read an incomplete test source once; syntax validation and the complete rerun
passed. These are host results, not on-TV installation qualification. Both TVs
remain on service 0.7.13 with managed selection. Production launch orchestration,
rollback and stopping-handoff qualification remain open; no reboot was performed.

### Managed short-job baseline repair — local follow-up

The intermittent short-job failure is now reproduced deterministically: after a
tracked child exits and is reaped, its procfs stat read can raise
`DirectoryNotFoundException`, while job start previously caught only
`FileNotFoundException`. A live procfs read can also race process exit. Identity
capture now treats an I/O failure as absent start identity only when the tracked
`Process.HasExited` confirms exit. Other failures still propagate; retained-job
cancellation continues using the strict identity reader.

A Linux harness checks live identity, then forces exit before identity capture,
and verifies 64 immediate commands preserve output, exit code and retained record.
The deterministic test failed before the fix. The combined migration suite passes
124 tests without skips. This is host validation; the deployed managed payloads
on both TVs have not changed, and device qualification remains required before
calling the repair deployed. No reboot was performed.

### Retained-state receipt consumption — local follow-up

The provider now binds acceptance to the receipt returned by its own installation
operation. Acceptance reads the private durable receipt and saved snapshot,
reconstructs the expected destination plan, checks transition identity/version,
and rechecks both source inventory and installed content through the independent
provider. Local ownership is checked around every remote await. Only then does
it advance the selection journal from prepared to state-ready using the receipt
digest. Managed remains selected, admission remains the controller's responsibility,
and the installation ownership marker is retained for the launch/rollback phase.

Repeating acceptance after a lost return is idempotent only for the same receipt
and reverified remote state. Changed receipt, source, destination, saved snapshot,
marker or selection refuses progress. An unfinished selection writer prevents
remote work. This operation does not reacquire a provider after service restart.

The combined Linux suite passes 128 tests without skips. The real managed-exit /
independent-native-channel test now consumes the receipt before its host-fixture
production launch, for both ordinary and BOM-prefixed JSON. Production launch in
that test is still performed by the harness, not the installed service controller.
Journaled production launch, readiness acceptance, rollback and both-TV stopping
handoff therefore remain open. The deployed TV packages are unchanged; no reboot
was performed.

### Journaled production submission — local follow-up

An independent provider can now submit a production worker after accepting its
own retained-state installation. The launch binds the accepted receipt, source
identity, target manifest, packaged worker/launcher hashes and a private loopback
token. Before staging, it persists a single-use production launch record and
ownership marker. The generated command revalidates all installed records, rejects
an existing unit, stages root-owned code/launcher/token, checks source departure
again and requests production mode with no bounded probe lifetime.

Submission acknowledgement only changes the launch journal to submitted. It does
not mark a worker ready, commit selection, release admission or retire the
independent provider. A lost/failed result retains unknown ownership and refuses
replay. Local ownership drift retains the original intent instead of overwriting
newer state. A partial staging directory is not automatically adopted or removed.

The combined Linux suite passes 135 tests without skips. Shell tests exercise
actual filesystem ownership, hashes, retained record preservation and source-exit
guards, including maximum retention command size. Systemd submission is a fixture
in these tests; no production unit was launched on either TV. The private listener,
production readiness record, uncertain-launch reconciliation and rollback still
need integration before installed stopping handoff can be enabled. Deployed .NET
fallback and both TV boots remain unchanged.

### Production readiness acceptance — local follow-up

The independent provider now verifies its submitted production peer before a
state-ready transition can become trial-ready. Readiness requires the expected
root/System peer, production lifetime/capabilities, staged launcher digest,
empty owned-resource inventory and distinct source/provider/production process
identities. Two matching unit observations bind the guardian and monotonic unit
start. Independent shell checks verify live process start identities/executable
paths, staged artifacts, consumed token, import manifest and retained bytes in
both source and destination. Every retained record is also read through the new
worker's job-status operation and compared with the expected saved-record result.

The ready launch record is durably published before the selection journal gains
its readiness digest. Selection remains managed and pending, and the production
ownership marker remains. Drift, disconnects and publication uncertainty retain
reconciliation evidence; a ready record alone cannot bypass an unfinished
readiness intent or authorize launch replay.

The combined Linux suite passes 141 tests without skips. The real managed-exit
integration now verifies a staged production native worker via a separate native
provider, including actual procfs/executable/file checks and ordinary/BOM job
records. Systemd state and unavailable host Smack/mount setup remain fixtures;
this does not establish on-TV production readiness. Maximum-retention command
size, identity/unit drift, changed resources/records and lost ready-publication
acknowledgement are covered. The private production listener, recovery of partial
publication, controller adoption/rollback and both-TV stopping handoff remain
open. Deployed packages and TV boots are unchanged.

### Private production session and channel transfer — local follow-up

A production session now owns the private loopback listener and random token,
invokes the independent provider's launch/readiness operations, and validates the
result against durable trial evidence. It removes unused token material only for
failures before submission; all uncertain launch/readiness/disconnect outcomes
retain ownership evidence. The listener deadline is distinct from the bounded
readiness check. Transport closure never claims process or staging cleanup.

The channel is available exactly once after the controller commits the matching
trial, with the selected manifest, state receipt, readiness receipt and latest
history entry all matching. Adoption rechecks the live worker identity and local
ownership; a mismatch closes transport and requires reconciliation. This session
does not itself commit selection, retire the provider, clear launch markers or
implement rollback.

The combined Linux suite passes 147 tests without skips. The real-process test
now uses this listener/token/session through authenticated production readiness,
a test-harness commit and channel transfer, then reads retained state and shuts
down. Both ordinary and BOM-prefixed records survive. Host staging/systemd and
Smack/mount boundaries remain fixtures. The exact app-state fixture is serialized
across test processes. Timeout, listener failure, premature adoption, identity
drift, duplicate adoption and disconnects are covered separately.

Installed-controller adoption, interrupted-session recovery, rollback and both-TV
stopping-handoff validation remain open. The TV packages and boots are unchanged;
.NET remains deployed. The host-harness commit is not a native-default rollout.

### Agent ownership transfer — local follow-up

The held agent can now adopt a production session only after its source shutdown
and observer cleanup completed, the exact source inventory matches the committed
trial, and fresh native status confirms the recorded worker/guardian identity,
production capabilities, launcher and empty owned-resource inventory. Source-exit
and readiness receipts are copied before use so later caller mutation cannot
change the held evidence.

The agent advances its generation before closing the stopped managed listener.
Late source callbacks therefore cannot overwrite native state. The adopted
channel has a disconnect handler that retains the hold and requests reconciliation
without scheduling managed reacquisition. Adoption is one-shot, and uncertainty
closes the supplied session. Public admission remains held; this change does not
yet enable serving requests from the adopted native peer or native cold startup.
Provider retirement and final transition completion must precede admission release.

The combined Linux suite passes 148 tests without skips. Agent ownership-swap
unit tests cover pre-shutdown/precommit refusal, identity/selection drift, stale
callbacks, duplicate adoption, retained admission and disconnect behavior. The
separate real-process session/readiness integration remains passing. Installed
controller orchestration, admission release, rollback/recovery and both-TV handoff
remain open. Deployed packages and TV boots are unchanged.

### Provider retirement and live admission release — local follow-up

The adopted agent can now retire its matching temporary provider using the new
native channel as the independently checked executor. Activation consumes the
complete retirement receipt, rechecks the inactive/missing unit and absence of
the provider's process identities/staging, and confirms the production identity
before removing local production token material and transition markers. A durable
activation intent covers partial cleanup/publication. Failure retains the hold;
an active receipt with an unfinished intent is not automatically adopted.

After activation and another fresh status check, the agent admits requests only
for the bound channel/generation and exact committed selection. Cold startup is
still governed by the existing selection launch policy; live admission does not
permit an unverified native restart. Disconnect clears live admission without
starting a managed replacement. Provider, source and production identities must
remain distinct.

The combined Linux suite passes 153 tests without skips, followed by targeted
activation/admission reruns after tightening identity/selection binding. Tests
cover incomplete provider cleanup, altered token/receipts, live/replaced provider,
native drift, lost activation publication, blocked requests before completion and
successful routing afterward. Agent retirement/activation uses fixture evidence
in these unit tests; this is not an installed both-TV handoff result. The separate
real native session/readiness tests remain passing.

Full orchestration, interrupted-transition recovery, rollback, native cold-start
integration and both-TV qualification remain open. Deployed packages and TV boots
are unchanged; .NET remains deployed as fallback.

### Coordinated live handoff — local follow-up

The internal agent migration entry point now coordinates candidate/baseline checks,
admission drain, selection intent, independent provider preparation, source stop,
retained snapshot/install/acceptance, production session/readiness, selection commit,
channel adoption and retirement/activation. The provider is prepared under the
held source identity and cannot race source shutdown while startup is pending.
S90D's external observer retirement uses that same prepared provider.

The controller is single-use. Pre-handoff refusal releases only a hold it acquired
before a selection intent could have published. After begin, uncertainty keeps
admission held and retains live session references for explicit recovery instead
of discarding useful access or replaying launches. Agent stop closes retained
transports and prevents the controller progressing through its next phase. Status
reports the migration phase/transaction without token or command contents.

The combined Linux suite passes 159 tests without skips. Controller tests use real
selection journals with operation fixtures to verify order, each failure boundary,
preexisting ownership refusal and cancellation. Separate live managed/native
session tests and the provider-preparation/admission tests remain passing. This
is not yet a full installed controller run on a TV. No public migration endpoint
is enabled by this change; rollback and interrupted-transition recovery remain
required before on-TV cutover. Native cold startup and broader sunset gates also
remain open. Deployed packages and TV boots are unchanged.

### Live-channel activation reconciliation — local follow-up

Activation now has an explicit resume mode for the ordered local cleanup windows:
a removed token, an empty/removed token directory, each marker removal, published
activation with a remaining intent, and a fully published receipt whose return
was lost. Partial cleanup requires the exact durable intent. A completed receipt
without an intent is accepted only with the fully cleaned layout. Every resume
rechecks the native identity, committed selection, original receipts and remote
provider absence; it neither launches a worker nor repeats provider shutdown.

The held agent retains the completed retirement receipt before activation begins.
Its explicit completion retry reuses that receipt, excludes concurrent completion,
and keeps admission held on failure. The migration controller exposes this retry
only after its activation phase failed; earlier handoff failures cannot skip ahead.

The combined Linux suite passes 163 tests without skips. Fault tests interrupt
after every cleanup/publication boundary, then verify matching resume and repeated
receipt readback. Missing/changed intents, foreign directory entries, changed
markers and changed native identity refuse recovery. Agent/controller tests prove
provider retirement and earlier handoff phases are not replayed.

This recovery requires the verified production channel to remain alive. Service
restart/provider reacquisition, earlier launch/readiness reconciliation, rollback,
native cold startup and both-TV qualification remain open. Deployed packages and
TV boots are unchanged; .NET remains deployed as fallback.
