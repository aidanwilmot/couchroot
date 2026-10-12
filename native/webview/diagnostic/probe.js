(function () {
  'use strict';
  var buttons = Array.prototype.slice.call(document.querySelectorAll('button'));
  var selection = 0;
  var started = performance.now();
  function supports(property, value) {
    try { return !!(window.CSS && (value === undefined ? CSS.supports(property) : CSS.supports(property, value))); }
    catch (_) { return false; }
  }
  var lines = [
    'User agent: ' + navigator.userAgent,
    ':has(): ' + supports('selector(:has(*))'),
    'Container queries: ' + supports('container-type', 'inline-size'),
    'Tizen application API: ' + !!(window.tizen && window.tizen.application)
  ];
  // The native host logs document.title changes; the page has no other channel.
  function publish(text) { document.title = 'diag ' + text; }
  function report(text) { document.getElementById('input').textContent = text; publish('input ' + text); }
  buttons.forEach(function (button, index) {
    button.addEventListener('focus', function () { selection = index; });
    button.addEventListener('click', function () { report('Activated ' + button.textContent); });
  });
  document.addEventListener('keydown', function (event) {
    var key = event.key;
    if (key === 'ArrowRight' || key === 'ArrowDown' || key === 'ArrowLeft' || key === 'ArrowUp') {
      event.preventDefault();
      selection = (selection + ((key === 'ArrowRight' || key === 'ArrowDown') ? 1 : buttons.length - 1)) % buttons.length;
      buttons[selection].focus();
      report('Focused ' + buttons[selection].textContent);
    } else if (key === 'Escape' || key === 'XF86Back' || event.keyCode === 10009) {
      event.preventDefault(); selection = 0; buttons[0].focus(); report('Back received');
    } else { report('Key received: ' + key + ' (' + event.keyCode + ')'); }
  });
  document.addEventListener('visibilitychange', function () { publish('visibility ' + document.visibilityState); });
  buttons[0].focus();
  document.getElementById('features').textContent = lines.join('\n');
  publish('ready ' + lines.slice(1).join('; ') + '; ' + lines[0]);
  requestAnimationFrame(function () { requestAnimationFrame(function () {
    lines.push('Two animation frames after script start: ' + (performance.now() - started).toFixed(1) + ' ms (not physical paint)');
    document.getElementById('features').textContent = lines.join('\n');
    publish('frames ' + (performance.now() - started).toFixed(1) + ' ms');
  }); });
}());
