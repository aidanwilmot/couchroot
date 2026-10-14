# Worker parity contract and differential tests

`contract.json` freezes the public operation families, limits, result fields,
outcome categories and intentional differences against managed agent 0.7.0.
This is a migration contract, not a declaration that all production integration
is complete. Prototype capability names must not be promoted prematurely.

`worker_parity_test.py` sends the same fixtures through the actual managed
`Operation`/`Execute` methods and the native authenticated wire protocol. The
managed line bridge is compiled only into the test harness, never the TV payload.
The comparison requires the contract's fields, normalizes generated identities and
fixture roots, and checks known failures by outcome rather than exception wording.
Root-command output is compared as base64 bytes; job output uses the public cursor
format. Download frames are decoded and their digest checked before comparison.
Job timeouts may become visible before reaping; known-exit fixtures wait for the
exit result rather than equating `timed_out` with a completed drain.

Current differential groups cover file lifecycle/resume/status/ranges/conditional
publication, path rejection/external reads, root execution/bytes/timeouts, job
lifecycle/output/cancellation, job admission boundaries and legacy saved records.
The resource-inventory group compares fresh empty status, upload/download handles,
running and cancelled jobs, and explicit close/forget. Legacy-record fixtures
also verify that disk-only records are excluded from the worker-owned inventory.
Helper inventory on both actual TV runtimes remains a device qualification item.
The native tests separately exercise production-path descriptor thresholds,
parent replacement and cleanup, managed write roots, incomplete migration refusal
and imported-record restart behavior. Offline migration tests cover atomic
publication, interruption/resume, conflicting IDs, retention, links/permissions,
source preservation and rollback export.

The real HTTPS service, enrollment and implementation selection are unchanged.
Their end-to-end native selection remains a later integration gate; this harness
does not simulate it and call that parity. App identity and helper execution need
TV validation because host builds cannot reproduce Smack. The managed oracle runs
the production source on the test runtime, not the TV's old runtime binary.

## Run in a disposable Linux ARM64 container

Use an output directory outside Git. Build the managed oracle on the host with
its configured SDK, then build the isolated test image:

```sh
dotnet build tests/root-agent-harness/Harness.csproj -c Release -o /absolute/private/parity/managed
docker build --platform linux/arm64 -t couchroot-parity-test:arm64 tests/worker-parity
```

Mount the checkout read-only at `/repo`, that private output directory at `/out`,
and run with `--network none --cap-add SYS_PTRACE --cap-add SYS_ADMIN
--security-opt seccomp=unconfined`. Do not mount host `/opt` or device credentials.
The root job tests use `/opt/couchroot-agent/jobs` inside the disposable container.
Compile and run inside it:

```sh
cc -std=c99 -O1 -g -Wall -Wextra -Werror -Wno-unused-function \
  -DNATIVE_WORKER_TEST -DNATIVE_WORKER_FAULT_TEST \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  /repo/research/autonomous-root/native-worker/worker.c -ldl -pthread -o /out/worker-test-arm64
export ASAN_OPTIONS=detect_leaks=0
export NATIVE_WORKER=/out/worker-test-arm64
export MANAGED_PARITY=/out/managed/Harness.dll
export COUCHROOT_PARITY_CONTAINER=1
export NATIVE_WORKER_FAULT_TEST=1 NATIVE_WORKER_STORAGE_TEST=1
cd /repo
python3 -m unittest discover -s tests -p native_worker_test.py
python3 -m unittest discover -s tests -p native_file_policy_test.py
python3 -m unittest discover -s tests -p worker_parity_test.py
python3 -m unittest discover -s tests -p native_job_migration_test.py
```

The production ARM build still excludes host substitutions and fault controls.

## Production lifetime checks

`native_lifetime_test.py` checks explicit production-mode admission, status,
buffered requests and retained job deadlines. Set
`NATIVE_WORKER_LIFETIME_TEST=1` to additionally exercise an uninterrupted
315-second idle connection with a running job and a stalled partial frame with
owned-job cleanup. Use the same isolated container and `NATIVE_WORKER` path as
above. An ordinary host build needs only `-DNATIVE_WORKER_TEST` for host platform
substitutions; these checks need no fault controls. The 315-second check crosses
the old worker and guardian expiry thresholds; accepting a 24-hour job timeout
and cancelling it is not a completed 24-hour job qualification.

## Slow-storage checks

`native_io_progress_test.py` runs the ordinary host worker with a separate
`LD_PRELOAD` fixture that delays selected local-file syscalls. It exercises slow
hashing and range reads, partial upload writes, blocked reads/flushes, repeated
EINTR, concurrent file-size changes, and a sparse file at the 2 GiB limit. Delays
cross the real 30-second grace; the suite takes several minutes. The fixture is
only in `tests/native-io/delay.c` and is never part of the TV build.

Inside the isolated container described above, build and run:

```sh
cc -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-function \
  -DNATIVE_WORKER_TEST /repo/research/autonomous-root/native-worker/worker.c \
  -ldl -pthread -o /out/worker-io
cc -std=c99 -O2 -Wall -Wextra -Werror -shared -fPIC \
  /repo/tests/native-io/delay.c -ldl -o /out/delay.so
NATIVE_WORKER=/out/worker-io NATIVE_IO_DELAY=/out/delay.so \
  COUCHROOT_PARITY_CONTAINER=1 python3 -m unittest discover \
  -s tests -p native_io_progress_test.py -v
```

These checks do not reproduce TV storage or Smack helper staging. Startup before
guardian activation and durable job-record writes retain their existing bounds;
this is request-side storage progress, not a new storage or startup supervisor.
