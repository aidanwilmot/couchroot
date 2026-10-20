// Native adapter against the real web/bridge.js. No TV, browser, or host process.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const bridgeSource = fs.readFileSync(path.join(__dirname, '../../../web/bridge.js'), 'utf8');
const shimSource = fs.readFileSync(path.join(__dirname, '../native-shim.js'), 'utf8');

function load({ search = '?host=native-webview', tizen, hash = '', storage = {}, HubBridge = true } = {}) {
  const titles = [], timers = new Map(), replaced = [], classes = new Set();
  let nextTimer = 0;
  const window = {
    location: { search, hash, pathname: '/opt/hub/index.html' },
    localStorage: {
      getItem: key => Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null,
      setItem: (key, value) => { storage[key] = String(value); }
    },
    history: { replaceState: (state, title, url) => replaced.push(url) },
    document: { set title(value) { titles.push(value); }, get title() { return titles[titles.length - 1] || ''; },
      documentElement: { classList: { add: name => classes.add(name) } } },
    setTimeout: (fn, ms) => { timers.set(++nextTimer, { fn, ms }); return nextTimer; },
    clearTimeout: id => timers.delete(id),
    tizen
  };
  window.window = window;
  const context = vm.createContext(Object.assign(window, { Object, Error, Array, String, JSON }));
  if (HubBridge) { vm.runInContext(bridgeSource, context); }
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../../web/model.js'), 'utf8'), context);
  vm.runInContext(shimSource, context);
  const fire = () => { const [id, timer] = [...timers][0]; timers.delete(id); timer.fn(); };
  return { window, titles, timers, fire, storage, replaced, classes };
}
function capture() {
  const calls = [];
  // JSON round trip: values come from the vm realm's prototypes.
  return { calls, ok: value => calls.push(['ok', JSON.parse(JSON.stringify(value))]), fail: error => calls.push(['fail', error.name, error.message]) };
}

// Inactive in the signed WGT and in a plain browser.
{
  const wgt = load({ tizen: { application: {} } });
  assert.equal(wgt.window.HubNativePlatform, undefined);
  const browser = load({ search: '' });
  assert.equal(browser.window.HubNativePlatform, undefined);
  assert.equal(browser.window.HubBridge.create(undefined).preview, true);
}

// Discovery goes through bridge.js's own consumer filter, sort and icon rules.
{
  const { window, titles } = load();
  const bridge = window.HubBridge.create(undefined);
  assert.equal(bridge.preview, false);
  const result = capture();
  bridge.discover(result.ok, result.fail);
  assert.deepEqual(titles, ['hubbridge:1:r1:discover']);
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: true, apps: [
    { id: 'kIciSQlYEM.plex', name: 'Plex', iconPath: '/opt/plex.png', packageId: 'kIciSQlYEM', show: true },
    { id: 'org.tizen.netflix-app', name: 'Netflix', iconPath: 'http://remote.invalid/x.png', packageId: 'org.tizen.netflix-app', show: true },
    { id: 'org.tizen.factory', name: 'Factory', iconPath: '', packageId: 'org.tizen.factory', show: true },
    { id: 'AbCdEfGhIj.x', name: 'Hidden', iconPath: '', packageId: 'AbCdEfGhIj', show: false },
    { id: 'MiniHub001.Hub', name: 'Hub', iconPath: '', packageId: 'MiniHub001', show: true }
  ] });
  assert.deepEqual(result.calls, [['ok', [
    { id: 'org.tizen.netflix-app', name: 'Netflix', icon: '' },
    { id: 'kIciSQlYEM.plex', name: 'Plex', icon: '/opt/plex.png' }
  ]]]);
}

// Launch uses the ordinary path (no app-control constructors are supplied);
// the host decides the quiet-launch hint. Requests are serialized.
{
  const { window, titles } = load();
  const bridge = window.HubBridge.create(undefined);
  const first = capture(), second = capture();
  bridge.launchApp({ id: 'kIciSQlYEM.plex', name: 'Plex' }, first.ok, first.fail);
  bridge.discover(second.ok, second.fail);
  assert.deepEqual(titles, ['hubbridge:1:r1:launch:kIciSQlYEM.plex']);
  window.HubNativePlatform.receive({ v: 1, id: 'r9', ok: true });       // Stale/unknown: ignored.
  window.HubNativePlatform.receive({ v: 2, id: 'r1', ok: true });       // Wrong version: ignored.
  assert.deepEqual(first.calls, []);
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: true });
  assert.deepEqual(first.calls, [['ok', { preview: false, name: 'Plex' }]]);
  assert.deepEqual(titles, ['hubbridge:1:r1:launch:kIciSQlYEM.plex', 'hubbridge:1:r2:discover']);
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: true });       // Duplicate: ignored.
  window.HubNativePlatform.receive({ v: 1, id: 'r2', ok: false, error: { name: 'UnknownError', message: 'x'.repeat(500) } });
  assert.equal(second.calls[0][1], 'UnknownError');
  assert.equal(second.calls[0][2].length, 200);
}

// Error names are passed through only from the known set; invalid ids never leave the page.
{
  const { window, titles } = load();
  const bridge = window.HubBridge.create(undefined);
  const failed = capture();
  bridge.launchApp({ id: 'kIciSQlYEM.plex', name: 'Plex' }, failed.ok, failed.fail);
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: false, error: { name: '<script>', message: 'no' } });
  assert.deepEqual(failed.calls, [['fail', 'UnknownError', 'no']]);
  const invalid = capture();
  bridge.launchApp({ id: 'bad id', name: 'Bad' }, invalid.ok, invalid.fail);
  assert.equal(invalid.calls[0][0], 'fail');
  assert.equal(titles.length, 1);
}

// A silent host times out, frees the slot, and a late reply is ignored.
{
  const { window, titles, fire } = load();
  const bridge = window.HubBridge.create(undefined);
  const first = capture(), second = capture();
  bridge.discover(first.ok, first.fail);
  bridge.discover(second.ok, second.fail);
  fire();
  assert.deepEqual(first.calls, [['fail', 'UnknownError', 'The native host did not respond.']]);
  assert.equal(titles[1], 'hubbridge:1:r2:discover');
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: true, apps: [] });
  assert.deepEqual(second.calls, []);
  window.HubNativePlatform.receive({ v: 1, id: 'r2', ok: true, apps: 'not-a-list' });
  assert.deepEqual(second.calls, [['ok', []]]);
}
// One-time preference import from the native launcher.
{
  const offer = { shortcuts: { version: 1, apps: [{ id: 'kIciSQlYEM.plex', name: 'Plex' }, { id: '9Ur5IzDKqV.TizenYouTube', name: 'YouTube' }] },
    layout: 'compact', clock: '24h', start: 'last', selection: '9Ur5IzDKqV.TizenYouTube' };
  const hash = '#import=' + encodeURIComponent(JSON.stringify(offer));
  const fresh = load({ hash });
  assert.deepEqual(fresh.storage, {
    'minimal-hub.shortcuts.v1': JSON.stringify({ version: 1, apps: offer.shortcuts.apps }),
    'minimal-hub.layout.v1': 'compact', 'minimal-hub.clock.v1': '24h', 'minimal-hub.start.v1': 'last',
    'minimal-hub.selection.v1': '9Ur5IzDKqV.TizenYouTube'
  });
  assert.deepEqual(fresh.replaced, ['/opt/hub/index.html?host=native-webview']);
  // Existing WebView data always wins; nothing is overwritten.
  const existing = { 'minimal-hub.shortcuts.v1': '{"version":1,"apps":[]}' };
  const kept = load({ hash, storage: existing });
  assert.deepEqual(kept.storage, { 'minimal-hub.shortcuts.v1': '{"version":1,"apps":[]}' });
  // Invalid offers are ignored entirely.
  for (const bad of [{ ...offer, clock: 'noon' }, { ...offer, shortcuts: { version: 1, apps: [{ id: 'bad id', name: 'x' }] } }]) {
    assert.deepEqual(load({ hash: '#import=' + encodeURIComponent(JSON.stringify(bad)) }).storage, {});
  }
  assert.deepEqual(load({ hash: '#import=%7Bnot-json' }).storage, {});
  // Not applied outside the native host.
  assert.deepEqual(load({ hash, search: '' }).storage, {});
}
console.log('Native shim: inactive outside host, discovery/launch through bridge.js, serialization, stale/timeout/error handling passed');

// Readiness waits for fonts and an animation frame, shares the serialized
// channel, and is sent once even if startup calls it again.
{
  const { window, titles } = load();
  let fontsReady, frame;
  window.document.fonts = { ready: { then: fn => { fontsReady = fn; } } };
  window.requestAnimationFrame = fn => { frame = fn; };
  window.HubNativePlatform.ready();
  window.HubNativePlatform.ready();
  assert.deepEqual(titles, []);
  fontsReady();
  assert.deepEqual(titles, []);
  const bridge = window.HubBridge.create(undefined);
  bridge.discover(() => {}, () => {});
  frame();
  assert.deepEqual(titles, ['hubbridge:1:r1:discover']);
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: true, apps: [] });
  assert.deepEqual(titles, ['hubbridge:1:r1:discover', 'hubbridge:1:r2:ready']);
  window.HubNativePlatform.receive({ v: 1, id: 'r2', ok: true });
}

// The rendered Home is revealed by ready(); 'painted' follows its presented
// first contentful paint, or a bounded fallback without paint timing.
{
  const { window, titles, timers, classes } = load();
  let observed, observing;
  window.PerformanceObserver = function (callback) { observed = callback; this.observe = options => { observing = options; }; this.disconnect = () => { observed = null; }; };
  window.requestAnimationFrame = fn => fn();
  assert.equal(classes.size, 0); // The static markup stays transparent until the Hub has rendered.
  window.HubNativePlatform.ready();
  assert.deepEqual([...classes], ['native-hub-rendered']);
  assert.deepEqual(JSON.parse(JSON.stringify(observing)), { type: 'paint', buffered: true });
  assert.deepEqual(titles, ['hubbridge:1:r1:ready']);
  observed({ getEntriesByName: name => name === 'first-paint' ? [{}] : [] }); // Not contentful: keep waiting.
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: true });
  assert.deepEqual(titles, ['hubbridge:1:r1:ready']);
  observed({ getEntriesByName: name => name === 'first-contentful-paint' ? [{}] : [] });
  assert.deepEqual(titles, ['hubbridge:1:r1:ready', 'hubbridge:1:r2:painted']);
  window.HubNativePlatform.receive({ v: 1, id: 'r2', ok: true });
  const [fallback] = [...timers.values()].filter(timer => timer.ms === 3000);
  fallback.fn(); // Already sent once: no duplicate.
  assert.equal(titles.length, 2);
}
{
  const { window, titles, fire, timers } = load(); // No paint timing support at all.
  window.requestAnimationFrame = fn => fn();
  window.HubNativePlatform.ready();
  assert.deepEqual(titles, ['hubbridge:1:r1:ready']);
  window.HubNativePlatform.receive({ v: 1, id: 'r1', ok: true });
  const id = [...timers].find(([, timer]) => timer.ms === 3000)[0];
  timers.get(id).fn();
  assert.equal(titles[titles.length - 1], 'hubbridge:1:r2:painted');
}
// Where the shim stays inactive, nothing may remain hidden.
for (const options of [{ tizen: { application: {} } }, { search: '' }, { HubBridge: false }]) {
  assert.deepEqual([...load(options).classes], ['native-hub-rendered']);
}
console.log('Native shim: rendered-Home reveal, presented-paint confirmation and fallbacks passed');

// The same entry fixture also drives native storage, import and web-model tests.
for (const vector of require('../../../tests/fixtures/preferences.json')) {
  const data={shortcuts:{version:1,apps:vector.apps},layout:'comfortable',clock:'off',start:'last',selection:vector.apps.length?vector.apps[0].id:''};
  const {storage}=load({hash:'#import='+encodeURIComponent(JSON.stringify(data))});
  assert.equal(Object.hasOwn(storage,'minimal-hub.shortcuts.v1'),vector.native,vector.name);
}
