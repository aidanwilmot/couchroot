# Observer deployment gate

The observer is packaged; `service/main.js` now selects its staging path for an
explicit internal S90D handoff. Startup alone does not stage or launch it. A successful host
build or matching-credential probe is not evidence that the installed service can
launch it. Both supported TVs still need actual service-side staging/launch and
handoff validation. Keep the managed worker as the deployed fallback.

Adding native artifacts and service modules changes the signed package inventory.
The existing shared agent updater refuses that by default. Review the exact pair
of independently verified signed packages before allowing a changed inventory:

```sh
python3 -m tvsetup.autonomous_root_trial --device qn90a \
  --artifact /absolute/private/new-package \
  --previous /absolute/private/installed-package --review-inventory
```

This verifies local target bindings, package hashes, signatures and forward
version, then reports additions, removals and a digest covering both complete
member inventories and contents. It does not contact a TV. Inspect the report;
changed existing members also change its digest. Repeat separately for S90D.

For an authorized update, pass that exact digest with
`--reviewed-inventory-sha256 DIGEST`, the original enrollment's `--credentials`
directory, and `--yes` to the same update command without `--review-inventory`.
Do not substitute a newly generated candidate enrollment for the existing one.
This option does not bypass the disabled-baseline check, current installed-file
comparison, device lock, pending-run checks, signature checks or recovery archive.
Preparation verifies both signed inventories again. The journal records the
review and the union of old and new paths, including explicit absence for added
files before update and removed files after update. Unexpected leftovers or
missing additions fail readback. No file is removed by an ad hoc cleanup command.

Before invoking update, quiesce current requests/jobs, establish the disabled
baseline through the existing guarded workflow, retain the verified signed
recovery package and verify recovery access. Review any uncertain prior outcome
instead of resubmitting it. Restore the existing enrollment and enabled state only
after installation/readback. No reboot is required or authorized by this gate.

The inventory tests exercise review binding, drift refusal, union readback and
rollback observation locally. They do not prove that the TV installer removes
old members or that a forward-signed rollback completes on hardware. Those are
separate deployment observations. Observer executability, Smack context and
permissions also remain TV qualification items.

## Preparation evidence — 2026-10-14

Both TVs answered ready status, and read-only package-layout inspection preserved
their original worker, process and boot identities. Independently signed 0.6.1
candidates were prepared against the retained signed 0.6.0 packages. Both reviews
contain ten additions (four native payload/manifest files and six service modules)
and no removals. Artifacts, review digests and raw device evidence remain private;
neither package was installed.

On both devices the package directory belongs to installer UID 201 and existing
service source files have mode 0644. The app data directory belongs to UID 5001
and has mode 2755. The signed archives do not preserve a usable executable mode
for the observer. Do not infer service executability from a signed member hash.
The selection writer's private-parent requirement also needs a dedicated 0700
subdirectory rather than changing the existing app data directory's permissions.
Resolve both staging details before invoking an installed-service handoff.

The subsequent service bootstrap creates `data/worker-state` privately and uses
`data/worker-state/worker-selection.json`. It validates app ownership, rejects
group/other write access on the app data directory, syncs directory publication
and leaves existing data permissions and enrollment unchanged. Only a newly
created child's inherited setgid bit is cleared. An existing private 2700 child
can be reused unchanged after an interrupted creation; public, linked or wrongly
owned state directories are refused.

Any legacy `data/worker-selection.json` or `.writer` entry, including a dangling
link, prevents startup until reconciliation. The bootstrap neither migrates nor
deletes it. Pending selection and writer markers in the private directory remain
authoritative. Local state/selection/readiness tests passed (32 checks), and the
seven bootstrap checks also passed under UID 5001/GID 100 in Linux. This does not
qualify TV Smack behavior. The earlier signed candidates predate this new service
module and must be rebuilt and inventory-reviewed before deployment.

## Transaction-bound permission staging

For S90D's internal handoff, the held service checks the prepared native target's
manifest hash, validates the packaged observer, and asks the still-connected root
worker to enable execute permission on that exact installed package member. Only
the two known package layouts are accepted. The command checks boot, parent
components, regular-file type, installer UID 201, single link, expected hash and
mode 0644 or 0755 before changing the mode to 0755. It checks the same inode,
ownership, length, digest, mode and boot afterward; the service revalidates the
candidate manifest before binding pidfds. Bytes, labels and mounts are unchanged.
The executable belongs to the installed package rather than a helper directory
that worker shutdown would remove. Installer write permission is preserved.

Staging runs only after a prepared transaction and drained inventory are bound to
the held worker. Target/version changes, an uncertain command result or failed
readback leave admission held and prevent staging retry. The prepared journal
still blocks acquisition after service restart. There is no arbitrary staging API
or native selection activation. QN90A keeps its proc-stat observation path.

Local tests cover real mode changes on an installer-owned, source-built candidate
in an isolated container, refusal cases, no automatic retry, and transaction
binding. The staging/readiness/state/candidate run passed 35 checks; the final
handoff-target drift test passed in the 15-check readiness rerun. Twelve real-wire
observer/shutdown checks also passed. The staged ARM binary was not executed in
those staging tests; wire tests use the ordinary host build. TV service execution
and its signature/label rules remain unqualified. No TV was contacted in this step.

## Non-disruptive service probe

The new enrolled-client `observer-probe` command invokes `/v1/observer/probe` with
a request ID and expected installed manifest hash. The service journals it before
staging, holds admission, and exercises its own observer launch. S90D binds pidfds,
confirms current identity, then cancels/reaps only the observer. QN90A checks the
observer's fixed invalid-arguments response and observes the current worker using
proc-stat. Fresh status confirms the same worker remains after the probe, then
admission is released. The operation never invokes worker shutdown or changes
selection. An unknown staging/observer outcome leaves admission held; a confirmed
child-execution failure is reported separately and can release the hold.

Local validation passed 30 API/readiness/state tests, 17 Linux staging/observer/
wire tests, and a five-case managed-session rerun including both probe methods.
The probe integration uses the actual managed session and host-built observer;
only package permission staging is substituted there, and tested separately on
ARM candidate bytes. The repository runner passed 248 tests and skipped 88
environment-dependent checks. These results do not qualify TV service execution.
Rebuild and review signed candidates containing this endpoint before deployment.

Signed 0.6.1 candidates were subsequently rebuilt for both profiles at source
`e3062b9`. Verification against each retained signed 0.6.0 package found twelve
added members and no removals: the four native payload/manifest members and eight
service modules. Both managed payloads remain present; managed remains selected.
The content-bound inventory reviews and signed packages are retained privately.
These replace the earlier prepared candidates, which lacked the latest probe.

Read-only HTTPS observations before and after preparation confirmed both TVs
ready and connected, with unchanged boot ID, worker ID, process identity and
last acquisition time. No package was installed and neither TV was rebooted.
Installation still requires the shared update transaction, preservation of the
current enrollment/configuration, verified maintenance access and signed recovery
material. Successful preparation is not installed-service qualification.

## QN90A installed-service failure — 2026-10-14

The first update preflight rejected the saved 0.6.0 baseline before installation:
the TV actually had 0.7.0. A retained signed 0.7.0 package matched every installed
member. Both candidates were rebuilt as 0.7.1 against that baseline; the unused
0.6.1 candidates are obsolete. QN90A's 0.7.1 update and installed-content readback
passed, with managed selection and original enrollment preserved. S90D remains
on 0.7.0; its 0.7.1 candidate has not been installed.

The first QN90A observer probe lost its response and left the request journal at
`submitted`. HTTPS became unavailable. The owner subsequently rebooted the TV;
the service acquired a ready managed worker on the new boot. This was not an
agent-requested reboot. Subsequent readback verified all 34 tracked package
members, enrollment, protected files, startup flags and the restored loopback
SDK host setting. Neither the old request nor its outcome was rewritten.

A separate diagnostic request on the recovered boot reproduced the disconnect.
Before submission, independent systemd log capture, service-start and SDK-rescue
timers were confirmed active. The managed endpoint recovered on the same boot
with a new worker identity. Both recovery timers were then disarmed. There is no
service-start timer receipt, so recovery must not be attributed to that timer.
The original workflow had disarmed SDK rescue too early; future qualification
must retain independent recovery through the probe and its post-checks.

Bounded kernel snapshots identify SIGSEGV in `MiniRoot01.Service` / `wrt-service`,
with the faulting PC in `libchromium-impl.so` at image offset `0x004d446a` and link
register offset `0x00545595`. A digest-verified copy of the 55,212,354-byte library
was retained privately (SHA-256
`23bee1f3f9ceeae89e273971a6696dd0518365503815ce7eaffa6bdf5fa8e192`).
The observer's installed mode is 755, confirming staging progressed at least to
the permission change. These observations establish a service-runtime crash,
not an observer executable crash or its exact underlying cause. Nearby exported
symbols do not identify the faulting function. No successful probe receipt exists.

All 60 kernel snapshots, 60 process snapshots and the collector completion marker
were archived privately and digest-verified before removing the owned diagnostic
files from the TV. Managed access is restored; native service qualification and
the package update's acceptance remain pending. Do not run the same probe on
S90D based on the local tests or describe the observer launch gate as passed.

## QN90A crash remediation — 2026-10-14

Disassembly of the captured library resolves the caller more precisely than its
exported symbols: the assertion descriptor referenced by the function at
`0x00545574` names `node::HandleWrap::Close(v8::Local<v8::Value>)` and
`third_party/electron_node/src/handle_wrap.cc:75`. Its call at `0x00545590`
enters the handle-close routine at `0x004d43c8`. The faulting instruction reads
offset 196 through the handle's loop pointer. This matches libuv's pending-close
list update. The runtime's handle cleanup is the observed failure boundary;
the truncated kernel snapshot does not establish why that pointer was invalid.

The application defect was running an unnecessary `execFile` smoke test before
QN90A's proc-stat qualification. Its production handoff already uses proc-stat;
native subprocess execution is not a prerequisite for that method. The probe now
uses the same process observation as the handoff, retaining manifest-bound
staging, held admission, and fresh worker/boot identity checks on both sides.
It does not claim to qualify native executable launch on QN90A. S90D's distinct
pidfd launch path remains unchanged and requires its own device qualification.

Regression tests require no executable or pidfd launch for QN90A, even when
those launch functions would fail, and reject unreadable or replaced processes.
They retain the existing uncertain-outcome admission hold and S90D launch checks.

The signed 0.7.2 remediation was installed on QN90A through the shared update
engine. Three separately journaled probes passed with method `proc-stat`, the
same managed worker and boot, and admission released after each probe. A subsequent
managed command succeeded. Readback verified all 34 tracked package members,
enrollment, protected files, startup flags and the loopback SDK setting. Independent
SDK recovery remained armed through validation and was then disarmed. The two
earlier submitted/unknown probe records were preserved without replay or rewriting.
Neither TV was rebooted during remediation. S90D remains healthy on 0.7.0.

The prior 0.7.1 installation was reconciled as an installed managed fallback with
observer qualification explicitly failed. The 0.7.2 journal is complete for this
proc-stat remediation only; native launch and full migration are not accepted.
Local validation passed 30 focused Linux tests, including actual managed-worker
handoff, pidfd protocol and retained-record checks. The tracked-file privacy audit
reported no findings across 548 files. Raw evidence and signed artifacts remain
outside Git.

## S90D installed-runtime qualification — 2026-10-14

The signed 0.7.1 candidate was installed through the shared updater with managed
selection retained. Before its one-shot probe, independent bounded kernel/process
capture, service-start and SDK recovery timers were confirmed active. The request
lost its response. Captured kernel evidence identifies SIGSEGV in `wrt-service`
inside `libchromium-impl.so`, followed by approximately 21 seconds waiting for
the platform core-dump configuration. This establishes the failing runtime, not
the exact underlying instruction or cause on S90D.

The managed service recovered on the same boot with a new worker. The independent
service-start timer produced a successful-launch receipt. Recovery timers were
disarmed after managed readiness and loopback SDK readback. All 60 kernel and 60
process snapshots, the completion marker and restart receipt were archived and
digest-verified before removing the collector's named files. The uncertain probe
record remains submitted and must not be replayed or treated as passed.

Direct child-process observation is therefore unavailable in the installed TV
runtime. `main.js` explicitly disables that transport. S90D probe and internal
handoff now reject before staging, spawning or stopping the worker; probe admission
is released with a known rejection. Host-only pipe-bridge tests remain useful for
the observer protocol, but do not override this installed-runtime restriction.
QN90A continues using its qualified proc-stat path.

The next integration must provide an external observer launch transport that
survives worker shutdown. It must preserve manifest-bound executable identity,
bounded authenticated communication, bind-before-confirm-before-arm sequencing,
service-equivalent observation credentials, and cancellation of the observer only.
Neither a bare PID nor a worker's shutdown acknowledgement can replace independent
exit observation. No native selection or .NET retirement is accepted by these tests.

The guard was deployed as S90D 0.7.2 through the shared updater. Its installed probe
returned a known rejection with a completed failure journal entry, unchanged worker
and boot, and released admission. A following managed command succeeded. All 34
tracked package members, enrollment, protected files, startup flags and restored
loopback SDK setting verified. Recovery remained armed through the probe and was
then disarmed. Both TVs ended ready on managed workers, without an agent-requested
reboot. The S90D update journal is complete for the guard only, explicitly leaving
observer launch and native migration unqualified. Local Linux tests passed 31
focused service/observer/managed-wire checks. The tracked-file privacy audit
reported no findings across 548 files.

## External observer credential preflight — 2026-10-14

The signed 0.7.3 integration was installed on S90D with managed selection and
independent recovery retained. Its single journaled non-stopping probe failed
before listener creation or launch submission: the service receives EACCES when
opening `/proc/self/status`. The service remained connected with admission held;
no observer submission marker was created. Disabling and enabling the agent
restored a ready managed worker on the same boot. The request's unknown result
was preserved, not replayed or rewritten. All 39 signed package members,
enrollment, protected files, startup flags and loopback SDK configuration verified.
Bounded diagnostics were archived and digest-verified before exact-file cleanup.
The update journal is complete only for the installed managed fallback; observer
qualification failed and native migration remains unaccepted.

Credential capture now uses the authenticated held worker to read the explicit
service PID's status and label. It compares PID, real/effective/saved/filesystem
UID/GID, supplementary groups, label and effective capabilities for the explicit
JavaScript process PID. The external launch shell no longer reads procfs
under the package label. Systemd enforces the configured label, no-new-privileges,
and empty capability bounds/ambient capabilities. Before arming, the controller
uses the held worker to inspect the running supervisor's actual credentials and
then obtains fresh worker identity confirmation. Local validation passes 61
focused Linux tests; this correction still requires installed-runtime qualification.

The signed 0.7.4 correction reached the credential-profile comparison but rejected
before creating a listener or submitting a launch. Managed access was restored on
the same boot. Independent kernel readback matches the intended service profile,
and the actual captured record passes the parser locally. The remaining mismatch
is in the combined runtime/kernel comparison; the exact WRT getter discrepancy
has not been established. Credential checks now use the explicit current service
PID's kernel record as the authoritative source, and compare the supervisor's
kernel record against it. The fixed UID/GID, label, zero-capability and group
constraints remain enforced. A regression test makes WRT group getters throw;
credential validation must not consult them. Installed qualification remains open.


The signed 0.7.5 kernel-record revision also rejected the credential profile before
launch. This disproves attributing the failure solely to WRT credential getters.
The exact lookup mismatch remains unresolved. Local source now resolves the caller
PID using `readlink('/proc/self')` and reports the specific mismatching credential
field and PID. Tests deliberately give the runtime a different `process.pid`;
only the kernel link may determine the lookup. This PID correction is not deployed.

A separate S90D systemd test under the matching UID, primary group and package label
successfully read `/proc/self` as a link. It also demonstrated that systemd merges
account-default supplementary groups with `SupplementaryGroups=`, producing extra
groups and duplicates. The launch shell's exact-group check would reject that
profile. Preserve the check: the native launcher must explicitly install the
captured group list and drop credentials before observing processes. No such
credential-drop mode is implemented yet. The diagnostic unit exited normally;
raw identity output remains private.

S90D remains on 0.7.5 with a ready managed worker. Each unsuccessful probe retains
its submitted/unknown request record without replay. Neither TV rebooted, no
observer launch was submitted, and native selection remains disabled. The 0.7.5
package, enrollment, protected files, startup flags and loopback settings were
verified; bounded collector evidence was archived and its owned files removed.
The update journal accepts only the installed managed fallback, not the observer
or migration. Local PID/profile validation passes all 61 focused Linux tests.
