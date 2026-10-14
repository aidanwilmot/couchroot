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
