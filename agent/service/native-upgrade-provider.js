'use strict';
// The existing bounded bootstrap supplies root after the source shuts down.
const fs = require('fs'),
  path = require('path'),
  crypto = require('crypto');
const { RootAgentServer } = require('./root-agent');
const {
  prepareBootstrap,
  bindBootstrap,
  retireBootstrap,
} = require('./held-bootstrap');
const { privateRead } = require('./private-state');
function check(v) {
  if (!v) throw Error('Upgrade provider unavailable');
}
async function openUpgradeProvider({
  payload,
  device,
  selectionFile,
  directory,
  bootId,
  execute,
}) {
  // A private immutable selection snapshot keeps bootstrap recovery independent
  // of the enclosing selection transaction's phase changes.
  const snapshot = path.join(directory, 'selection.json');
  fs.writeFileSync(snapshot, privateRead(selectionFile, 65536), {
    mode: 0o600,
    flag: 'wx',
  });
  const stage =
    '/home/owner/share/tmp/sdk_tools/archive-root-' +
    crypto.randomBytes(8).toString('hex');
  fs.mkdirSync(stage, { mode: 0o700 });
  fs.mkdirSync(stage + '/code', { mode: 0o700 });
  const secret = crypto.randomBytes(32);
  fs.writeFileSync(
    stage + '/root-agent.token',
    secret.toString('base64') + '\n',
    { mode: 0o600, flag: 'wx' }
  );
  let resolve, reject, timer;
  const connected = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  connected.catch(() => {});
  const channel = new RootAgentServer({
    secret,
    bindHost: '127.0.0.1',
    port: 0,
    onConnect: resolve,
    onClose: () => reject(Error('Upgrade bootstrap disconnected')),
  });
  let record;
  try {
    await new Promise((yes, no) => {
      channel.start(yes);
      channel._server.once('error', no);
    });
    const prepared = prepareBootstrap({
      payload,
      device,
      stage,
      port: channel.listeningPort(),
      bootId,
      journalDirectory: directory,
      selectionFile: snapshot,
    });
    record = prepared.record;
    timer = setTimeout(
      () => reject(Error('Upgrade bootstrap deadline')),
      35000
    );
    const result = await execute(prepared.command, 25000);
    check(
      result && result.exit_code === 0 && !result.timed_out && !result.stderr
    );
    await connected;
    record = await bindBootstrap(record, channel, bootId);
    return {
      channel,
      record,
      execute: (c, t) => channel.execute(c, t),
      async retire(next) {
        await retireBootstrap(record, channel, next);
        // Only this provider's known staging files. Never touch on-demand.
        for (const n of [
          'code/native-worker',
          'code/native-app-launcher',
          'root-agent.token',
        ])
          fs.unlinkSync(stage + '/' + n);
        fs.rmdirSync(stage + '/code');
        fs.rmdirSync(stage);
      },
      close: () => channel.close(),
    };
  } catch (error) {
    channel.close();
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
module.exports = { openUpgradeProvider };
