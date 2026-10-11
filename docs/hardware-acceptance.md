# Owner-supervised hardware acceptance

This is a proposed acceptance procedure, **not authorization to execute it**.
No physical apply/rollback/reboot testing was performed during release preparation.
Use a separate private evidence directory and record the exact source commit,
CLI version, compiler versions and artifact hashes. Publish only a redacted result
table. Never attach raw journals, device identities, certificates or pairing data.

## Entry gates

- Finish disclosure/licensing review before any public artifact is distributed.
- Keep the current working installation, its original checkout and private
  backups available. Confirm the operator can reach Samsung Home and recover the
  device if Hub cannot launch. Do not test interruptions without a proven recovery
  route; a backup archive alone does not prove recoverability.
- Test one device at a time on its exact model/firmware. Keep the other device
  observing/ingesting. Do not allow another management host or automatic updater
  to mutate state during the test.
- Independently enroll signing trust and confirm matching signed forward-recovery
  packages. Preserve newly edited application data. Do not treat file archives as
  reinstall packages or force an installer to downgrade.
- QN90A: review the newly built saver core before accepting its differing digest.
  S90D: establish a reproducible compiler/sysroot/vendor-library recipe before
  accepting a new renderer. Do not relax resource/signature guards for testing.

## Stage 1: baseline and bounded diagnostics

Run `plan`, `status` and ordinary `verify` with the private site file. Record
unsupported or unavailable observations as failures, not absent configuration.
After explicit authorization for diagnostic staging, verify the new root runner
once per model. Confirm namespace/resource boundaries, preserved bytes and labels,
and complete cleanup. Stop if cleanup is uncertain; investigate before another
privileged invocation.

## Stage 2: minimal configuration, reapply and rollback

Prepare one small reversible proposal excluding optional-app cleanup and shared
NAS updates. Review the exact proposal, backups and recovery artifacts before
authorizing apply. Verify both the requested change and unrelated preserved state.
Reapply the same choices: expect no device mutations. Edit an unrelated setting
and application data, then roll back: those edits must survive.

On a separate recoverable run, edit a setting managed by the run before rollback.
Expect refusal to overwrite that drift. Preserve the later value and evidence;
do not bypass the conflict check to make the test pass. Verify local saved choices
and ownership ledger restore to their pre-run values after successful rollback.

## Stage 3: controlled interruption and recovery

Offline failure injection already covers these state transitions. Physical tests
are still required for firmware, installer, filesystem and namespace behavior.
Coordinate any deliberate fault with the owner and recovery operator.

| Boundary | Required result |
| --- | --- |
| Before durable mutation intent | No mutation submitted; new apply blocked if a run remains pending |
| During backup | No forward mutation; verify backup integrity before recovery |
| Mutation finished, reply lost | Readback recognizes completion; no duplicate submission |
| Outcome unchanged but uncertain | No implicit retry; inspect logs/installer before authorizing retry |
| Partial or foreign state | Stop; preserve evidence and later changes |
| Inverse finished, reply lost | Resume rollback; reconcile state and repeat required reload only |
| Complete staged payload left behind | Accept only the run-specific expected digest; recreate metadata and verify |
| Partial/unknown staged payload | Refuse automatic deletion/replacement; owner inspects it |
| Device changes complete, local writes fail | Run stays pending; resume finalization without TV contact |
| Local inverse interrupted | Restore original choices/ledger, including original absence |
| Second local invocation | Lock refusal before mutation |

Exercise unreachable device, slow transport and storage failure separately from
ordinary success. Do not simulate full storage by filling a TV's filesystem.
Use a bounded host test volume for local journal failures. Concurrent mutation
from independent management hosts remains unsupported.

## Stage 4: signed apps and model-specific runtime

Authorize installation/update tests separately. Confirm enrollment, forward
update, certificate renewal and signed forward recovery, including preservation
of user data. Optional-app removal requires separate authorization and a tested
Store/reinstall route; the reviewed allowlist remains mandatory.

Authorize exactly one full reboot for each observation test. Verify a new boot ID
and independent startup evidence without launching Hub or starting the collector.
Test slow/disconnected observation and remote diagnostic cleanup after host cutoff.

| Device | Runtime acceptance |
| --- | --- |
| QN85QN90AAFXZA / 2301.1 | Signed welcome-process relay; Hub → telemetry relay → service; Home and both AirPlay return paths; dashboard-owned five-minute saver |
| QN55S90DAFXZA / 2130.0 | Its own startup/splash acknowledgement and screensaver integration; independently reviewed S90D resources |
| Both | Streaming, standby/wake, input response, original Samsung Home fallback, privacy preferences and disabled telemetry |

Never apply S90D writable-cache assumptions or offsets to QN90A. Configuration
readback and runtime acceptance are separate results; a passing mock or a manual
launch does not establish autonomous startup.

## Stage 5: shared NAS, separately authorized

Fresh NAS provisioning is still a separate engineering milestone. Start from a
reviewed installation with unique credentials and enrolled certificates; do not
replay a historical compose file. Capture both devices' chart/history continuity,
registry, compose, credential records and volume ownership before changes.

Review and explicitly authorize the shared proposal. Test forward restart and
partial-batch rollback while the other TV keeps sending. Account for the brief
receiver interruption, verify ingestion resumes for both, and confirm no history,
credentials, endpoints, registry mapping or user configuration was replaced.

## Acceptance record

For each stage record: source/artifact versions, exact supported combination,
expected result, observed result, recovery outcome, operator and date. Keep the
private run identifier in private evidence only. A failed stage blocks the
corresponding supported scope; it is not waived by a successful build or unit test.
Release authorization remains a separate owner decision after every P0 is closed.
