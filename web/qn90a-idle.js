/* Included only by sign.py --profile MinimalHubQN90A. No native timeout setter. */
(function (root) {
  'use strict';
  function install(doc, platform, clock) {
    var timer = null, generation = 0;
    var state = { deadline: null, launches: 0, error: null };
    function cancel() {
      generation++;
      if (timer !== null) { clock.clearTimeout(timer); timer = null; }
      state.deadline = null;
    }
    function activity() {
      cancel();
      if (doc.hidden) { return; }
      state.error = null;
      state.deadline = clock.now() + 300000;
      var current = generation;
      function expired() {
        if (current !== generation || doc.hidden) { return; }
        var remaining = state.deadline - clock.now();
        if (remaining > 0) { timer = clock.setTimeout(expired, remaining); return; }
        timer = null; state.deadline = null;
        try {
          platform.application.launch('MiniSave01.Saver', function () {
            state.launches++;
          }, function (error) {
            if (current === generation) { state.error = error.name || String(error); }
          });
        } catch (error) { state.error = error.name || String(error); }
        // A failed launch is retried only after new input or a visible return.
      }
      timer = clock.setTimeout(expired, 300000);
    }
    ['keydown', 'keyup', 'pointerdown', 'pointermove', 'wheel'].forEach(function (name) {
      doc.addEventListener(name, activity, true);
    });
    doc.addEventListener('visibilitychange', activity);
    activity();
    return state;
  }
  if (typeof module !== 'undefined') { module.exports = install; }
  if (root.document && root.tizen && root.tizen.application) {
    root.QN90AIdleState = install(root.document, root.tizen, {
      now: function () { return root.performance.now(); },
      setTimeout: root.setTimeout.bind(root), clearTimeout: root.clearTimeout.bind(root)
    });
  }
}(typeof window !== 'undefined' ? window : globalThis));
