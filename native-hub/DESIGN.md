# Native Hub design system

Merged from two parallel design passes (2026-10-12): page layout/chrome, and tile direction A
(dark brand-tinted tiles with a bottom brand glow). Harness renders use Arial metrics; the TV uses Samsung One.

## Page layout and chrome

### Problems seen (TV capture + baseline renders)
- Home grid floated in mid-screen: ~180 px dead band above, ~150 px below, no header to anchor it;
  grid left edge (116) and footer edge (120) disagreed; grid gaps 38 x 30 (uneven).
- Footer actions were loose pills of different widths 22 px apart; they read as tags, not controls.
- Hint chips sat on a different rhythm from the footer; notices replaced the hints at y=905 and
  collided with the grid area in compact mode.
- List pages: title, list and panel used unrelated offsets; values were glued into labels
  ("Tile layout · Compact", "Added · Name"); the preview panel had dead space and a bare glyph
  for non-app states; the empty Home was a grey slab with a caption.
### Design system (tokens at the top of hub-ui.h)
- Safe area: one margin MX=120 / MR=1800 on every page; header line HEAD_Y=64; footer row
  FOOT_Y=956, h=60 (bottom margin 64). Body (lists, panel) starts at BODY_Y=168.
- Palette (opaque, warm neutrals over the unchanged #111212 window): panel 24,26,25; row/control
  plate 30,32,31; media well 35,38,36; keycap chip 38,40,39; badge 50,53,50.
  Ink: primary 240,239,229 (~16:1); secondary 172,174,163 (~8:1); quiet 146,148,139 (~6:1, clock);
  accent 228,196,132 (notice dot, "+", Undo remove). All text >= 4.5:1 on its plate.
- Type scale (px): title 44, panel heading 32, body/rows 28, controls 26, detail/hint labels 24,
  keycaps 22, clock 30. Regular weight throughout the chrome; brand weight stays in the tiles.
- Radii: panel 24, rows/controls 14, chips 8, badges 30, tiles 21 (ring placement only; art draws 20).
- Spacing: grid gap 40 (comfortable) / 32 (compact) both axes; list stride 92 (row 80 + 12);
  panel padding 32; chip-to-label 12, hint-to-hint 32.
### Pages
- Home: header line = clock (quiet, right-aligned, re-aligned when it ticks) and, when present, a
  notice on the left with an accent dot. Grid sits at the optical centre (45/55) between the top margin and
  the footer, clamped below the header line (>= 132). Footer = one control bar (plate) with
  equal 240 px segments; the focus ring frames a segment. Undo remove gets accent ink. Hints sit right-aligned
  on the same row, as quiet keycap chips with secondary labels.
- Moving: same header line ("Move X" title / "Position n of m"), same control bar.
- Empty: a 640x360 tile-shaped "Add apps" card (badge "+" and label) plus a centred caption.
- Lists (Edit, Add apps, App actions, Settings, Reset, Error): title on the header line; rows 920
  wide with the value right-aligned in secondary ink (Settings values, "Added" or an accent "+" in
  the picker, "+" on Add apps); scroll arrows centred in the gutter. Preview panel at x=1104 hugs
  its content: 16:9 media well (app art, or a rounded badge "+", "!" (amber), "↺", or the settings
  preview) then heading + detail lines. Notices are right-aligned on the header line.
### Tile geometry (for the tile designers): all rects 16:9, art drawn by card_art()/wordmark()
- 3 columns: 533x299 at x=120+i*573, y0=163 for two rows (was 537x302, gaps 38/30, y0=183).
- 4 columns (compact): 396x222, gap 32, y0=132 (was 393x221, gap 38/30, y0=139).
- 2 columns: 820x461, gap 40. 1 column: 820x461 centred (unchanged size).
- Preview art: (1136,200,632,355), wordmark size 58 (was 1140,245,630,354).
- Focus ring: look unchanged (4 px, 240,229,205); placed 9 px outside the target with corner
  radius = target radius + 9 (tiles: 21+9 = 30, as before). Tile ring clearance <= 13 px < gaps.
### Object counts (harness, scene_count; before -> after)
home 25->22, home-six 45->42, compact-brands 71->68 (test bound 450), many 64->61, empty 18->17,
single 19->16, moving 26->25, edit-preview 25->26, actions 24->24, error 21->23, reset 20->22,
settings 35->39, clock-24 24->28, picker 32->39, picker-real 25->42, home-footer 42->45.
Home scenes shrink (one bar plate replaces 4-5 pills). List pages grow by one label per row value and
one media-well plate. home-footer and picker-real also grow because hints now stay visible
alongside a notice (notice dot + label added; hints were previously hidden).
### Tests and behaviour
- No behaviour, navigation, page, label meaning or order changed; prototype.c, hub-model.h,
  hub-art.h, cards/* untouched. All assertions unchanged and passing (test.sh incl. guard test).
- ui_test.c: snapshot() prints per-scene object counts; added assertion-free design snapshots
  (home-six with clock, home-footer with Undo + notice, picker-real, actions, reset, settings-clock).
### Known limitations
- Harness uses Arial approximations: right-aligned text can be off a few px in SVGs (TV is exact).
- measure() creates and deletes a temporary text object so plates can sit under their text (no
  stacking calls are loaded). This runs on each sub-page focus move (6 temps for hints).
- round_box is a 28-gon (big circles look faceted), so badges are rounded squares. R_TILE (21) has to track the radius hub-art.h passes for tiles if the tile designers change it.
- Segments are a fixed 240 px; a wider label shrinks via label() fitting.

## App tiles and focus


### What was wrong (tv-capture-home.png, baseline-render/)
- Six tiles, six visual languages: Plex beams, a YouTube progress bar, Disney+ arches and a diamond, Amazon Music EQ bars, Crunchyroll slashes, a Prime swoosh. They were hard-edged, saturated, at random angles, and some touched the wordmark.
- Wordmark weights were mixed. Short words were set at 1.5x, so "plex" outweighed "Amazon Music" two to one.
- The YouTube badge (red rounded rectangle with a white triangle) is the logo itself.
- Focus was a heavy cream outline with a fixed 30 px radius on every element.

### Design system
**Tile anatomy.** All 26 apps and the `*default*` fallback use the same three layers; only colour changes.
1. Base: a deep, brand-tinted rounded card. Luminance is capped at 0.03 for a dark room. The radius is proportional to width (w x 20/393): 20, 27 or 42 px at 4, 3 or 2 columns.
2. Glow: 2-3 nested translucent ellipses of brand light rising from the bottom edge to about 64% of tile height, a low horizon under the wordmark. They are clipped to the rounded card in cards.py, with corner vertices kept so the glow sits flush.
   Alpha, outer to inner: soft 10/14/24 (utility tiles), normal 14/24/50, strong 18/30/62. Disney+, HBO Max, Peacock, Viaplay and Asteroids step through 2-3 related hues.
3. Wordmark: centred, 3% of tile height above the middle, always on plain base.

**Brand colour.** Only restrained accents carry it: the glow, a coloured wordmark (Netflix, Hulu, Crunchyroll, Tubi), an accent tail (Plex x, Max, TV, AMC+ "+"), or a small generic red play triangle for YouTube. The logo badge is gone.

**Palette.** Shared ink is #f3f1ec. Bases run #0a0b14 to #1a1d20. Accents are each brand's hue, lightened only where contrast requires it (Netflix ink #ff4650).

**Type.** Bold everywhere; on the TV, Samsung One Bold renders close to SemiBold.
Size is 0.19 x tile height (42 px at 4 columns, 57 at 3, 88 at 2, 67 in the preview). Words under 30% of the tile width grow up to 1.2x; words over 66% shrink, to no less than 0.6x. Unknown long names may widen to 84% before ellipsizing. wordmark() ignores the caller's size argument, so the hub-ui.h call sites are unchanged.

**Spacing.** The play glyph is 0.62 x size tall and takes 0.85 x size with its gap. Focus reaches 25 px outside the tile, inside the 30/38 px gutters.

**Focus (focus_ring).** Cards are never rebuilt; the 10,000-move retention test passes.
- Tiles: a 5 px #f8f7f3 ring after a 6 px dark gap, at the tile's radius, plus an 8 px white halo (alpha 20) for lift.
- card_lift() redraws the tile's outer glow layer in its accent (alpha 34): the brand light brightens and the text stays untinted.
- Buttons and rows keep a plain 4 px ring at their own radius. Focus uses up to 3 objects, all outside scene[].

### Spec, generator, validator (cards/cards.py)
- Raw polygons are gone. A spec names `base` and `accent` (required), plus optional `ink`, `glow` (one colour or 2-3), `strength`, `split`, `glyph` and `weight`.
- The generator emits glow polygons (up to 32 points) as straight RGBA. hub-art.h premultiplies them for Evas.
- The validator composites glow (and the focus lift) over the base and checks, at 96 samples in the wordmark box, ink and tail contrast of at least 4.5:1 at rest and focused, and glyph contrast of at least 3:1. It also checks base luminance, every point inside the rounded card at all 5 sizes, at most 6 objects per tile, and that `*default*` exists.
- The header exports CARD_LIFT_ALPHA, CARD_RADIUS_W and the type constants, so C and the validator share numbers. `preview` draws the same anatomy and lists object counts.

### Object counts (harness)
| scene | before | after |
|---|---|---|
| 12 compact branded cards (compact-brands) | 71 | 76 |
| owner's six-tile Home (6 cards + chrome) | 44 | 46 |
| per tile | 4-6 | 5-6 (6: Plex, YouTube, YouTube TV, HBO Max, AMC+, Sling TV) |
| focus objects (outside scene[]) | 1 | 3 on tiles, 1 elsewhere |

### Edits outside my files
- hub-ui.h: `#include "hub-art.h"` moved above focus_ring. focus_ring() was rewritten with a new focus_band() helper and `ring_extra[2]`. No layout, footer, header or page changes.
- ui_test.c: harness fidelity only; no assertion was weakened.
  The mock records alpha (and asserts premultiplied colours); SVGs draw in creation order (Evas stacking) with fill-opacity; uppercase and "+" widths are closer to Arial (fixes the "HBCMax" overlap); the style test also asserts the 6-object budget and tail/glyph exclusivity. New snapshots: owner-home, owner-home-focus, tiles-1, tiles-2.
- README.md: the "Card styles" paragraph was updated.

### Known limitations
- Evas polygons are flat, so the glow shows 2-3 soft bands. They are quiet, but visible at 2-column size.
- The harness uses Arial metrics. The device measures Samsung One, so tails and glyphs land correctly there.
- Colours were tuned in a browser. QN90A local dimming may lift blacks, so check glow strength on the panel.
- The Peacock glow is subtle. Brand hues are contrast-safe approximations, not official values.
