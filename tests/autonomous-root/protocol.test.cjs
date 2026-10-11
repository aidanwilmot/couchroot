// Adapted from Vetro 9319cb0, MIT; see research/autonomous-root/service/vendor/LICENSE.
'use strict';
const assert = require('assert').strict;
const EventEmitter = require('events');
const crypto = require('crypto');
const {RootAgentServer} = require('../../research/autonomous-root/service/vendor/root-agent.js');
class Socket extends EventEmitter {
  constructor() { super(); this.writes = []; this.destroyed = false; }
  write(data) { this.writes.push(data); }
  destroy() { this.destroyed = true; this.emit('close'); }
}
function frame(server, socket, payload) {
  const nonce = Buffer.from(socket.writes[0].trim().split('\t')[1], 'hex');
  const mac = crypto.createHmac('sha256', server.secret).update(nonce).update('\x00').update(payload).digest('hex');
  return payload + '\t' + mac + '\n';
}
function authenticate(server, socket) {
  socket.emit('data', Buffer.from(frame(server, socket, 'AUTH\t42\t0\t0\t0\t0\t3fffffffff\tVXNlcg==')));
}
async function main() {
  let failures = 0;
  async function check(name, fn) {
    try { await fn(); console.log('PASS ' + name); }
    catch (e) { failures++; console.error('FAIL ' + name + ': ' + e.message); }
  }
  await check('disconnect rejects pending commands immediately', async () => {
    const server = new RootAgentServer(); const socket = new Socket(); server._handle(socket); authenticate(server, socket);
    const pending = server.execute('id', 1).then(() => 'resolved', () => 'rejected');
    socket.destroy();
    assert.equal(await Promise.race([pending, new Promise(r => setImmediate(() => r('still pending')))]), 'rejected');
    server.close();
  });
  await check('a second peer cannot replace an authenticated agent', async () => {
    const server = new RootAgentServer(); const first = new Socket(); const second = new Socket();
    server._handle(first); server._handle(second); authenticate(server, first); authenticate(server, second);
    assert.equal(server._conn._socket, first); assert.equal(second.destroyed, true);
    first.destroy(); second.destroy(); server.close();
  });
  await check('AUTH and RESULT in one TCP chunk are both processed', async () => {
    let pending;
    const server = new RootAgentServer({onConnect: () => { pending = server.execute('id', 1); }});
    const socket = new Socket(); server._handle(socket);
    socket.emit('data', Buffer.from(frame(server, socket, 'AUTH\t42\t0\t0\t0\t0\t3fffffffff\tVXNlcg==') + frame(server, socket, 'RESULT\t1\t0\t0\tb2s=\t')));
    const result = await Promise.race([pending, new Promise(r => setImmediate(() => r(null)))]);
    socket.destroy(); pending.catch(() => {}); server.close();
    assert.ok(result); assert.equal(result.stdout, 'ok');
  });
  process.exitCode = failures ? 1 : 0;
}
main().catch(e => { console.error(e); process.exitCode = 1; });
