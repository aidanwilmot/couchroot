# Process exit observer

This small executable observes a worker and optional guardian using Linux `pidfd_open` and
`poll`. It does not acquire credentials, signal the target, or prove resource
cleanup. It is intended for S90D's service identity, which cannot read the root
worker's `/proc/<pid>/stat`. QN90A's older kernel retains the existing proc-stat
observer. An unavailable syscall or denied observation is a failure, never proof
that a process has exited.

Invocation: `process-observer BOOT_ID WORKER_PID [GUARDIAN_PID]`, with pipes for
stdin/stdout/stderr. Pair PIDs must be distinct.

An opt-in external transport is also available:
`process-observer --connect SOCKET_PATH TOKEN_FILE BOOT_ID WORKER_PID [GUARDIAN_PID]`.
The observer connects to an existing filesystem Unix socket, checks that its peer
has the same effective UID and GID, and redirects only stdin/stdout to that socket.
It reads exactly 64 lowercase hexadecimal characters from a regular, single-link,
0600 token file owned by its effective UID, refusing a final-component symlink.
It emits `AUTH TOKEN\n` before the unchanged observation protocol. Stderr remains
with the external launcher; no token is printed there or in argument values.

The internal `service/external-observer.js` listener creates a fresh random token
and private directory for each launch, authenticates the first connection before
interpreting `BOUND`, refuses additional connections, and bounds input/deadlines.
After binding it requires a fresh authenticated worker status with unchanged
identities; native pairs also require fresh guardian-parent confirmation. Only
then does it send `ARM` and expose readiness. Its launch descriptor contains paths,
boot ID and target PIDs, not token contents. A future launch adapter must bind this
listener and its termination receipt to the selection transaction.

The listener does not spawn a process. Socket EOF is not proof of the observer's
exit status: its trusted launcher must call `recordExit` with independently observed
termination. Successful exit observation requires `EXITED`, clean socket EOF and
a zero-exit/no-signal receipt. Nonzero exit or signals invalidate the result.
`cancel` closes the control channel without signalling a target. `dispose` refuses
to remove the private token/directory until termination has been established, and
unknown outcomes retain those files for reconciliation. This is not a durable
launch journal or recovery controller. The installed service's child-process
rejection guard remains enabled; neither transport is selected automatically.

External connection/authentication uses the same independent 35-second alarm.
Descriptor admission precedes token/socket allocation, and controller loss fails
observation without signalling either target. Parent stdio is not needed for the
observation protocol. Callers must preserve the selected service-equivalent
identity; this option never changes credentials or labels.

The native supervision entry point is
`process-observer --supervise SOCKET_PATH TOKEN_FILE BOOT_ID WORKER_PID [GUARDIAN_PID]`.
It requires `control` and `token` in the same caller-owned 0700 directory. Before
forking it creates and syncs an exclusive `result.next` intent. Existing intent or
result files refuse a second launch. The child runs the socket observer in the
same executable/identity; it sets a parent-death signal and verifies its parent
before proceeding. The supervisor waits for and reaps only that child, then
publishes a synced, create-only `result` receipt and removes the intent. It never
signals the target worker or guardian. Observer and supervisor alarms are 35 and
45 seconds respectively; interrupted supervision can leave only an unknown intent.

Receipt schema 1 records boot ID, both target PIDs, observer PID, nullable exit
code and nullable numeric terminating signal. Supervisor exit zero means receipt
publication succeeded, **not** that observation succeeded: the receipt can record
a failed or signalled observer. `readPublishedExit()` on the service listener waits
for intent removal, validates the bounded private single-link receipt against the
launch, and feeds its result into the existing socket-plus-termination gate. It
retains malformed, mismatched or unfinished files for reconciliation. Cleanup
removes a consumed receipt only if its inode still matches.

The TV launch adapter is still required. It must start this supervisor outside
`wrt-service`, pin the executable and invocation to the selected manifest and
transaction, use the service-equivalent credentials, and reconcile uncertain
submission rather than retrying. Neither the listener nor this entry point is
currently selected by the installed service.

1. Check descriptor capacity and boot, close inherited descriptors, bind all
   pidfds and verify none has exited; emit `BOUND`.
2. The service obtains fresh authenticated worker identity and resource inventory
   and compares them to the journal-bound snapshot. A bare numeric PID is not
   sufficient. The worker must still answer over the original connection.
3. The service writes `ARM\n`; the observer verifies boot and liveness again and
   emits `ARMED`. Only then may the service submit `SHUTDOWN`.
4. Once every handle reports exit, verify boot again, emit `EXITED` and exit zero.
   The service requires the exact protocol, clean pipe closure and zero exit.

Preparation is bounded to ten seconds, armed observation to twenty seconds, and
the entire helper to a separate 35-second alarm. Controller EOF, malformed input,
early target exit, wrong boot, and broken output fail. The service bridge bounds
output and elapsed time and cancels only its own observer child. A pidfd exit
receipt means the process exited; unlike proc-stat absence it does not establish
reaping. Neither method establishes mount, descendant or retained-state cleanup.

`service/agent.js` accepts an internal `processObserver: {binary, sha256}`
construction option. The artifact is checked as a bounded regular file against
the supplied digest before launch. The deployment owner must provide the digest
from a verified manifest and keep the staged path immutable through execution;
this check is not a race-free executable loader. The option has no public API or
configuration route. Default behavior remains proc-stat observation; there is no
automatic fallback after a permission error.

Native pair observation requires a fresh raw authenticated status response after
both handles are bound, including `guardian-parent-identity-v1` and matching worker
and guardian identities. Missing capability or changed identity refuses arming.
Native status confirms the original parent relationship on every request.
Startup established the
guardian's start ticks and direct parent relationship; the fresh kernel parent
check binds that cached identity to the original parent without opening another
descriptor. This is point-in-time confirmation; either process can subsequently
exit. The observer retains evidence of each exit and waits for the other process
without repeatedly polling an already-exited handle.

## Qualification boundary

The bridge is integrated into the service's internal managed handoff and tested
locally with the real managed wire session, admission hold and selection journal.
The native pair path is tested through the actual wire server and ordinary native
worker/guardian, with journal/runtime cleanup verified separately after exit. The
service selection controller still supports managed handoff only; these native
wire tests do not qualify a native-to-managed service transition.
The tests also cover changed confirmation, malformed protocol, digest mismatch,
descriptor inheritance, deadlines, controller loss and no target signalling.

Local validation on 2026-10-14 passed eight native protocol tests and 29 Node
bridge/service/process tests, including real managed handoff through both proc
and pidfd observation and refusal before shutdown on an observer digest mismatch.
Two ordinary ARMv7 softfp builds matched byte-for-byte; their maximum required
GLIBC version is 2.17. These results do not establish TV executable staging or
service launch compatibility.

The subsequent paired-observer revision passed 12 native protocol tests and 32
Node bridge/service/process tests, including ordinary native worker and guardian
shutdown through the actual wire server. Final repeated ARM builds matched and
all nine candidate-package tests passed; GLIBC remains capped at 2.17. This is
local evidence only.

Schema-2 candidate manifests now include the observer and its source/build hashes.
Schema-1 candidates remain accepted without an observer. `main.js` selects the
packaged permission-staging path for an explicit internal S90D handoff, with the
prepared target manifest required. It does not stage at startup or select native.
See [deployment details](DEPLOYMENT.md).
Its launch from the actual installed TV service still needs qualification. Earlier
TV pidfd probes establish kernel feasibility, not this executable's deployment.
Do not enable production handoff based only on host tests. .NET remains deployed.

Cross-compile with `sh build.sh /absolute/output/directory`. For local Linux
tests compile `process-observer.c` with `cc -std=c99 -O2 -Wall -Wextra -Werror`,
then set `PROCESS_OBSERVER` to the executable and `COUCHROOT_PARITY_CONTAINER=1`
inside the disposable parity container. Run `process_observer_test.py`,
`pidfd-observer.test.cjs`, and `managed-handoff-integration.test.cjs`; the latter
also needs the existing `MANAGED_PARITY` harness. Never point test process-control
fixtures at device PIDs.

The external socket revision passed 22 native tests (12 existing and 10 socket
cases), plus all 31 focused Node bridge/service/managed-wire tests in the Linux
container. Socket coverage includes fragmented control, both target exits,
controller disconnect, invalid control, token contents/mode/links, wrong boot,
descriptor pressure, missing listener and mismatched peer credentials. Two ARM
builds matched at 18,016 bytes, SHA-256
`e8a3b47e66b92791c0a06d50c0a6edd72e46e1235f70601892c7249caee32085`,
with the maximum GLIBC requirement still 2.17. This is local transport evidence;
no TV was contacted, changed or rebooted for this revision.

The subsequent service listener passed eight additional tests, including the real
ordinary socket observer against a live Linux target. All 39 focused Node observer,
service and managed-wire tests passed. Tests require an independent termination
receipt after EOF, refuse bad authentication/sequence/identity, propagate a nonzero
observer exit, preserve files after cancellation or timeout, and enforce a private
parent directory. Device launch integration and supervised termination evidence
remain required; host test children supply that receipt only in the test harness.

The native supervisor revision passed eight supervisor tests in addition to the
22 existing native observer/socket tests. Coverage includes a pair, actual child
reaping, nonzero/signal receipts, controller and supervisor loss, retained unknown
intent, duplicate refusal, directory permissions and boot mismatch. All 42 focused
Node tests passed, including the real supervisor publishing a receipt consumed by
the socket listener. Two ARM builds matched at 22,740 bytes, SHA-256
`8919e5283aae233f1cdf619306a4b34a55c57d4e378bf52d9236d8766f4b7691`;
the maximum GLIBC requirement remains 2.17. No TV access or deployment occurred.
