'use strict';
// Explicit native-to-native handoff. Historical receipts and old scopes survive.
const fs = require('fs'),
  path = require('path'),
  crypto = require('crypto');
const { hash, atomic } = require('./policy');
const { privateRead, privateDirectory } = require('./private-state');
const { SelectionJournal, selectionStatus } = require('./worker-selection');
const { startupCandidate } = require('./native-startup');
const { readRuntime } = require('./native-runtime');
const { loadCandidate } = require('./native-candidate');
const { processIdentities, bootGuard } = require('./worker-processes');
const {
  validateReadiness,
  validateResourceInventory,
} = require('./worker-readiness');
const { prepareProductionExit } = require('./production-exit');
const { snapshotNativeJobs } = require('./native-retained-state');
const { planInstallation } = require('./retained-install');
const { submitProduction } = require('./production-launch');
const { readyProduction } = require('./production-readiness');
const { openProductionSession } = require('./production-session');
const { openUpgradeProvider } = require('./native-upgrade-provider');
const check = (v) => {
  if (!v) throw Error('Native upgrade evidence unavailable');
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function sync(directory) {
  const fd = fs.openSync(directory, 'r');
  try {
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}
function targetRuntime(selectionFile, source) {
  const directory = path.dirname(selectionFile),
    prior = JSON.parse(
      privateRead(
        path.join(directory, source.record.id + '.upgrade.json'),
        524288
      )
    );
  check(
    prior.id === source.record.id &&
      prior.phase === 'committed' &&
      prior.review.to.manifest_sha256 === source.record.manifest_sha256
  );
  const retained = readRuntime(directory, prior.review.from.id);
  check(
    retained.readiness_sha256 === prior.review.from.readiness_sha256 &&
      same(retained.original, prior.source.original)
  );
  return retained.record;
}
function reviewUpgrade({
  selectionFile,
  payload,
  device,
  target: choice = 'package',
}) {
  check(['package', 'previous'].includes(choice));
  const source = startupCandidate(selectionFile);
  check(source);
  const retained =
    choice === 'previous' ? targetRuntime(selectionFile, source) : null;
  const target = retained
    ? {
        manifest_sha256: retained.manifest_sha256,
        artifacts: {
          'native-worker': { sha256: retained.worker_sha256 },
          'native-app-launcher': { sha256: retained.launcher_sha256 },
        },
      }
    : loadCandidate(payload, device);
  check(
    source &&
      target &&
      source.record.device === device &&
      source.record.manifest_sha256 !== target.manifest_sha256
  );
  const review = {
    schema: 1,
    device,
    target: choice,
    selection_sha256: hash(privateRead(selectionFile, 65536)),
    from: {
      id: source.record.id,
      manifest_sha256: source.record.manifest_sha256,
      worker_sha256: source.record.worker_sha256,
      readiness_sha256: source.readiness_sha256,
      activation_sha256: source.activation.receipt_sha256,
    },
    to: {
      manifest_sha256: target.manifest_sha256,
      worker_sha256: target.artifacts['native-worker'].sha256,
      launcher_sha256: target.artifacts['native-app-launcher'].sha256,
    },
    recovery: 'retained-native-runtime',
  };
  return { ...review, sha256: hash(JSON.stringify(review)) };
}
function upgradeStatus(selectionFile) {
  const directory = path.dirname(selectionFile),
    marker = path.join(directory, 'native-upgrade.pending');
  let id;
  try {
    id = privateRead(marker, 33).trim();
  } catch (e) {
    if (e.code === 'ENOENT') return null;
    throw e;
  }
  check(/^[a-f0-9]{32}$/.test(id));
  const file = path.join(directory, id + '.upgrade.json'),
    record = JSON.parse(privateRead(file, 524288));
  check(
    record.schema === 1 &&
      record.id === id &&
      record.review &&
      record.source &&
      record.directory === path.join(directory, 'upgrade-' + id)
  );
  return { file, record };
}
async function runUpgrade({
  selectionFile,
  payload,
  device,
  reviewSha256,
  hold,
  retain,
  target = 'package',
}) {
  const directory = path.dirname(selectionFile),
    marker = path.join(directory, 'native-upgrade.pending');
  check(
    privateDirectory(fs.lstatSync(directory)) && !upgradeStatus(selectionFile)
  );
  const review = reviewUpgrade({ selectionFile, payload, device, target });
  check(review.sha256 === reviewSha256);
  const source = startupCandidate(selectionFile),
    journal = new SelectionJournal(selectionFile);
  let state = journal.read(),
    record,
    provider,
    production,
    begun = false;
  const save = (phase, extra = {}) => {
    hold.check();
    record = { ...record, ...extra, phase };
    atomic(path.join(directory, record.id + '.upgrade.json'), record);
  };
  try {
    const info = await hold.status();
    validateReadiness(info, {
      implementation: 'native-prototype',
      bootId: source.record.boot_id,
      launcherSha256: source.record.launcher_sha256,
    });
    check(
      same(processIdentities(info, hold.pid), source.record.worker_identity)
    );
    const resources = validateResourceInventory(info);
    check(
      resources.jobs.every(
        (j) =>
          j.monitor_finished &&
          ['completed', 'cancelled', 'timed_out', 'interrupted'].includes(
            j.state
          )
      ) &&
        !resources.transfers.length &&
        !resources.helpers.length
    );
    check(hash(privateRead(selectionFile, 65536)) === review.selection_sha256);
    const id = crypto.randomBytes(16).toString('hex'),
      local = path.join(directory, 'upgrade-' + id);
    record = {
      schema: 1,
      id,
      phase: 'prepared',
      review,
      source,
      directory: local,
    };
    // Recovery uses the normal loopback acquisition path after transport loss.
    // A surviving worker with SDK still pointed at a development host is not a
    // sufficient recovery prerequisite.
    const sdk = await hold.execute(
      'set -eu\n' +
        bootGuard(source.record.boot_id) +
        'vconftool get db/sdk/develop/ip | grep -Fx "db/sdk/develop/ip, value = 127.0.0.1 (String)"\n',
      5000
    );
    check(
      sdk &&
        sdk.exit_code === 0 &&
        !sdk.timed_out &&
        !sdk.stderr &&
        sdk.stdout === 'db/sdk/develop/ip, value = 127.0.0.1 (String)\n'
    );
    check(
      source.selected.history
        .slice(-31)
        .some((h) => h.id === source.record.id && h.outcome === 'committed')
    );
    begun = true;
    atomic(path.join(directory, id + '.upgrade.json'), record);
    fs.writeFileSync(marker, id + '\n', { mode: 0o600, flag: 'wx' });
    sync(directory);
    state = journal.begin(
      state.revision,
      {
        implementation: 'native-prototype',
        manifest_sha256: review.to.manifest_sha256,
      },
      hash(JSON.stringify(info)),
      id
    );
    fs.mkdirSync(local, { mode: 0o700 });
    sync(directory);
    save('provider-submitted');
    provider = await openUpgradeProvider({
      payload,
      device,
      selectionFile,
      directory: local,
      bootId: source.record.boot_id,
      execute: hold.execute,
    });
    if (retain) retain(provider.channel);
    const execute = provider.execute;
    provider.execute = async (c, t) => {
      hold.check();
      const r = await execute(c, t);
      hold.check();
      return r;
    };
    save('provider-ready', { bootstrap: provider.record });
    const exit = await prepareProductionExit({
      record: source.record,
      execute: provider.execute,
    });
    const sourceHash =
      'set -eu\n' +
      bootGuard(source.record.boot_id) +
      Object.values(source.record.worker_identity.processes)
        .map(
          (p) =>
            'test /proc/' +
            p.pid +
            '/exe -ef ' +
            source.record.directory +
            '/code/worker\n' +
            'test "$(sha256sum /proc/' +
            p.pid +
            '/exe | cut -d " " -f1)" = ' +
            source.record.worker_sha256 +
            '\n'
        )
        .join('') +
      'printf "UPGRADE-SOURCE-VERIFIED\n"\n';
    const verified = await provider.execute(sourceHash, 5000);
    check(
      verified &&
        verified.exit_code === 0 &&
        !verified.timed_out &&
        !verified.stderr &&
        verified.stdout === 'UPGRADE-SOURCE-VERIFIED\n'
    );
    save('source-stop-submitted');
    const stopped = await hold.shutdown();
    check(stopped.acknowledged && stopped.disconnected);
    await exit.waitForExit();
    save('source-stopped');
    const original = await snapshotNativeJobs({
      record: source.record,
      installation: source.installation,
      execute: provider.execute,
    });
    // The common importer accepts the exact native records; origin is retained in
    // the upgrade receipt rather than disguised as a managed snapshot.
    const body = {
      schema: 1,
      implementation: 'native-prototype',
      source: original.source,
      records: original.records,
    };
    const snapshot = { ...body, sha256: hash(JSON.stringify(body)) };
    const plan = planInstallation({
      snapshot,
      id,
      manifestSha256: review.to.manifest_sha256,
    });
    atomic(path.join(directory, id + '.retained-snapshot.json'), snapshot);
    save('state-submitted', { snapshot: original });
    fs.writeFileSync(path.join(directory, 'state-install.pending'), id + '\n', {
      mode: 0o600,
      flag: 'wx',
    });
    sync(directory);
    const run = async (command, expected) => {
      const r = await provider.execute(command, 25000);
      check(
        r &&
          r.exit_code === 0 &&
          !r.timed_out &&
          !r.stderr &&
          r.stdout === expected
      );
    };
    await run(plan.begin, 'STATE-PENDING\n');
    for (const command of plan.copies) await run(command, 'STATE-RECORD\n');
    check(
      same(
        original,
        await snapshotNativeJobs({
          record: source.record,
          installation: source.installation,
          execute: provider.execute,
        })
      )
    );
    await run(plan.commit, 'STATE-READY\n');
    await run(plan.inspect, 'STATE-READY\n');
    const installation = {
        ...plan.record,
        quiescence_sha256: state.pending.quiescence_sha256,
        phase: 'ready',
      },
      receipt = hash(JSON.stringify(installation));
    atomic(path.join(directory, id + '.state-install.json'), installation);
    state = journal.advance(state.revision, id, 'state-ready', receipt);
    save('state-ready');
    production = await openProductionSession({
      id,
      device,
      payload,
      journalDirectory: directory,
      selectionFile,
      manifestSha256: review.to.manifest_sha256,
      receiptSha256: receipt,
      retainedRuntime:
        target === 'previous' ? targetRuntime(selectionFile, source) : null,
      provider: {
        identity: provider.record.worker_identity,
        launchProduction: async (options) => {
          save('candidate-submitted');
          return submitProduction({ ...options, execute: provider.execute });
        },
        verifyProduction: (options) =>
          readyProduction({
            ...options,
            record: JSON.parse(
              privateRead(path.join(directory, id + '.production.json'), 16384)
            ),
            execute: provider.execute,
            providerIdentity: provider.record.worker_identity,
          }),
        completeUpgrade: async ({ channel, record: ready }) => {
          if (retain) retain(channel);
          save('candidate-ready', { candidate: ready });
          save('provider-retirement-submitted');
          await provider.retire(channel);
          save('provider-retired');
        },
      },
    });
    const ready = production.record;
    const activation = {
      schema: 1,
      id,
      phase: 'active',
      boot_id: ready.boot_id,
      manifest_sha256: ready.manifest_sha256,
      readiness_sha256: production.readiness_sha256,
      worker_identity: ready.worker_identity,
      upgrade_sha256: hash(JSON.stringify(record)),
    };
    // Publication is ordered: verification, provider retirement, receipts, then
    // selection. Any interruption keeps native-upgrade.pending holding admission.
    save('commit-submitted');
    atomic(path.join(directory, id + '.activation.json'), activation);
    state = journal.read();
    check(
      state.pending &&
        state.pending.id === id &&
        state.pending.phase === 'trial-ready'
    );
    journal.commit(state.revision, id);
    const channel = await production.takeChannel();
    const token = ready.token_file;
    check(hash(privateRead(token, 44)) === ready.token_sha256);
    fs.unlinkSync(token);
    fs.rmdirSync(path.dirname(token));
    for (const name of ['state-install.pending', 'production-launch.pending']) {
      const p = path.join(directory, name);
      check(privateRead(p, 64) === id + '\n');
      fs.unlinkSync(p);
    }
    save('committed');
    check(privateRead(marker, 33) === id + '\n');
    fs.unlinkSync(marker);
    sync(directory);
    const selected = startupCandidate(selectionFile);
    await hold.adopt({
      channel,
      record: ready,
      activation: selected.activation,
      selection: JSON.stringify(selected.selected),
      info: await channel.operation({ op: 'status' }),
    });
    return {
      transaction_id: id,
      phase: 'committed',
      worker_sha256: ready.worker_sha256,
    };
  } catch (cause) {
    if (!begun) hold.release();
    // Do not replay or erase an uncertain step. Keep the old scope and all receipts.
    throw Object.assign(
      Error(
        begun
          ? 'Native upgrade requires reconciliation'
          : 'Native upgrade rejected'
      ),
      { outcome: begun ? 'unknown' : 'rejected', cause }
    );
  }
}
module.exports = { reviewUpgrade, upgradeStatus, runUpgrade };
