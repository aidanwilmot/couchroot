/* Local card treatments. No downloaded logos, fonts, or network artwork. */
(function (root) {
  'use strict';
  var looks = {
    'org.tizen.netflix-app': ['Netflix', 'NETFLIX', 'netflix'],
    'org.tizen.primevideo': ['Prime Video', 'prime video', 'prime'],
    'org.tizen.browser': ['Internet', 'Explore.', 'internet'],
    'com.samsung.tv.tvplus': ['Samsung TV Plus', 'TV Plus', 'tvplus'],
    '4j8Nf2XKwh.basic': ['Angel Studios', 'ANGEL', 'angel'],
    'ZmmGjO6VKO.slingtv': ['Sling TV', 'sling', 'sling'],
    '70fRFUwYlD.OtterGAProd': ['PBS Video', 'PBS', 'pbs'],
    'gzcc4LRFBF.Peacock': ['Peacock', 'peacock', 'peacock'],
    '25emanual1.emanual': ['User Guide', 'Good to know.', 'guide'],
    'KMZlIHL7Pp.Blacknut1wO': ['Blacknut', 'blacknut', 'blacknut'],
    'OGLLvqej7u.CrunchyrollWebApp': ['Crunchyroll', 'crunchyroll', 'crunchyroll'],
    '6ReMD8pcTY.Pandora': ['Pandora', 'pandora', 'pandora'],
    'AQKO41xyKP.AmazonAlexa': ['Amazon Alexa', 'alexa', 'alexa'],
    'XtU8fQk2gN.ESPN': ['ESPN', 'ESPN', 'espn'],
    'HupEmjIB4I.Glance': ['Glance', 'glance', 'glance'],
    'yL49PNFmjW.PromotionApp': ['Samsung Promotion', 'Discover.', 'promotion'],
    'Ob3XhAVMu6.amcplus': ['AMC+', 'amc+', 'amc'],
    'jAfAs7yVDX.TheSix': ['Samsung GameBreaks', 'GameBreaks', 'gamebreaks'],
    'GHI3a0zMSx.XboxGamePass': ['Xbox', 'XBOX', 'xbox'],
    'CmeyUlnhYY.LunaWebApp': ['Amazon Luna', 'luna', 'luna'],
    'LBUAQX1exg.Hulu': ['Hulu', 'hulu', 'hulu'],
    'rJeHak5zRg.Spotify': ['Spotify', 'Spotify', 'spotify'],
    'LImG0QPABV.QXHMarketplace': ['QVC+ and HSN+', 'QVC+  HSN+', 'qvc'],
    'MCmYXNxgcu.DisneyPlus': ['Disney+', 'Disney+', 'disney'],
    '9TYrsHWbaB.klyq': ['klyq', 'klyq', 'klyq'],
    'zigzSWa1hy.InstagramAirwave': ['Instagram', 'Instagram', 'instagram'],
    'PvWgqxV3Xa.YouTubeTV': ['YouTube TV', 'YouTube TV', 'youtubetv'],
    '3KA0pm7a7V.TubiTV': ['Tubi', 'tubi', 'tubi']
  };
  function get(app) {
    var item = looks[app.id];
    if (item) { return { name: item[0], wordmark: item[1], theme: 'brand-' + item[2], custom: true }; }
    var hash = 0; for (var i = 0; i < app.id.length; i++) { hash = (hash + app.id.charCodeAt(i)) % 4; }
    return { name: app.name, wordmark: app.name, theme: 'brand-fallback-' + hash, custom: false };
  }
  root.HubPresentation = { get: get };
  if (typeof module !== 'undefined') { module.exports = root.HubPresentation; }
}(typeof window !== 'undefined' ? window : globalThis));
