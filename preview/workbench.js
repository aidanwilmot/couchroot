(function () {
  'use strict';
  var select = document.getElementById('scenario'), frame = document.getElementById('hub');
  var stage = document.getElementById('stage'), url = new URL(location.href);
  Object.keys(HubScenarios).forEach(function (name) {
    var option = document.createElement('option'); option.value = name; option.textContent = HubScenarios[name].label; select.appendChild(option);
  });
  var requested = url.searchParams.get('scenario');
  select.value = Object.prototype.hasOwnProperty.call(HubScenarios, requested) ? requested : 'home';
  function show(reset) {
    var link = '/hub?scenario=' + encodeURIComponent(select.value);
    frame.src = link + (reset ? '&reset=1' : '');
    document.getElementById('fullscreen').href = link;
    document.getElementById('activity').textContent = 'No app launches yet.';
    url.searchParams.set('scenario', select.value); history.replaceState(null, '', url);
  }
  select.addEventListener('change', function () { show(true); });
  document.getElementById('reset').addEventListener('click', function () { show(true); });
  window.addEventListener('message', function (event) {
    if (event.origin !== location.origin || event.source !== frame.contentWindow || !event.data || event.data.type !== 'hub-preview-launch') return;
    document.getElementById('activity').textContent = (event.data.failed ? 'Simulated failure: ' : 'Simulated launch: ') + event.data.id;
  });
  new ResizeObserver(function () { frame.style.transform = 'scale(' + stage.clientWidth / 1920 + ')'; }).observe(stage);
  show(false);
}());
