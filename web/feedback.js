/* Short local sine tones, scheduled after paint; no downloads or volume changes. */
(function (root) {
  'use strict';
  var KEY = 'minimal-hub.sound.v1';
  function create(platform, storage, schedule, now, makeAudio) {
    var enabled = true, available = false;
    var Audio = root.AudioContext || root.webkitAudioContext, context = null;
    makeAudio = makeAudio || (Audio ? function () { return new Audio(); } : null);
    available = !!makeAudio;
    // Native extension access can block during cold boot. Our local tones use
    // Web Audio, so inspect the native fallback only when Web Audio is absent.
    if (!available) {
      try { available = !!(platform && platform.tvaudiocontrol && typeof platform.tvaudiocontrol.playSound === 'function'); } catch (_) { /* Unsupported/denied audio is silent. */ }
    }
    function tone(type) {
      if (!enabled || (root.document && root.document.hidden)) { return; }
      var start = context.currentTime, duration = type === 'SELECT' ? .10 : .075;
      var oscillator = context.createOscillator(), gain = context.createGain();
      oscillator.type = 'sine'; oscillator.frequency.setValueAtTime(type === 'SELECT' ? 420 : type === 'BACK' ? 260 : 320, start);
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(type === 'SELECT' ? .045 : .035, start + .012);
      gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
      oscillator.connect(gain); gain.connect(context.destination);
      oscillator.onended = function () { oscillator.disconnect(); gain.disconnect(); };
      oscillator.start(start); oscillator.stop(start + duration + .005);
    }
    function sound(type) {
      if (!makeAudio) { platform.tvaudiocontrol.playSound(type); return; }
      if (!context) { context = makeAudio(); }
      if (context.state === 'suspended') {
        context.resume().then(function () { try { tone(type); } catch (_) { available = false; } }, function () { available = false; });
      } else { tone(type); }
    }
    var queued = false, pending = 'MOVE', last = -Infinity;
    try { enabled = storage.getItem(KEY) !== 'off'; } catch (_) { /* Keep the user-requested default. */ }
    now = now || Date.now;
    schedule = schedule || function (task) {
      if (typeof requestAnimationFrame === 'function') { requestAnimationFrame(function () { setTimeout(task, 0); }); }
      else { setTimeout(task, 0); }
    };
    return {
      enabled: function () { return enabled; },
      toggle: function () {
        var next = !enabled; storage.setItem(KEY, next ? 'on' : 'off'); enabled = next; return enabled;
      },
      play: function (type) {
        if (!enabled || !available) { return; }
        // Coalesce held-key events. Selection/Back takes priority over movement.
        if (!queued || type !== 'MOVE') { pending = type; }
        if (queued) { return; }
        queued = true;
        schedule(function () {
          queued = false;
          if (!enabled || (pending === 'MOVE' && now() - last < 90)) { return; }
          try { sound(pending); last = now(); }
          catch (_) { available = false; } // Audio never blocks navigation.
        });
      }
    };
  }
  root.HubFeedback = { create: create, KEY: KEY };
  if (typeof module !== 'undefined') { module.exports = root.HubFeedback; }
}(typeof window !== 'undefined' ? window : globalThis));
