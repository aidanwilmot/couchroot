# Native worker upgrades

Installing an agent package does not change the committed native worker. Use an
explicit upgrade after reviewing both executable hashes. An agent package that
includes this API must be installed first; older packages cannot activate it.

## Review and apply

Use the device's enrollment **client.json** for these commands. The package trial
tool separately takes an enrollment **folder**. Keep evidence outside the repo.

```sh
python3 -m tvsetup.native_upgrade review --device s90d --credentials "$CLIENT"
python3 -m tvsetup.native_upgrade apply --device s90d --credentials "$CLIENT" \
  --review-sha256 "$REVIEW_SHA256" --evidence "$PRIVATE/new-upgrade" --yes
python3 -m tvsetup.native_upgrade status --device s90d --credentials "$CLIENT"
```

Replace `s90d` with `qn90a` for that device. Review is read-only. Apply submits one
request, with a private local intent written first. A submitted request is not a
successful upgrade. Never resubmit an uncertain request: inspect status and the
retained evidence. Each new mutation needs a new evidence directory.

The agent requires stable native selection, verified package artifacts and the
exact review digest and loopback SDK access for recovery. It holds public requests, refuses in-flight requests and
nonterminal jobs, transfers or helpers, and verifies the old executable. A bounded
native bootstrap maintains root access while the old worker shuts down. Retained
job records are copied byte-for-byte into a fresh scope; jobs are not replayed.
The new worker's authenticated identity, executable inode and hash, service unit,
launcher and retained records are verified before selection is committed.

The old executable, scope and historical receipts remain intact. Only the new
transaction's files change. The upgrade provider does not use `on-demand`.
Normal agent acquisition/recovery may create and retire its own archive files;
it must preserve unrelated files. Do not accept an unexplained inventory change
or replace a previously reviewed fingerprint to make recovery pass.

## Interrupted upgrade

```sh
python3 -m tvsetup.native_upgrade recover --device s90d --credentials "$CLIENT" \
  --evidence "$PRIVATE/new-recovery" --yes
python3 -m tvsetup.native_upgrade status --device s90d --credentials "$CLIENT"
```

Recovery closes this coordinator's transports and uses the existing loopback SDK
acquisition path. **Developer Mode host must be loopback**, with the normal
firmware and acquisition prerequisites satisfied. This command does not change
Developer Mode, reboot, or install a package. Arrange any maintenance-window and
SDK-host restoration sequence separately, with owner approval.

Recovery seals the failed launch against delayed execution and verifies that its
unit and recorded processes are absent. It restarts the old committed worker if
selection was not committed, or completes the newly committed selection otherwise.
The existing native startup path verifies retained state on the same or a new
boot. Uncertain ownership, live remnants, invalid receipts or a selection writer
left by an uncertain publication cause refusal; recovery does not kill guessed
PIDs, repair receipts or bypass guards. Keep the previous package and its trial
journal for failures that prevent acquisition itself.

Failed candidate scopes and receipts remain quarantined for inspection. They are
not reused or automatically garbage-collected. This intentionally avoids another
cleanup/migration system in the upgrade path.

## Return to the previous worker

A completed upgrade can be reversed with another reviewed native handoff:

```sh
python3 -m tvsetup.native_upgrade review --device s90d --credentials "$CLIENT" \
  --target previous
python3 -m tvsetup.native_upgrade apply --device s90d --credentials "$CLIENT" \
  --target previous --review-sha256 "$REVIEW_SHA256" \
  --evidence "$PRIVATE/return-previous" --yes
```

This stages the retained executable in a fresh scope and copies the current
retained job records. It does not restore a stale jobs snapshot or roll back the
agent package. Package rollback remains a separate operation through the original
setup journal and retained signed package.

## Hardware acceptance

S90D agent 0.7.54 passed forward/reverse native handoffs, root command/job checks,
retained-job preservation and unattended reboot on 2026-10-21. The native gate
and actual running worker hash were verified; Hub/telemetry files and registrations
were preserved, and telemetry resumed. QN90A acceptance and hardware interruption
fault injection remain pending. See [the acceptance record](../project/release-readiness.md).

**Check service startup flags after a package update.** The S90D installer left
on-boot/auto-restart registration false even though the manifest specified true.
Reboot acceptance passed only after a separately reviewed correction with backup
and recovery. Package installation or a successful live handoff does not prove
unattended startup; stop and review a correction if those flags are wrong.


Local tests and simulated transports do not qualify a TV release. On each model,
with separately reviewed scripts and owner approval:

1. Record boot ID, SDK host, selected manifest, running executable hash and a
   file-level inventory of unrelated agent files. Resolve existing drift first.
2. Verify package inventory, review/apply the upgrade, then check native gate,
   actual `/proc/<pid>/exe` hash, root identity and committed selection.
3. Exercise one root command and one job, and check Hub and telemetry.
4. Exercise reviewed interruption recovery and a return to the previous worker.
5. Reboot using the shared reboot command and confirm unattended native startup
   on the new boot, correct hash and unchanged unrelated files.

Stop at the first failed check. A successful local suite or read-only inspection
is not evidence that upgrade, recovery or reboot acceptance has passed on hardware.
