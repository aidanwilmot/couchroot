/* Only included in an explicitly signed diagnostic build. No network or UI. */
(function (root) {
  'use strict';
  var perf = root.performance;
  var now = perf && typeof perf.now === 'function' ? function () { return perf.now(); } : function () { return Date.now(); };
  var started = now(), finished = false, frames = 0;
  var report = { schema: 1, id: String(Date.now()) + '-' + Math.random().toString(16).slice(2, 10), clock: perf && perf.now ? 'performance.now' : 'wall-clock-fallback', wallStart: Date.now(), perfStart: started, events: [] };
  function timing() {
    try {
      // Values are relative to navigation, including work before this script.
      var nav = perf.getEntriesByType('navigation')[0];
      if (nav) {
        report.navigation = {};
        ['startTime', 'duration', 'fetchStart', 'responseStart', 'responseEnd', 'domInteractive', 'domContentLoadedEventStart', 'domContentLoadedEventEnd', 'domComplete', 'loadEventStart', 'loadEventEnd'].forEach(function (key) { report.navigation[key] = nav[key]; });
      }
      report.paint = perf.getEntriesByType('paint').slice(0, 4).map(function (entry) { return { name: entry.name, startTime: entry.startTime }; });
      report.resources = perf.getEntriesByType('resource').slice(0, 24).map(function (entry) { return { name: entry.name.split('/').pop(), startTime: entry.startTime, responseEnd: entry.responseEnd, duration: entry.duration }; });
    } catch (_) { /* Older engines may omit navigation or paint entries. */ }
  }
  function mark(name) {
    if (finished || report.events.length >= 64) { return; }
    report.events.push({ name: name, ms: now() - started, wall: Date.now(), visible: !document.hidden, focus: document.hasFocus() });
  }
  function save() {
    if (finished) { return; }
    mark('trace-end'); timing(); finished = true;
    try {
      var key = 'minimal-hub.boot-traces.v1', old = JSON.parse(localStorage.getItem(key) || '[]');
      if (!Array.isArray(old)) { old = []; }
      old.push(report); localStorage.setItem(key, JSON.stringify(old.slice(-3)));
      // Single ASCII record is retrievable from the offline package storage snapshot.
      localStorage.setItem('minimal-hub.boot-trace.latest.v1', 'BOOTTRACEv1:' + JSON.stringify(report));
    } catch (_) { /* Trace must never break startup, including full storage. */ }
  }
  root.HubBootTrace = { mark: mark, report: report };
  mark('script-entry');
  document.addEventListener('DOMContentLoaded', function () { mark('dom-content-loaded'); });
  document.addEventListener('visibilitychange', function () { mark('visibility'); });
  root.addEventListener('focus', function () { mark('window-focus'); });
  root.addEventListener('blur', function () { mark('window-blur'); });
  document.addEventListener('keydown', function firstKey() { mark('first-key'); document.removeEventListener('keydown', firstKey, true); }, true);
  if (root.requestAnimationFrame) {
    root.requestAnimationFrame(function frame() { mark('animation-frame-' + (++frames)); if (frames < 2) { root.requestAnimationFrame(frame); } });
  }
  setTimeout(save, root.HUB_BOOT_TRACE_MS || 120000);
}(window));
