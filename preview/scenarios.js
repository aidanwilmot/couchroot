(function (root) {
  'use strict';
  var scenarios = {
    home: { label: 'Home · two favorites' },
    many: { label: 'Home · full catalog', favorites: 'all' },
    compact: { label: 'Home · compact layout with clock', favorites: 'all', prefs: { 'minimal-hub.layout.v1': 'compact', 'minimal-hub.clock.v1': '12h' } },
    empty: { label: 'Home · no favorites', favorites: 'none' },
    unavailable: { label: 'Home · unavailable app', unavailable: true },
    edit: { label: 'Edit apps', favorites: 'all', screen: 'edit' },
    options: { label: 'Edit apps · move or remove', favorites: 'all', screen: 'options' },
    move: { label: 'Home · moving a shortcut', favorites: 'all', screen: 'move' },
    undo: { label: 'Home · undo removal', screen: 'undo' },
    opening: { label: 'Home · opening an app', launchDelay: 5000, screen: 'opening' },
    hold: { label: 'Settings · hold OK to edit', screen: 'hold', prefs: { 'minimal-hub.hold.v1': 'on' } },
    picker: { label: 'Add apps', screen: 'picker' },
    settings: { label: 'Settings', screen: 'settings' },
    'startup-selection': { label: 'Settings · startup selection', screen: 'start' },
    reset: { label: 'Reset confirmation', screen: 'reset' },
    monitoring: { label: 'TV monitoring', screen: 'monitoring' },
    'launch-error': { label: 'App launch failure', launchFail: true },
    'discovery-error': { label: 'App discovery failure', discoveryFail: true, screen: 'picker' },
    'bad-storage': { label: 'Unreadable saved shortcuts', badStorage: true },
    'missing-artwork': { label: 'Missing app artwork', favorites: 'fallback', missingArtwork: true },
    dock: { label: 'Home · glass dock on a photo', favorites: 'all', prefs: { 'minimal-hub.layout.v1': 'dock', 'minimal-hub.background.v1': 'misty', 'minimal-hub.clock.v1': '12h' } },
    'dock-few': { label: 'Home · dock with two apps', prefs: { 'minimal-hub.layout.v1': 'dock', 'minimal-hub.background.v1': 'peaks' } },
    photo: { label: 'Home · comfortable on a photo', prefs: { 'minimal-hub.background.v1': 'forest' } },
    inputs: { label: 'Home · inputs panel', screen: 'inputs' },
    'inputs-dock': { label: 'Dock · inputs panel', favorites: 'all', screen: 'inputs', prefs: { 'minimal-hub.layout.v1': 'dock', 'minimal-hub.background.v1': 'cove' } },
    'inputs-missing': { label: 'Inputs · switch helper not installed', screen: 'inputs', inputHelperMissing: true },
    background: { label: 'Settings · background picker', screen: 'background', prefs: { 'minimal-hub.background.v1': 'valley' } }
  };
  if (typeof module !== 'undefined') module.exports = scenarios;
  else root.HubScenarios = scenarios;
}(typeof window !== 'undefined' ? window : globalThis));
