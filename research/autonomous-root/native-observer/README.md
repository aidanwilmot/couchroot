# Process exit observer

This small executable observes a single process using Linux `pidfd_open` and
`poll`. It does not acquire credentials, signal the target, or prove resource
cleanup. It is intended for S90D's service identity, which cannot read the root
worker's `/proc/<pid>/stat`. QN90A's older kernel retains the existing proc-stat
observer. An unavailable syscall or denied observation is a failure, never proof
that a process has exited.

Invocation: `process-observer BOOT_ID PID`, with pipes for stdin/stdout/stderr.

1. Check the boot, close inherited descriptors, bind the pidfd and verify the
   process has not exited; emit `BOUND`.
2. The service obtains fresh authenticated worker identity and resource inventory
   and compares them to the journal-bound snapshot. A bare numeric PID is not
   sufficient. The worker must still answer over the original connection.
3. The service writes `ARM\n`; the observer verifies boot and liveness again and
   emits `ARMED`. Only then may the service submit `SHUTDOWN`.
4. Once the handle reports exit, verify boot again, emit `EXITED` and exit zero.
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

Native guardian observation is deliberately rejected by this single-handle
bridge. Native status now confirms the original parent relationship on every
request and advertises `guardian-parent-identity-v1`. Startup established the
guardian's start ticks and direct parent relationship; the fresh kernel parent
check binds that cached identity to the original parent without opening another
descriptor. This is point-in-time confirmation. Extending the observer to bind
both handles before requiring that capability remains necessary.

## Qualification boundary

The bridge is integrated into the service's internal managed handoff and tested
locally with the real managed wire session, admission hold and selection journal.
The tests also cover changed confirmation, malformed protocol, digest mismatch,
descriptor inheritance, deadlines, controller loss and no target signalling.

Local validation on 2026-10-14 passed eight native protocol tests and 29 Node
bridge/service/process tests, including real managed handoff through both proc
and pidfd observation and refusal before shutdown on an observer digest mismatch.
Two ordinary ARMv7 softfp builds matched byte-for-byte; their maximum required
GLIBC version is 2.17. These results do not establish TV executable staging or
service launch compatibility.

Schema-2 candidate manifests now include the observer and its source/build hashes.
Schema-1 candidates remain accepted without an observer. The observer is not
enabled by `main.js`.
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
