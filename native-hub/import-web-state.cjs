'use strict';
// Offline conversion of an explicit localStorage export. Never reads browser
// databases, reaches a TV, or writes back to the web Hub.
const fs = require('node:fs');
const Model = require('../web/model.js');
function convert(storage) {
  if (!storage || typeof storage !== 'object' || Array.isArray(storage)) throw new Error('Expected an object containing exported localStorage keys');
  let apps = Model.defaults;
  const raw = storage[Model.KEY];
  if (raw !== undefined) {
    if (typeof raw !== 'string') throw new Error('Shortcut export must retain the localStorage string value');
    const saved = JSON.parse(raw);
    if (!saved || saved.version !== 1 || !Array.isArray(saved.apps)) throw new Error('Unsupported shortcut export');
    apps = saved.apps;
  }
  if (apps.length > 128) throw new Error('Native currently supports 128 favorites; refusing to truncate this export');
  if (!Model.nativeApps(apps)) throw new Error('Invalid, duplicate, reserved or oversized shortcut; export was not changed');
  const lines = apps.map(app => app.id + '\t' + app.name);
  function choice(key, values, fallback) {
    const value = storage['minimal-hub.' + key + '.v1'];
    if (value === undefined) return fallback;
    if (typeof value !== 'string' || !Object.hasOwn(values, value)) throw new Error('Unsupported ' + key + ' preference');
    return values[value];
  }
  const compact = choice('layout', {comfortable: 0, compact: 1}, 0);
  const clock = choice('clock', {off: 0, '12h': 1, '24h': 2}, 0);
  const first = choice('start', {last: 0, first: 1}, 0);
  const selected = Math.max(0, apps.findIndex(a => a.id === storage['minimal-hub.selection.v1']));
  return `COUCHROOT1 ${compact} ${clock} ${first} ${selected}\n` + (lines.length ? lines.join('\n') + '\n' : '');
}
module.exports = {convert};
if (require.main === module) {
  try {
    const [input, output, ...extra] = process.argv.slice(2);
    if (!input || !output || extra.length) throw new Error('Usage: node import-web-state.cjs exported-storage.json /private/native-state');
    if (fs.statSync(input).size > 1024 * 1024) throw new Error('Export is too large');
    const state = convert(JSON.parse(fs.readFileSync(input, 'utf8')));
    fs.writeFileSync(output, state, {flag: 'wx', mode: 0o600});
    console.log('Created native preference candidate. Web data and existing native files were not modified.');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
