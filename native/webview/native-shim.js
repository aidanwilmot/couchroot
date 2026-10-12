/* Native WebView adapter for the shipped Hub UI. Loaded after bridge.js only in
 * the native bundle. It supplies HubBridge with the two platform calls it uses
 * (application.getAppsInfo and application.launch) over the native host's
 * channel: requests via document.title, replies via HubNativePlatform.receive.
 * Inactive in the signed WGT (window.tizen exists) and in a plain browser
 * (the host adds ?host=native-webview). Feedback and telemetry receive no
 * platform object, exactly as in the desktop preview. */
(function (root) {
  'use strict';
  var search = root.location && typeof root.location.search === 'string' ? root.location.search : '';
  if (root.tizen || !/[?&]host=native-webview(&|$)/.test(search) || !root.HubBridge) { return; }

  // One-time import of the native launcher's preferences, offered by the host in
  // the URL fragment. Applied only when this WebView has no saved shortcuts, and
  // only with values hub.js itself writes. The fragment is then dropped.
  (function importNative() {
    var match = /^#import=(.*)$/.exec(root.location.hash || '');
    if (!match) { return; }
    try {
      var data = JSON.parse(decodeURIComponent(match[1])), store = root.localStorage;
      var id = /^[A-Za-z0-9_.-]{1,256}$/, apps = data && data.shortcuts && data.shortcuts.apps;
      var valid = store && store.getItem('minimal-hub.shortcuts.v1') === null && data.shortcuts.version === 1 &&
        Object.prototype.toString.call(apps) === '[object Array]' && apps.length <= 128 &&
        apps.every(function (app) {
          return app && id.test(app.id) && typeof app.name === 'string' && app.name.length && app.name.length <= 120 &&
            !/[\x00-\x1f\x7f]/.test(app.name);
        }) &&
        ['comfortable', 'compact'].indexOf(data.layout) >= 0 && ['off', '12h', '24h'].indexOf(data.clock) >= 0 &&
        ['first', 'last'].indexOf(data.start) >= 0 && (data.selection === undefined || id.test(data.selection));
      if (valid) {
        store.setItem('minimal-hub.shortcuts.v1', JSON.stringify({ version: 1, apps: apps.map(function (app) { return { id: app.id, name: app.name }; }) }));
        store.setItem('minimal-hub.layout.v1', data.layout);
        store.setItem('minimal-hub.clock.v1', data.clock);
        store.setItem('minimal-hub.start.v1', data.start);
        if (data.selection) { store.setItem('minimal-hub.selection.v1', data.selection); }
      }
    } catch (_) { /* Malformed or storage unavailable: the Hub uses its own data. */ }
    try { root.history.replaceState(null, '', root.location.pathname + root.location.search); } catch (_) {}
  }());

  var TIMEOUT = 12000; // Longer than the host's worker bounds; hub.js keeps its own 8 s / 10 s guards.
  var queue = [], current = null, counter = 0;

  function failure(name, message) { var error = new Error(message || name); error.name = name; return error; }
  function next() {
    if (current || !queue.length) { return; }
    current = queue.shift();
    current.timer = setTimeout(function () { settle(current.id, null, failure('UnknownError', 'The native host did not respond.')); }, TIMEOUT);
    // One message at a time, each with a fresh id, so no title change is lost or repeated.
    root.document.title = 'hubbridge:1:' + current.id + ':' + current.op + (current.arg ? ':' + current.arg : '');
  }
  function settle(id, value, error) {
    if (!current || current.id !== id) { return; } // Stale or unknown reply.
    var request = current; current = null; clearTimeout(request.timer);
    try { if (error) { request.reject(error); } else { request.resolve(value); } }
    finally { next(); }
  }
  function request(op, arg, resolve, reject) {
    queue.push({ id: 'r' + (++counter), op: op, arg: arg, resolve: resolve, reject: reject });
    next();
  }
  function receive(message) {
    if (!message || message.v !== 1 || typeof message.id !== 'string' || !current || message.id !== current.id) { return; }
    if (message.ok === true) { settle(message.id, message, null); return; }
    var error = message.error || {};
    var names = ['NotFoundError', 'InvalidValuesError', 'UnknownError', 'NotSupportedError', 'SecurityError'];
    settle(message.id, null, failure(names.indexOf(error.name) >= 0 ? error.name : 'UnknownError',
      typeof error.message === 'string' ? error.message.slice(0, 200) : ''));
  }
  function text(value, limit) { return typeof value === 'string' && value.length <= limit ? value : ''; }

  var platform = {
    application: {
      getAppsInfo: function (success, error) {
        request('discover', '', function (reply) {
          var apps = Object.prototype.toString.call(reply.apps) === '[object Array]' ? reply.apps : [];
          success(apps.slice(0, 128).map(function (app) {
            return { id: text(app && app.id, 256), name: text(app && app.name, 120), iconPath: text(app && app.iconPath, 512),
              packageId: text(app && app.packageId, 256), show: !!(app && app.show === true) };
          }));
        }, error);
      },
      launch: function (id, success, error) {
        if (typeof id !== 'string' || !/^[A-Za-z0-9_.-]{1,256}$/.test(id)) { error(failure('InvalidValuesError', 'Unknown app')); return; }
        request('launch', id, function () { success(); }, error);
      }
    }
  };
  var create = root.HubBridge.create;
  root.HubBridge.create = function (given) { return create(given || platform); };
  var readySent = false;
  root.HubNativePlatform = { receive: receive, ready: function () {
    if (readySent) { return; }
    readySent = true;
    // Wait for layout/fonts, then signal before the next paint. The host still
    // requires EWK's subsequent rendered-frame callback before mapping.
    function painted() {
      root.requestAnimationFrame(function () { request('ready', '', function () {}, function () {}); });
    }
    if (root.document.fonts && root.document.fonts.ready) { root.document.fonts.ready.then(painted, painted); }
    else { painted(); }
  } };
}(typeof window !== 'undefined' ? window : globalThis));
