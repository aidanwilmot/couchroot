const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/boot-trace.js', 'utf8');
function fixture(storage, entries) {
  let ms = 10, finish;
  const events = {};
  const context = { performance: { now: () => ms }, document: { hidden: false, hasFocus: () => true, addEventListener: (n, f) => { events[n] = f; }, removeEventListener() {} }, localStorage: storage, addEventListener() {}, setTimeout: f => { finish = f; }, Date, Math, JSON };
  context.window = context;
  if (entries) { context.performance.getEntriesByType = type => entries[type] || []; }
  vm.runInNewContext(source, context);
  return { context, finish: () => { ms = 120010; finish(); }, advance: n => { ms += n; } };
}
test('diagnostic saves once in separate keys and preserves app preferences', () => {
  const data = new Map([['minimal-hub.shortcuts.v1', 'keep']]); let writes = 0;
  const f = fixture({ getItem: k => data.get(k), setItem: (k,v) => { data.set(k,v); writes++; } });
  f.advance(20); f.context.HubBootTrace.mark('initial-dom-render'); f.finish(); f.finish();
  assert.equal(data.get('minimal-hub.shortcuts.v1'), 'keep'); assert.equal(writes, 2);
  const report = JSON.parse(data.get('minimal-hub.boot-trace.latest.v1').slice(12));
  assert.equal(report.events[1].ms, 20); assert.equal(report.events.at(-1).name, 'trace-end');
});
test('diagnostic event count is bounded and storage failure is harmless', () => {
  const f = fixture({ getItem() { throw Error('unavailable'); }, setItem() { throw Error('full'); } });
  for(let i=0;i<100;i++) f.context.HubBootTrace.mark('visibility');
  assert.equal(f.context.HubBootTrace.report.events.length,64);
  assert.doesNotThrow(f.finish);
});
test('diagnostic includes work before script execution and bounds resource metadata', () => {
  const data = new Map();
  const f = fixture({ getItem: k => data.get(k), setItem: (k, v) => data.set(k, v) }, {
    navigation: [{ startTime: 0, responseEnd: 4, domInteractive: 30 }],
    paint: [{ name: 'first-contentful-paint', startTime: 48 }],
    resource: Array.from({ length: 100 }, () => ({ name: 'file:///private/package/style.css', startTime: 1, responseEnd: 8, duration: 7 }))
  });
  f.finish();
  const report = JSON.parse(data.get('minimal-hub.boot-trace.latest.v1').slice(12));
  assert.equal(report.navigation.responseEnd, 4);
  assert.equal(report.perfStart, 10);
  assert.equal(report.paint[0].startTime, 48);
  assert.equal(report.resources.length, 24);
  assert.equal(report.resources[0].name, 'style.css');
});
