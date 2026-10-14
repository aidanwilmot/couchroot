# Observer deployment gate

The observer is packaged but not enabled by `service/main.js`. A successful host
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
