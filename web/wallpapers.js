/* Bundled wallpapers from CleanFrame (Unsplash License; see wallpapers/credits.txt).
   Each photo has a 1920x1080 image, a thumbnail and a pre-blurred frost material
   with the same crop, so glass plates can show the frost aligned with the backdrop. */
(function (root) {
  'use strict';
  var list = [
    {"id": "misty", "name": "Misty coast", "tone": "light", "veil": 0.2, "credit": "Ganapathy Kumar"},
    {"id": "cove", "name": "Quiet cove", "tone": "light", "veil": 0.12, "credit": "Joshua Wordel"},
    {"id": "forest", "name": "Forest mist", "tone": "dark", "veil": 0.12, "credit": "Dejan Zakic"},
    {"id": "valley", "name": "Mountain valley", "tone": "dark", "veil": 0.12, "credit": "Aniket Deole"},
    {"id": "night", "name": "Desert stars", "tone": "light", "veil": 0.2, "credit": "Mohammad Alizade"},
    {"id": "peaks", "name": "Blue peaks", "tone": "dark", "veil": 0.36, "credit": "John Rodenn Castillo"},
    {"id": "bridge", "name": "Bridge at dusk", "tone": "dark", "veil": 0.44, "credit": "Justin Wolff"},
    {"id": "ridge", "name": "Sunlit ridges", "tone": "dark", "veil": 0.12, "credit": "Cristina Gottardi"},
    {"id": "golden", "name": "Golden hour", "tone": "dark", "veil": 0.3, "credit": "Karthik Sreenivas"},
    {"id": "summit", "name": "Sunlit summits", "tone": "dark", "veil": 0.2, "credit": "Rudra Gupta"},
    {"id": "goldcoast", "name": "Gold Coast dusk", "tone": "light", "veil": 0.2, "credit": "City of Gold Coast"},
    {"id": "sydney", "name": "Sydney Harbour", "tone": "light", "veil": 0.44, "credit": "Caleb"},
    {"id": "amber", "name": "Amber hills", "tone": "light", "veil": 0.2, "credit": "Chris Barbalis"},
    {"id": "mint", "name": "Mint wave", "tone": "light", "veil": 0.44, "credit": "MagicPattern"},
    {"id": "alpine", "name": "Alpine glow", "tone": "light", "veil": 0.2, "credit": "Cristina Gottardi"}
  ];
  root.HubWallpapers = list;
  if (typeof module !== 'undefined') { module.exports = list; }
}(typeof window !== 'undefined' ? window : globalThis));
