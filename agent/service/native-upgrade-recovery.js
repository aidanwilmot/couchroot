'use strict';
// Explicit recovery fences the failed launch before restarting either retained
// committed runtime. It never infers success from a missing reply or a PID alone.
const fs = require('fs'),
  path = require('path');
const { privateRead } = require('./private-state');
const { atomic, hash } = require('./policy');
const {
  SelectionJournal,
  selectionStatus,
  nativeCommit,
} = require('./worker-selection');
const { readRuntime } = require('./native-runtime');
const { upgradeStatus } = require('./native-upgrade');
const { startNativeRuntime } = require('./native-startup');
const { fenceCommand } = require('./launch-fence');
const { bootGuard, processAbsenceGuard } = require('./worker-processes');
const {
  recoveryCandidate,
  recoveryCommand,
  completeAcquisitionRecovery,
} = require('./bootstrap-recovery');
const check = (v) => {
  if (!v) throw Error('Native upgrade recovery evidence unavailable');
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function exists(file) {
  try {
    fs.lstatSync(file);
    return true;
  } catch (e) {
    if (e.code === 'ENOENT') return false;
    throw e;
  }
}
function recoveryPlan(selectionFile) {
  const pending = upgradeStatus(selectionFile);
  check(pending);
  const { record: r } = pending,
    directory = path.dirname(selectionFile),
    selected = selectionStatus(selectionFile),
    p = selected.pending;
  check(['stable', 'reconciliation-required'].includes(selected.phase));
  check(
    r.source.record.manifest_sha256 === r.review.from.manifest_sha256 &&
      r.source.record.worker_sha256 === r.review.from.worker_sha256
  );
  const source = readRuntime(directory, r.review.from.id);
  check(
    source.readiness_sha256 === r.review.from.readiness_sha256 &&
      same(source.original, r.source.original)
  );
  const committed =
    !p && selected.selected_manifest_sha256 === r.review.to.manifest_sha256;
  if (p)
    check(
      p.id === r.id &&
        p.from.implementation === 'native-prototype' &&
        p.to.implementation === 'native-prototype' &&
        p.from.manifest_sha256 === r.review.from.manifest_sha256 &&
        p.to.manifest_sha256 === r.review.to.manifest_sha256
    );
  else
    check(
      committed ||
        selected.selected_manifest_sha256 === r.review.from.manifest_sha256
    );
  if (committed)
    check(nativeCommit(selected) && nativeCommit(selected).id === r.id);
  const id = committed ? r.id : r.review.from.id,
    binding = readRuntime(directory, id);
  const activationText = privateRead(
      path.join(directory, id + '.activation.json'),
      16384
    ),
    activation = JSON.parse(activationText);
  const installation = JSON.parse(
    privateRead(path.join(directory, id + '.state-install.json'), 16384)
  );
  check(
    hash(JSON.stringify(installation)) ===
      binding.record.state_receipt_sha256 &&
      activation.readiness_sha256 === binding.readiness_sha256 &&
      activation.id === id &&
      activation.manifest_sha256 === binding.record.manifest_sha256 &&
      same(activation.worker_identity, binding.original.worker_identity)
  );
  // The old immutable commitment must survive the bounded history when a rollback
  // receipt is appended. Refuse instead of publishing an unstartable selection.
  if (p)
    check(
      selected.history
        .slice(-31)
        .some((h) => h.id === id && h.outcome === 'committed')
    );
  return {
    ...pending,
    selected,
    committed,
    candidate: {
      ...binding,
      installation,
      activation: { ...activation, receipt_sha256: hash(activationText) },
      selected,
    },
  };
}
async function recoverUpgrade({ selectionFile, executor }) {
  const plan = recoveryPlan(selectionFile),
    { record: r, candidate } = plan,
    directory = path.dirname(selectionFile);
  const before = JSON.stringify(plan),
    bound = () => check(JSON.stringify(recoveryPlan(selectionFile)) === before);
  const info = await executor.status(),
    boot = info.boot_id;
  bootGuard(boot);
  const run = async (command, expected) => {
    bound();
    const v = await executor.execute(command, 25000);
    bound();
    check(
      v &&
        v.exit_code === 0 &&
        !v.timed_out &&
        !v.stderr &&
        v.stdout === expected
    );
  };
  // Seal even an unacknowledged production submission. The same kernel flock
  // prevents a delayed original launch from racing the empty-unit observation.
  const unit = 'couchroot-worker-' + r.id + '.service';
  const absent =
    bootGuard(boot) +
    'test "$(systemctl show -p MainPID ' +
    unit +
    ')" = MainPID=0\n' +
    'cg=$(systemctl show -p ControlGroup ' +
    unit +
    ' | sed -n "s/^ControlGroup=//p")\ncase "$cg" in "") ;; /system.slice/' +
    unit +
    ') if test -e "/sys/fs/cgroup/systemd$cg/cgroup.procs"; then test "$(wc -l < "/sys/fs/cgroup/systemd$cg/cgroup.procs")" -eq 0; fi;; *) exit 1;; esac\n' +
    (boot !== r.source.record.boot_id
      ? 'test "$(systemctl show -p LoadState ' +
        unit +
        ')" = LoadState=not-found\n'
      : '') +
    (r.candidate
      ? Object.values(r.candidate.worker_identity.processes)
          .map((p) => processAbsenceGuard(p, r.candidate.boot_id, boot))
          .join('')
      : '') +
    'printf "UPGRADE-FENCED\\n"\n';
  await run(
    fenceCommand(
      {
        id: r.id,
        boot_id: r.source.record.boot_id,
        fence: '/opt/couchroot-startup-fence-' + r.id,
      },
      absent,
      { kind: 'startup', seal: true, bootId: boot }
    ),
    'UPGRADE-FENCED\n'
  );
  const nested = path.join(r.directory, 'selection.json');
  if (exists(path.join(r.directory, 'bootstrap-launch.pending'))) {
    const provider = recoveryCandidate(nested, boot);
    check(provider);
    const value = await executor.execute(
      recoveryCommand(provider, { bootId: boot }),
      25000
    );
    check(value && value.exit_code === 0 && !value.timed_out && !value.stderr);
    completeAcquisitionRecovery(nested, provider, boot, value.stdout);
    bound();
  }
  // A committed selection can outlive final token cleanup. Remove only the
  // original, hash-bound token before the ordinary restart creates a fresh one.
  if (plan.committed && !exists(path.join(directory, r.id + '.startup.json'))) {
    const token = candidate.record.token_file,
      folder = path.dirname(token);
    if (exists(folder)) {
      check(
        fs.readdirSync(folder).join('|') === 'token' &&
          hash(privateRead(token, 44)) === candidate.record.token_sha256
      );
      fs.unlinkSync(token);
      fs.rmdirSync(folder);
    }
  }
  // Retained state and process absence are independently verified by the normal
  // startup path. No failed candidate staging or historical receipt is removed.
  const result = await startNativeRuntime({
    selectionFile,
    executor,
    candidate,
    assertCandidate: bound,
  });
  // Finalize only after the caller retires this new recovery bootstrap using the
  // verified runtime. Persisted startup receipts make another interruption safe.
  const finish = () => {
    const current = recoveryPlan(selectionFile);
    check(current.record.id === r.id);
    const journal = new SelectionJournal(selectionFile);
    let s = journal.read();
    if (s.pending) {
      if (
        !['rollback-required', 'rollback-state-ready'].includes(s.pending.phase)
      )
        s = journal.advance(
          s.revision,
          r.id,
          'rollback-required',
          hash(JSON.stringify(result.record.worker_identity))
        );
      if (s.pending.phase === 'rollback-required')
        s = journal.advance(
          s.revision,
          r.id,
          'rollback-state-ready',
          candidate.record.state_receipt_sha256
        );
      journal.commitRollback(s.revision, r.id, candidate.readiness_sha256);
    }
    for (const name of ['state-install.pending', 'production-launch.pending']) {
      const file = path.join(directory, name);
      if (exists(file)) {
        check(privateRead(file, 64) === r.id + '\n');
        fs.unlinkSync(file);
      }
    }
    // Preserve every receipt and failed candidate scope for inspection. Only this
    // transaction's admission marker is released after selection is durable.
    atomic(plan.file, {
      ...r,
      phase: plan.committed ? 'committed' : 'rolled-back',
    });
    const marker = path.join(directory, 'native-upgrade.pending');
    check(privateRead(marker, 33) === r.id + '\n');
    fs.unlinkSync(marker);
    const fd = fs.openSync(directory, 'r');
    try {
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    result.selection = JSON.stringify(selectionStatus(selectionFile));
    check(nativeCommit(selectionStatus(selectionFile)).id === result.record.id);
  };
  result.finish = finish;
  return result;
}
module.exports = { recoveryPlan, recoverUpgrade };
