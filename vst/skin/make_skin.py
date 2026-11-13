#!/usr/bin/env python3
"""Generate the OxZygen MPC skin: artwork (Chromium via Playwright, Pillow) and layout.conf.

    python3 vst/skin/make_skin.py

Every coordinate lives here, so the baked artwork and MPC's live controls always line up. Writes:
  art/bg_player.png, art/bg_browse.png, art/bg_sound.png, art/bg_fx.png   tab backgrounds, 1280x628 (the plugin area)
  art/cat_*.png, art/row_*.png, art/pad_*.png        BROWSE's rows (off, lit) and the clear pads that take the taps
  art/knob48.png                                     knob filmstrip, 128 frames (light fixed, pointer and arc turn)
  art/orb.png                                        orb meter filmstrip: 2 energy levels x 17 frames, 360x360
  art/seg_cat_*.png, art/seg_snd<n>_*.png, art/seg_oct_*.png   category, sound (n per row) and octave segments
  art/lbl_<sound>.png                                the three knob labels for each sound (a picture follows the sound)
  layout.conf

Coordinates are MPC screen pixels (1280x800). The plugin area is y=86..714, so backgrounds subtract 86.
MPC draws knob values live (Titillium Web) at cy + r + 2; names are baked here in Barlow Condensed (OFL, fonts/).
Re-run after any design change; the build (tools/build_port.sh) then turns layout.conf into the MPC skin.
"""
import base64
import io
import json
import os
import random

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "art")
FONTS = os.path.join(HERE, "fonts")
Y0 = 86                      # top of the plugin area
W, H = 1280, 628

# palette (the prototype's)
# Aluminum Cobalt: brushed aluminum panels, graphite machined knobs, cobalt accent, ice-blue lit readouts
BEZEL, PANEL, FG, DIM, LIVE, BRASS = "#b9bdc2", "#cfd2d6", "#15171a", "#4a4f56", "#1f6fff", "#d1a85c"
READ_BG, READ_TX = "#0b1424", "#7ff0ff"

# Themes (the "theme" parameter, picked on BROWSE): a panel and an accent each. The knob caps, readout boxes and LCDs
# stay; the accent lights knob rings and pointers, lit buttons and rows, the orb, the Z and every live text.
# Aluminum's art stays in art/; the others' in art/<key>/.
_DARK = """
.klabel, .title { color: %(fg)s !important; text-shadow: 0 1px 0 rgba(0,0,0,.7) !important; }
.heading { color: %(dim)s !important; text-shadow: 0 1px 0 rgba(0,0,0,.7) !important; }
.heading::after, .rule { background: linear-gradient(90deg, rgba(%(hi)s,.22), transparent) !important; box-shadow: 0 1px 0 rgba(0,0,0,.5) !important; }
.grain { opacity: .9 !important; background-image: repeating-linear-gradient(0deg, rgba(%(hi)s,.045) 0 1px, rgba(0,0,0,.08) 1px 2px, transparent 2px 3px) !important;
  box-shadow: inset 0 1px 0 rgba(%(hi)s,.16), inset 0 -2px 6px rgba(0,0,0,.5) !important; }
.vbox { box-shadow: inset 0 2px 5px rgba(0,0,0,.95), 0 1px 0 rgba(%(hi)s,.14) !important; }
.lcd { box-shadow: inset 0 3px 8px rgba(0,0,0,.9), inset 0 0 0 1px rgba(0,0,0,.9), 0 1px 0 rgba(%(hi)s,.14) !important; }
.well::before { opacity: .55; }
"""
THEMES = [
    dict(key="aluminum", name="ALUMINUM", dir="", acc="#1f6fff", acc_hi="#3b82ff", acc_lo="#1450c8", glow="31,111,255",
         ptr="#4d8dff", txt="#7ff0ff", txt_dim="#5a82aa", row_tx="#a9dcef", fg=FG, fg_shadow="rgba(255,255,255,.55)", orb_hue=0,
         css=""),
    dict(key="green", name="GREEN", dir="green", acc="#19c27a", acc_hi="#3ee39a", acc_lo="#0f8f58", glow="25,194,122",
         ptr="#52f0a8", txt="#8cffc4", txt_dim="#4f9a77", row_tx="#b4f0d2", fg="#e6f3ec", fg_shadow="rgba(0,0,0,.7)", orb_hue=-60,
         css=_DARK % {"fg": "#e6f3ec", "dim": "#9cc3ae", "hi": "200,255,225"} + """
body { background: radial-gradient(1300px 420px at 50% -80px, rgba(180,255,210,.16), transparent 70%),
  linear-gradient(180deg, #24493a, #17352a 55%, #0e241c) !important; }
.well { background: linear-gradient(180deg, #24463a, #1a372c 60%, #152e25) !important;
  box-shadow: inset 0 1px 0 rgba(200,255,225,.14), 0 0 0 1px rgba(0,20,10,.6), 0 6px 14px rgba(0,20,10,.4) !important; }
.bezel { background: radial-gradient(circle at 35% 28%, #b8dcc8, #4a7a62 55%, #1a3a2c) !important; }
"""),
    dict(key="navy", name="NAVY", dir="navy", acc="#e0a23e", acc_hi="#f2bd5e", acc_lo="#b37a22", glow="224,162,62",
         ptr="#ffc45e", txt="#ffd280", txt_dim="#a88a5c", row_tx="#f0dcb4", fg="#e8eefa", fg_shadow="rgba(0,0,0,.7)", orb_hue=165,
         css=_DARK % {"fg": "#e8eefa", "dim": "#9fb4d8", "hi": "200,220,255"} + """
body { background: radial-gradient(1300px 420px at 50% -80px, rgba(170,200,255,.22), transparent 70%),
  linear-gradient(180deg, #2c4470, #1c3058 55%, #121f3c) !important; }
.well { background: linear-gradient(180deg, #2a4068, #1f3256 60%, #192a4a) !important;
  box-shadow: inset 0 1px 0 rgba(200,220,255,.15), 0 0 0 1px rgba(0,0,20,.6), 0 6px 14px rgba(0,0,20,.4) !important; }
.bezel { background: radial-gradient(circle at 35% 28%, #b9cbea, #4f6a98 55%, #1f3156) !important; }
"""),
]
TH = THEMES[0]   # the theme being drawn


def art(name, th=None):
    """A theme's art file, as layout.conf names it (relative to the skin folder)."""
    d = (th or TH)["dir"]
    return "art/%s%s" % (d + "/" if d else "", name)

ORB_PHASES, ORB_LEVELS, ORB_SIZE = 17, 2, 360   # 34 frames x 360 px = 12240 px, under MPC's 12288 px strip limit

# --- layout -------------------------------------------------------------------------------------------
# knob: (key, label, cx, cy, r, value text size, touch width)
PLAYER = {
    "orb": (640, 414),
    "headings": [("VOICE", 46, 420, 132), ("ATMOSPHERE", 860, 1234, 132)],
    "knobs": [
        ("velocity", "Velocity", 125, 286), ("breath", "Breath", 325, 286),
        ("attack", "Attack", 125, 518), ("release", "Release", 325, 518),
        ("air", "Air", 955, 286), ("dark", "Filter", 1155, 286),
        ("lofi", "Lo-Fi", 955, 518), ("motion", "Motion", 1155, 518),
    ],
}
PLAYER_R, PLAYER_VS, PLAYER_BW = 58, 30, 150
# the preset strip under the wordmark: the name (live), prev / next pads at its ends
STRIP = (410, 178, 870, 222)           # x0, y0, x1, y1 (screen): ~16 px clear of the wordmark above and the orb's ticks (238) below
STRIP_PAD = 64                         # the arrow pads' width

# BROWSE page: categories on the left, that category's presets on the right (3 columns of 8), one LCD each
CAT_BOX = (40, 182, 300, 682)          # the LCD panels (screen)
ROW_BOX = (320, 182, 1240, 682)
LIST_Y, LIST_TH, LIST_GAP = 228, 46, 8 # the first row's top, row height, gap (8 rows end at 228 + 8*46 + 7*8 = 652)
CAT_LIST = (52, LIST_Y, 236)           # x, y, width: 1 column
ROW_LIST = (332, LIST_Y, 896, 3)       # x, y, width, columns
ROW_COL_GAP = LIST_GAP              # the list widget uses one gap both ways
PG_W, PG_H = 52, 30                    # page up / down pads, top right of the presets panel
THEME_BOX = (1000, 116, 1234, 148)     # the theme picker, right of the THEME heading (screen)
THEME_PAD = 44   # 58: 126 px x 128 frames = 16128 px; 59 hits the 16384 limit and drifts on the device

# SOUND page: slots A and B side by side, each a 610 x 600 panel
# categories and their sounds (must match params.json); SOUNDS is the derived a_sound/b_sound list, in order
CATS = ["Off", "Voices", "Winds", "Brass", "Strings", "Bells", "Synth", "Air"]
PER = {"Voices": ["Choir", "Vowels"], "Winds": ["Flute", "Ocarina", "Sax", "Clarinet", "Oboe"],
       "Brass": ["Horn", "Mute Trumpet", "Trombone"], "Strings": ["Sustain", "Tremolo"],
       "Bells": ["Church", "Tubular", "Vibes", "Bowed Vibes", "Glass"], "Synth": ["Pad", "Lead", "Brass"],
       "Air": ["Wind", "Texture"]}
SOUNDS = ["Off", "Choir", "Vowels", "Flute", "Ocarina", "Sax", "Clarinet", "Oboe", "Horn", "Mute Trumpet", "Trombone",
          "Strings", "Tremolo", "Church Bells", "Tubular", "Vibes", "Bowed Vibes", "Glass", "Synth Pad", "Synth Lead",
          "Synth Brass", "Wind", "Texture"]
WIND3 = ["Vibrato", "Breath", "Tone"]
KNOB_LABELS = {"Off": ["", "", ""], "Choir": ["Vowel", "Spread", "Attack"], "Vowels": ["Morph", "Formant", "Attack"],
               "Flute": WIND3, "Ocarina": WIND3, "Sax": WIND3, "Clarinet": WIND3, "Oboe": WIND3,
               "Horn": WIND3, "Mute Trumpet": WIND3, "Trombone": WIND3,
               "Strings": ["Ensemble", "Swell", "Tone"], "Tremolo": ["Ensemble", "Swell", "Tone"],
               "Church Bells": ["Strike", "Decay", "Shimmer"], "Tubular": ["Decay", "Shimmer", "Tone"],
               "Vibes": ["Decay", "Shimmer", "Tone"], "Bowed Vibes": ["Swell", "Shimmer", "Tone"],
               "Glass": ["Swell", "Shimmer", "Tone"], "Synth Pad": ["Cutoff", "Shape", "Chorus"],
               "Synth Lead": ["Cutoff", "Glide", "Chorus"], "Synth Brass": ["Cutoff", "Bloom", "Chorus"],
               "Wind": ["Density", "Drift", "Width"], "Texture": ["Grain", "Pitch", "Smear"]}   # must match engine.c
SLOTS = [("a", "Sound A", 20, 100), ("b", "Sound B", 650, 100)]
CAT_SW, CAT_SH = 140, 40               # 4 x 2 grid of categories
SND_ROW, SND_H = 560, 42               # a category's sounds share one row this wide
OCT_SW, OCT_SH = 80, 38                # five octave segments
SLOT_KNOB_DX, SLOT_KNOB_DY = 132, 448  # four knobs 132 px apart, centred in the panel, at y0 + 425
SLOT_R, SLOT_VS, SLOT_BW = 56, 28, 124
LBL_W, LBL_H = 3 * SLOT_KNOB_DX, 32    # the label strip under knobs 1-3


def slot_geom(x0, y0):
    cx = x0 + 305
    knobs = [(cx + int((i - 1.5) * SLOT_KNOB_DX), y0 + SLOT_KNOB_DY) for i in range(4)]
    return {"cat": (cx, y0 + 98), "snd": (cx, y0 + 214), "oct": (x0 + 360, y0 + 282), "oct_label": (x0 + 24, y0 + 282),
            "knobs": knobs}


def snd_sw(n):
    """Segment width for a row of n sounds (2 px gaps)."""
    return (SND_ROW - 2 * (n - 1)) // n


def slot_knobs():
    out = []
    for p, name, x0, y0 in SLOTS:
        g = slot_geom(x0, y0)
        for (cx, cy), k in zip(g["knobs"], ("k1", "k2", "k3", "level")):
            out.append(("%s_%s" % (p, k), "Level" if k == "level" else "", cx, cy))
    return out


def label_top(cy, r=SLOT_R, vs=SLOT_VS):
    """Where a knob's baked name sits: under MPC's live value (cy + r + 2, value_h tall), 5 px gap."""
    return cy + r + 2 + max(30, round(vs * 1.25)) + 5


FX = [("rv", "Reverb", ["Size", "Decay", "Mix"], 20, 100),
      ("dl", "Delay", ["Time", "Feedback", "Mix"], 650, 100),
      ("dr", "Drive / Tuning", ["Amount", "Tone", "Mix"], 20, 406),
      ("sb", "Sub / Output", ["Level", "Tune", "Drop"], 650, 406)]
FX_R, FX_VS, FX_BW = 56, 28, 116   # Sub / Output has 4 knobs 122 px apart


def fx_knobs():
    out = []
    for p, name, ks, x0, y0 in FX:
        n = len(ks) + (1 if p in ("sb", "dr") else 0)
        step = 610 // (n + 1)
        for i, k in enumerate(ks):
            out.append(("%s_%s" % (p, k.lower()), k, x0 + step * (i + 1), y0 + 160))
        if p == "sb":
            out.append(("master", "Output", x0 + step * n, y0 + 160))
        if p == "dr":   # A4 reference pitch, in Hz
            out.append(("a4", "A4 Tune", x0 + step * n, y0 + 160))
    return out


# --- artwork in Chromium ------------------------------------------------------------------------------
FONT_CSS = """
@font-face { font-family: 'BC'; font-weight: 600; src: url('file://%(f)s/BarlowCondensed-SemiBold.ttf'); }
@font-face { font-family: 'BC'; font-weight: 700; src: url('file://%(f)s/BarlowCondensed-Bold.ttf'); }
""" % {"f": FONTS}

DRAW_JS = r"""
const LIVE = '__LIVE__';
function knob(size, v) {
  // Graphite machined knob on the aluminum panel. In 100-unit space: value ring r 44-48, cap r 37, light from the
  // top left stays put (only the pointer and the arc move), so the 128 frames read as one object turning.
  const c = document.createElement('canvas'); c.width = c.height = size * 2;     // drawn at 2x, downsampled later
  const x = c.getContext('2d'); x.scale(size * 2 / 100, size * 2 / 100);
  const A = deg => deg * Math.PI / 180;
  // value track, then the cobalt arc with a soft glow
  x.lineCap = 'round'; x.lineWidth = 4.2;
  x.beginPath(); x.arc(50, 50, 45.5, A(135), A(405)); x.strokeStyle = 'rgba(20,24,30,.28)'; x.stroke();
  if (v > 0.002) {
    x.save(); x.shadowColor = 'rgba(31,111,255,.65)'; x.shadowBlur = 3;
    x.beginPath(); x.arc(50, 50, 45.5, A(135), A(135 + 270 * v)); x.strokeStyle = LIVE; x.stroke(); x.restore();
  }
  // shadow cast on the panel, then the dark skirt
  x.save(); x.shadowColor = 'rgba(0,0,0,.55)'; x.shadowBlur = 6; x.shadowOffsetY = 3;
  x.beginPath(); x.arc(50, 50, 39.5, 0, 2 * Math.PI); x.fillStyle = '#0c0d0f'; x.fill(); x.restore();
  // cap: machined graphite (a conic sheen like spun metal) with fine concentric turning marks
  const g = x.createConicGradient(A(-60), 50, 50);
  [[0, '#6a6f78'], [.12, '#2a2d33'], [.25, '#5a5f68'], [.38, '#1f2227'], [.5, '#62676f'], [.63, '#25282d'],
   [.76, '#575c64'], [.88, '#1d2025'], [1, '#6a6f78']].forEach(([o, col]) => g.addColorStop(o, col));
  x.beginPath(); x.arc(50, 50, 37, 0, 2 * Math.PI); x.fillStyle = g; x.fill();
  for (let r = 4; r < 37; r += 1.1) {
    x.beginPath(); x.arc(50, 50, r, 0, 2 * Math.PI);
    x.strokeStyle = (r * 7 | 0) % 2 ? 'rgba(255,255,255,.035)' : 'rgba(0,0,0,.05)'; x.lineWidth = .5; x.stroke();
  }
  // vertical shading over the sheen: lit from above
  const sh = x.createLinearGradient(0, 13, 0, 87);
  sh.addColorStop(0, 'rgba(255,255,255,.16)'); sh.addColorStop(.5, 'rgba(0,0,0,0)'); sh.addColorStop(1, 'rgba(0,0,0,.35)');
  x.beginPath(); x.arc(50, 50, 37, 0, 2 * Math.PI); x.fillStyle = sh; x.fill();
  // chamfer: a bright machined edge on top, dark below
  const ed = x.createLinearGradient(0, 13, 0, 87);
  ed.addColorStop(0, 'rgba(255,255,255,.55)'); ed.addColorStop(.45, 'rgba(255,255,255,.08)'); ed.addColorStop(1, 'rgba(0,0,0,.6)');
  x.beginPath(); x.arc(50, 50, 36.4, 0, 2 * Math.PI); x.strokeStyle = ed; x.lineWidth = 1.3; x.stroke();
  x.beginPath(); x.arc(50, 50, 37.6, 0, 2 * Math.PI); x.strokeStyle = 'rgba(0,0,0,.85)'; x.lineWidth = .8; x.stroke();
  // pointer: a lit cobalt line inset in the cap
  const d = A(135 + 270 * v), P = r => [50 + r * Math.cos(d), 50 + r * Math.sin(d)];
  const [a, b] = P(12), [e, f] = P(33);
  x.lineWidth = 3.6; x.beginPath(); x.moveTo(a, b + .7); x.lineTo(e, f + .7); x.strokeStyle = 'rgba(0,0,0,.7)'; x.stroke();
  x.save(); x.shadowColor = 'rgba(80,150,255,.9)'; x.shadowBlur = 3; x.lineWidth = 2.6;
  x.beginPath(); x.moveTo(a, b); x.lineTo(e, f); x.strokeStyle = '#4d8dff'; x.stroke(); x.restore();
  return c.toDataURL('image/png');
}

function rng(seed) { return () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }; }
// CRT pass over the orb's picture (device pixels): tube bulge, RGB convergence fringe, scanlines, phosphor
// triads, a slow rolling refresh band, faint flicker, and the darker tube edge. All loop with t (0..1).
function crt(x, W, C, R, t, level) {
  const src = x.getImageData(0, 0, W, W), s = src.data, out = x.createImageData(W, W), d = out.data;
  const roll = (t * W * 1.0) % W, flick = 1 + 0.035 * Math.sin(t * 2 * Math.PI * 3) + (level ? 0.04 : 0);
  const sample = (px, py, ch) => {
    px = Math.max(0, Math.min(W - 1, px | 0)); py = Math.max(0, Math.min(W - 1, py | 0));
    return s[(py * W + px) * 4 + ch];
  };
  for (let y = 0; y < W; y++) for (let xx = 0; xx < W; xx++) {
    const i = (y * W + xx) * 4, dx = (xx - C) / R, dy = (y - C) / R, r2 = dx * dx + dy * dy;
    if (r2 > 1.0) { d[i] = s[i]; d[i + 1] = s[i + 1]; d[i + 2] = s[i + 2]; d[i + 3] = s[i + 3]; continue; }
    const k = 1 - 0.10 * r2;                                    // bulge: the middle pushes toward you
    const sx = C + dx * k * R, sy = C + dy * k * R, fr = 2.5 + 4 * r2;   // fringe grows toward the edge
    let rr = sample(sx + fr, sy, 0), gg = sample(sx, sy, 1), bb = sample(sx - fr, sy, 2);
    const line = (y % 6) < 2 ? 0.38 : 1.12;                    // scanlines: 3 px pitch on screen, one px dark
    const tri = ((xx / 2) | 0) % 3, mask = 0.82;                 // phosphor triads, one screen px each
    const band = 1 + 0.22 * Math.exp(-Math.pow(((y - roll + W) % W) / 40 - 1, 2) * 3);   // rolling refresh
    const vig = 1 - 0.45 * Math.pow(r2, 1.6);
    const g = line * band * vig * flick * 1.3;                  // phosphor glow makes up for the dark lines
    rr *= g * (tri === 0 ? 1.12 : mask); gg *= g * (tri === 1 ? 1.12 : mask); bb *= g * (tri === 2 ? 1.12 : mask);
    const lift = 3 * vig;                                        // the tube is never quite black
    d[i] = Math.min(255, rr + lift); d[i + 1] = Math.min(255, gg + lift * 1.3); d[i + 2] = Math.min(255, bb + lift * 1.6);
    d[i + 3] = 255;
  }
  x.putImageData(out, 0, 0);
}

function orb(S, phase, phases, level) {
  const c = document.createElement('canvas'); c.width = c.height = S * 2;
  const x = c.getContext('2d'); x.scale(2, 2);
  const C = S / 2, R = 150, t = phase / phases;
  x.save(); x.beginPath(); x.arc(C, C, R, 0, 2 * Math.PI); x.clip();
  const body = x.createRadialGradient(C - 30, C - 40, 6, C, C, R);
  body.addColorStop(0, '#1c2634'); body.addColorStop(.55, '#0a0f17'); body.addColorStop(.92, '#04060a'); body.addColorStop(1, '#000');
  x.fillStyle = body; x.fillRect(0, 0, S, S);
  x.strokeStyle = 'rgba(160,200,220,.06)'; x.lineWidth = 1;          // faint facets, like cut crystal
  for (let i = 0; i < 6; i++) { const a = i * Math.PI / 3 + .3;
    x.beginPath(); x.moveTo(C + Math.cos(a) * R, C + Math.sin(a) * R); x.lineTo(C - Math.cos(a) * R * .2, C - Math.sin(a) * R * .2); x.stroke(); }
  // wisps: each one's life u = (t * m + o) mod 1, so the 17 frames loop without a seam
  const r = rng(7), N = level ? 22 : 14, base = level ? .5 : .26;
  x.lineCap = 'round';
  for (let k = 0; k < 22; k++) {
    const w = { x0: C + (r() - .5) * R * 1.0, rise: R * (.9 + r() * .6), A: 8 + r() * 22, wf: .6 + r() * 1.1,
                ph: r(), o: r(), m: r() < .3 ? 2 : 1, wd: .8 + r() * 1.6, drift: (r() - .5) * 40, hue: r() < .55 };
    if (k >= N) continue;
    const u = (t * w.m + w.o) % 1, env = Math.pow(Math.sin(Math.PI * u), 1.4);
    const pos = q => [w.x0 + w.A * Math.sin(2 * Math.PI * (w.wf * q + w.ph)) + w.drift * q, C + R * .62 - w.rise * q];
    const steps = 36, tail = .32, col = w.hue ? '92,200,255' : '138,127,230';
    let prev = null;
    for (let j = 0; j <= steps; j++) {
      const q = u - tail + tail * j / steps; if (q < 0) { prev = null; continue; }
      const p = pos(q);
      if (prev) { const f = j / steps;
        x.strokeStyle = 'rgba(' + col + ',' + (base * env * f).toFixed(3) + ')'; x.lineWidth = w.wd * (.4 + f * 1.3);
        x.beginPath(); x.moveTo(prev[0], prev[1]); x.lineTo(p[0], p[1]); x.stroke(); }
      prev = p;
    }
  }
  const core = x.createRadialGradient(C, C + 12, 0, C, C + 12, 90);
  core.addColorStop(0, 'rgba(92,200,255,' + (level ? .17 : .06) + ')'); core.addColorStop(1, 'rgba(92,200,255,0)');
  x.fillStyle = core; x.fillRect(0, 0, S, S);
  crt(x, S * 2, C * 2, R * 2, t, level);
  x.save(); x.translate(C - 54, C - 62); x.rotate(-.6);               // hard window reflection
  x.beginPath(); x.ellipse(0, 0, 32, 9, 0, 0, 2 * Math.PI); x.fillStyle = 'rgba(235,245,255,.18)'; x.fill(); x.restore();
  x.restore();
  x.beginPath(); x.arc(C, C, R - .5, 0, 2 * Math.PI); x.strokeStyle = 'rgba(255,255,255,.08)'; x.lineWidth = 1; x.stroke();
  // tick scale around the orb, lit while playing
  for (let i = 0; i < 60; i++) {
    const a = i * 6 * Math.PI / 180 - Math.PI / 2, major = i % 5 === 0;
    const r0 = 176, r1 = major ? 160 : 166;
    x.beginPath(); x.moveTo(C + Math.cos(a) * r0, C + Math.sin(a) * r0); x.lineTo(C + Math.cos(a) * r1, C + Math.sin(a) * r1);
    x.strokeStyle = level ? (major ? LIVE : 'rgba(92,200,255,.35)') : (major ? '#6b7588' : '#3a4352');
    x.lineWidth = major ? 1.8 : 1.2; x.lineCap = 'butt'; x.stroke();
  }
  return c.toDataURL('image/png');
}
""".replace("__LIVE__", LIVE)


def png(data_url):
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))).convert("RGBA")


def strip(frames, size):
    out = Image.new("RGBA", (size, size * len(frames)), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        out.paste(f.resize((size, size), Image.LANCZOS), (0, i * size))
    return out


def seg_html(on, w, h):
    """A blank button plate; the renderer writes the option name on it (skin.css sets the font)."""
    if on:
        bg = ("linear-gradient(180deg,rgba(255,255,255,.22),rgba(255,255,255,0) 50%%),"
              "linear-gradient(180deg,%s,%s 55%%,%s)" % (TH["acc_hi"], TH["acc"], TH["acc_lo"]))
        sh = "inset 0 1px 0 rgba(255,255,255,.55),inset 0 -1px 0 rgba(0,0,0,.35),0 0 10px rgba(%s,.45)" % TH["glow"]
        border = "#0e3c9e" if not TH["dir"] else TH["acc_lo"]
    else:
        bg = ("repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 2px),"
              "linear-gradient(180deg,#4a4e55 0%,#33363c 50%,#26292e 100%)")
        sh = "inset 0 1px 0 rgba(255,255,255,.25),inset 0 -1px 0 rgba(0,0,0,.5),0 1px 0 rgba(255,255,255,.6)"
        border = "#121418"
    return ("<div style='width:%dpx;height:%dpx;box-sizing:border-box;border:1px solid %s;border-radius:4px;"
            "background:%s;box-shadow:%s'></div>" % (w, h, border, bg, sh))


def labels_html(names):
    """Three knob names, centred under knobs 1-3 (a transparent strip a picture widget swaps per sound)."""
    cells = "".join("<div style='width:%dpx;text-align:center'>%s</div>" % (SLOT_KNOB_DX, n.upper()) for n in names)
    return ("<div style='display:flex;width:%dpx;height:%dpx;align-items:center;font:700 23px BC,sans-serif;"
            "letter-spacing:.14em;color:%s;text-shadow:0 1px 0 %s'>%s</div>" % (LBL_W, LBL_H, TH["fg"], TH["fg_shadow"], cells))


SKIN_CSS = """/* generated by make_skin.py: the selector's option names in the skin's condensed face */
@font-face { font-family: "BC"; font-weight: 600; src: url("fonts/BarlowCondensed-SemiBold.ttf"); }
@font-face { font-family: "BC"; font-weight: 700; src: url("fonts/BarlowCondensed-Bold.ttf"); }
.seg-tx { font-family: "BC", sans-serif; font-weight: 700; font-size: 21px; letter-spacing: 0.12em; text-transform: uppercase; }
.seg-sheen { display: none; }
"""


def value_box(cx, cy, r, vs, width):
    """The dark readout behind MPC's live value, and where the baked name goes under it."""
    vh = max(30, round(vs * 1.25))
    top = cy + r + 2 - Y0
    return top, vh, ("<div class='vbox' style='left:%dpx;top:%dpx;width:%dpx;height:%dpx'></div>"
                     % (cx - width // 2, top, width, vh))


def knob_block(key, label, cx, cy, r, vs, width, label_px):
    top, vh, box = value_box(cx, cy, r, vs, width)
    return box + ("<div class='klabel' style='left:%dpx;top:%dpx;width:200px;font-size:%dpx'>%s</div>"
                  % (cx - 100, top + vh + 5, label_px, label.upper()))


PAGE_CSS = """
%(fonts)s
* { margin: 0; padding: 0; box-sizing: border-box; }
/* brushed aluminum: a fine horizontal grain, a soft light from above, slightly darker toward the bottom */
body { width: 1280px; height: 628px; overflow: hidden; position: relative;
  background: radial-gradient(1300px 420px at 50%% -80px, rgba(255,255,255,.55), transparent 70%%),
    linear-gradient(180deg, #dfe2e5, #c4c8cc 55%%, #a9adb2); }
.grain { position: absolute; inset: 0; opacity: .55;
  background-image: repeating-linear-gradient(0deg, rgba(255,255,255,.10) 0 1px, rgba(0,0,0,.035) 1px 2px, transparent 2px 3px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.7), inset 0 -2px 6px rgba(0,0,0,.25); }
.vbox { position: absolute; background: %(READ_BG)s; border-radius: 5px;
  box-shadow: inset 0 2px 5px rgba(0,0,0,.85), 0 1px 0 rgba(255,255,255,.7), 0 -1px 0 rgba(0,0,0,.25); }
.klabel { position: absolute; text-align: center; font-family: BC, sans-serif; font-weight: 700; color: %(FG)s;
  letter-spacing: .14em; text-transform: uppercase; text-shadow: 0 1px 0 rgba(255,255,255,.55); }
.heading { position: absolute; display: flex; align-items: center; gap: 14px; font: 700 22px BC, sans-serif;
  letter-spacing: .3em; color: %(DIM)s; text-shadow: 0 1px 0 rgba(255,255,255,.6); }
.heading::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, rgba(0,0,0,.25), transparent);
  box-shadow: 0 1px 0 rgba(255,255,255,.5); }
/* a recessed aluminum plate for each section, with four screws */
.well { position: absolute; border-radius: 8px;
  background: repeating-linear-gradient(0deg, rgba(255,255,255,.09) 0 1px, rgba(0,0,0,.03) 1px 2px, transparent 2px 3px),
    linear-gradient(180deg, #d7dade, #c3c7cb 60%%, #b6babf);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.85), inset 0 -1px 0 rgba(0,0,0,.18), 0 0 0 1px rgba(0,0,0,.22),
    0 6px 14px rgba(0,0,0,.18); }
.well::before { content: ""; position: absolute; inset: 9px; pointer-events: none;   /* corner screws */
  background: radial-gradient(circle at 6px 6px, #f2f3f5 0 1.5px, #9a9fa6 3px, #5b6067 4.5px, transparent 5.5px) 0 0 / 12px 12px no-repeat,
    radial-gradient(circle at 6px 6px, #f2f3f5 0 1.5px, #9a9fa6 3px, #5b6067 4.5px, transparent 5.5px) 100%% 0 / 12px 12px no-repeat,
    radial-gradient(circle at 6px 6px, #f2f3f5 0 1.5px, #9a9fa6 3px, #5b6067 4.5px, transparent 5.5px) 0 100%% / 12px 12px no-repeat,
    radial-gradient(circle at 6px 6px, #f2f3f5 0 1.5px, #9a9fa6 3px, #5b6067 4.5px, transparent 5.5px) 100%% 100%% / 12px 12px no-repeat; }
.title { position: absolute; font: 700 26px BC, sans-serif; letter-spacing: .24em; color: %(FG)s; text-transform: uppercase;
  text-shadow: 0 1px 0 rgba(255,255,255,.6); }
.title b { color: var(--acc); font-weight: 700; text-shadow: 0 0 10px rgba(var(--glow),var(--zglow)); }
.lcd { position: absolute; border-radius: 10px; background: %(READ_BG)s;
  background-image: repeating-linear-gradient(0deg, rgba(255,255,255,.035) 0 1px, transparent 1px 3px);
  box-shadow: inset 0 3px 8px rgba(0,0,0,.9), inset 0 0 0 1px rgba(0,0,0,.9), 0 1px 0 rgba(255,255,255,.75), 0 -1px 0 rgba(0,0,0,.2); }
.lcdcap { position: absolute; font: 700 15px BC, sans-serif; letter-spacing: .16em; color: #5a82aa; }
.arrow { position: absolute; width: 0; height: 0; border-top: 7px solid transparent; border-bottom: 7px solid transparent;
  filter: drop-shadow(0 0 4px rgba(64,170,255,.8)); }
.rule { position: absolute; height: 1px; background: linear-gradient(90deg, rgba(0,0,0,.22), transparent);
  box-shadow: 0 1px 0 rgba(255,255,255,.55); }
""" % {"fonts": FONT_CSS, "FG": FG, "DIM": DIM, "PANEL": PANEL, "LIVE": LIVE, "READ_BG": READ_BG}


def bg_player():
    ox, oy = PLAYER["orb"]
    h = ["<div class='grain'></div>"]
    # the orb's shadow on the panel (the orb itself is the live meter on top)
    h.append("<div class='bezel' style='position:absolute;left:%dpx;top:%dpx;width:340px;height:340px;border-radius:50%%;"
             "background:radial-gradient(circle at 35%% 28%%,#f4f5f7,#b4b8be 55%%,#80858c);"
             "box-shadow:0 18px 36px rgba(0,0,0,.35),inset 0 2px 1px rgba(255,255,255,.9),inset 0 -3px 6px rgba(0,0,0,.35)'></div>"
             % (ox - 170, oy - Y0 - 170))
    h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:304px;height:304px;border-radius:50%%;background:#05070a;"
             "box-shadow:inset 0 3px 8px rgba(0,0,0,.9),0 1px 0 rgba(255,255,255,.6)'></div>" % (ox - 152, oy - Y0 - 152))
    # wordmark: all caps, the Z carries the emphasis (larger, accent colour)
    h.append(wordmark())
    for text, x0, x1, y in PLAYER["headings"]:
        h.append("<div class='heading' style='left:%dpx;top:%dpx;width:%dpx'>%s</div>" % (x0, y - Y0 - 12, x1 - x0, text))
    for key, label, cx, cy in PLAYER["knobs"]:
        h.append(knob_block(key, label, cx, cy, PLAYER_R, PLAYER_VS, 104, 26))
    h.append(strip_html())
    return "".join(h)


def strip_html():
    """The preset strip: an LCD the width of the orb's bezel, ◀ and ▶ lit in its ends (MPC writes the name)."""
    x0, y0, x1, y1 = STRIP
    cy = (y0 + y1) // 2 - Y0
    big = "border-top-width:11px;border-bottom-width:11px"
    return ("<div class='lcd' style='left:%dpx;top:%dpx;width:%dpx;height:%dpx;border-radius:11px'></div>"
            "<div class='arrow' style='left:%dpx;top:%dpx;%s;border-right:17px solid %s'></div>"
            "<div class='arrow' style='left:%dpx;top:%dpx;%s;border-left:17px solid %s'></div>"
            % (x0, y0 - Y0, x1 - x0, y1 - y0, x0 + 22, cy - 11, big, TH["txt"], x1 - 39, cy - 11, big, TH["txt"]))


def wordmark():
    return ("<div class='title' style='left:0;width:1280px;top:%dpx;text-align:center;font-size:40px;"
            "letter-spacing:.24em;line-height:48px'>OX<b style='font-size:58px;vertical-align:-5px;"
            "letter-spacing:.18em'>Z</b>YGEN</div>" % (106 - Y0))


def bg_browse():
    h = ["<div class='grain'></div>", wordmark()]
    for text, x0, x1, y in (("BROWSE", 46, 420, 132), ("THEME", 860, 990, 132)):
        h.append("<div class='heading' style='left:%dpx;top:%dpx;width:%dpx'>%s</div>" % (x0, y - Y0 - 12, x1 - x0, text))
    # the theme picker: a small LCD with ◀ ▶ (MPC writes the theme's name)
    x0, y0, x1, y1 = THEME_BOX
    cy = (y0 + y1) // 2 - Y0
    h.append("<div class='lcd' style='left:%dpx;top:%dpx;width:%dpx;height:%dpx;border-radius:8px'></div>"
             "<div class='arrow' style='left:%dpx;top:%dpx;border-right:11px solid %s'></div>"
             "<div class='arrow' style='left:%dpx;top:%dpx;border-left:11px solid %s'></div>"
             % (x0, y0 - Y0, x1 - x0, y1 - y0, x0 + 14, cy - 7, TH["txt"], x1 - 25, cy - 7, TH["txt"]))
    for x0, y0, x1, y1 in (CAT_BOX, ROW_BOX):
        h.append("<div class='lcd' style='left:%dpx;top:%dpx;width:%dpx;height:%dpx'></div>" % (x0, y0 - Y0, x1 - x0, y1 - y0))
    h.append("<div class='lcdcap' style='left:%dpx;top:%dpx'>CATEGORY</div>" % (CAT_BOX[0] + 18, CAT_BOX[1] - Y0 + 14))
    # the page arrows, top right of the presets panel (pads on top take the taps)
    px = ROW_BOX[2] - 18 - 2 * PG_W
    for i, d in enumerate(("up", "down")):
        x, y = px + i * PG_W, CAT_BOX[1] - Y0 + 8
        tri = ("border-left:9px solid transparent;border-right:9px solid transparent;border-%s:11px solid %s" %
               ("bottom" if d == "up" else "top", TH["txt"]))
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:0;height:0;%s;"
                 "filter:drop-shadow(0 0 4px rgba(64,170,255,.8))'></div>" % (x + PG_W // 2 - 9, y + PG_H // 2 - 6, tri))
    # column rules between the preset columns
    x, y, w, cols = ROW_LIST
    cw = (w - (cols - 1) * ROW_COL_GAP) // cols
    for c in range(1, cols):
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:1px;height:%dpx;background:#1c2c46'></div>"
                 % (x + c * (cw + ROW_COL_GAP) - ROW_COL_GAP // 2, LIST_Y - Y0 - 4, 8 * LIST_TH + 7 * LIST_GAP + 8))
    return "".join(h)


def row_html(on, w, h, solid):
    """A list row's picture: nothing (off), or lit: a solid cobalt bar (the category) or a glowing outline (the preset)."""
    if not on:
        return "<div style='width:%dpx;height:%dpx'></div>" % (w, h)
    if solid:
        return ("<div style='width:%dpx;height:%dpx;box-sizing:border-box;border-radius:6px;"
                "background:linear-gradient(180deg,%s,%s 55%%,%s);"
                "box-shadow:inset 0 1px 0 rgba(255,255,255,.45)'></div>" % (w, h, TH["acc_hi"], TH["acc"], TH["acc_lo"]))
    return ("<div style='width:%dpx;height:%dpx;box-sizing:border-box;border-radius:6px;border:2px solid %s;"
            "background:rgba(%s,.28);box-shadow:inset 0 0 12px rgba(%s,.45)'></div>" % (w, h, TH["acc"], TH["glow"], TH["glow"]))


def bg_sound():  # noqa: E302
    h = ["<div class='grain'></div>"]
    for p, name, x0, y0 in SLOTS:
        g = slot_geom(x0, y0)
        h.append("<div class='well' style='left:%dpx;top:%dpx;width:610px;height:600px'></div>" % (x0, y0 - Y0))
        h.append("<div class='title' style='left:%dpx;top:%dpx'>SOUND <b>%s</b></div>" % (x0 + 22, y0 - Y0 + 18, p.upper()))
        h.append("<div class='rule' style='left:%dpx;top:%dpx;width:566px'></div>" % (x0 + 22, y0 - Y0 + 66))
        h.append("<div class='rule' style='left:%dpx;top:%dpx;width:566px'></div>" % (x0 + 22, y0 - Y0 + 178))
        lx, ly = g["oct_label"]
        h.append("<div class='heading' style='left:%dpx;top:%dpx;width:120px;font-size:20px'>OCTAVE</div>" % (lx, ly - Y0 - 12))
        h.append("<div class='rule' style='left:%dpx;top:%dpx;width:566px'></div>" % (x0 + 22, y0 - Y0 + 330))
        for i, (cx, cy) in enumerate(g["knobs"]):
            top, vh, box = value_box(cx, cy, SLOT_R, SLOT_VS, 96)
            h.append(box)
            if i == 3:   # Level is the same for every sound: baked; knobs 1-3 get a picture per sound
                h.append("<div class='klabel' style='left:%dpx;top:%dpx;width:200px;font-size:23px'>LEVEL</div>"
                         % (cx - 100, label_top(cy) - Y0))
    return "".join(h)


def bg_fx():
    h = ["<div class='grain'></div>"]
    for p, name, ks, x0, y0 in FX:
        h.append("<div class='well' style='left:%dpx;top:%dpx;width:610px;height:296px'></div>" % (x0, y0 - Y0))
        h.append("<div class='title' style='left:%dpx;top:%dpx'>%s</div>" % (x0 + 22, y0 - Y0 + 18, name))
        h.append("<div class='rule' style='left:%dpx;top:%dpx;width:566px'></div>" % (x0 + 22, y0 - Y0 + 66))
    for key, label, cx, cy in fx_knobs():
        h.append(knob_block(key, label, cx, cy, FX_R, FX_VS, 96, 23))
    return "".join(h)


def hue_shift(img, deg):
    """The orb in another theme's colour: its hues turned by deg (alpha kept)."""
    if not deg:
        return img
    a = img.getchannel("A")
    h, sat, v = img.convert("RGB").convert("HSV").split()
    h = h.point(lambda x: (x + int(round(deg / 360.0 * 256))) % 256)
    out = Image.merge("HSV", (h, sat, v)).convert("RGB").convert("RGBA")
    out.putalpha(a)
    return out


def render_art():
    global TH
    os.makedirs(ART, exist_ok=True)
    tmp = os.path.join(ART, "_page.html")
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        orb = None
        for TH in THEMES:
            out = os.path.join(ART, TH["dir"]) if TH["dir"] else ART
            os.makedirs(out, exist_ok=True)
            var = ":root { --acc: %s; --glow: %s; --zglow: %s; }" % (TH["acc"], TH["glow"], ".35" if not TH["dir"] else ".55")

            def page(body):
                open(tmp, "w").write("<!doctype html><meta charset=utf-8><style>%s%s%s</style><body>%s</body>"
                                     % (PAGE_CSS, var, TH["css"], body))
                pg.goto("file://" + tmp)
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(150)

            # backgrounds
            for name, fn in (("player", bg_player), ("browse", bg_browse), ("sound", bg_sound), ("fx", bg_fx)):
                page(fn())
                Image.open(io.BytesIO(pg.screenshot())).convert("RGB").save(os.path.join(out, "bg_%s.png" % name), optimize=True)

            # filmstrips: knobs in the theme's accent; the orb drawn once and turned to the theme's hue
            page("")
            js = DRAW_JS if not TH["dir"] else DRAW_JS.replace(LIVE, TH["acc"]).replace("31,111,255", TH["glow"]).replace("80,150,255", TH["glow"]) \
                        .replace("#4d8dff", TH["ptr"])
            pg.add_script_tag(content=js)
            for r in sorted({PLAYER_R, SLOT_R, FX_R}):
                sz = 2 * r + 10
                frames = [png(pg.evaluate("([s, v]) => knob(s, v)", [sz, i / 127])) for i in range(128)]
                strip(frames, sz).save(os.path.join(out, "knob%d.png" % r), optimize=True)
            if orb is None:
                frames = [png(pg.evaluate("([S, p, n, l]) => orb(S, p, n, l)", [ORB_SIZE, ph, ORB_PHASES, lv]))
                          for lv in range(ORB_LEVELS) for ph in range(ORB_PHASES)]
                orb = strip(frames, ORB_SIZE)
            hue_shift(orb, TH["orb_hue"]).save(os.path.join(out, "orb.png"), optimize=True)

            # selector segments
            sizes = [("cat", CAT_SW, CAT_SH), ("oct", OCT_SW, OCT_SH)] + \
                    [("snd%d" % n, snd_sw(n), SND_H) for n in sorted({len(v) for v in PER.values()})]
            for kind, w, h in sizes:
                for on in (0, 1):
                    pg.set_content("<style>body{margin:0;background:transparent}</style>" + seg_html(on, w, h))
                    shot = pg.screenshot(clip={"x": 0, "y": 0, "width": w, "height": h}, omit_background=True)
                    Image.open(io.BytesIO(shot)).save(os.path.join(out, "seg_%s_%s.png" % (kind, "on" if on else "off")))

            # BROWSE's rows (off: the LCD; lit: a bar or an outline). MPC flattens a row's picture onto a solid colour,
            # so each is cut from the LCD it sits on (rows are 54 px apart, a multiple of the 3 px scanlines, so one cut
            # fits every row of a column)
            lcd = Image.open(os.path.join(out, "bg_browse.png")).convert("RGBA")
            for kind, x, w, solid in (("cat", CAT_LIST[0], CAT_LIST[2], True), ("row", ROW_LIST[0], row_col_w(), False)):
                under = lcd.crop((x, LIST_Y - Y0, x + w, LIST_Y - Y0 + LIST_TH))
                for on in (0, 1):
                    pg.set_content("<style>body{margin:0;background:transparent}</style>" + row_html(on, w, LIST_TH, solid))
                    shot = Image.open(io.BytesIO(pg.screenshot(clip={"x": 0, "y": 0, "width": w, "height": LIST_TH},
                                                               omit_background=True))).convert("RGBA")
                    cut = under.copy()
                    cut.alpha_composite(shot)
                    cut.convert("RGB").save(os.path.join(out, "%s_%s.png" % (kind, "on" if on else "off")))

            # knob-name strips, one per sound. MPC flattens a picture onto a solid colour, so each is drawn onto the
            # panel it sits on (slot A's; slot B's panel is the same drawing 630 px to the right)
            g = slot_geom(*SLOTS[0][2:])
            lx, ly = g["knobs"][0][0] - SLOT_KNOB_DX // 2, label_top(g["knobs"][0][1]) - 3 - Y0
            panel = Image.open(os.path.join(out, "bg_sound.png")).convert("RGBA").crop((lx, ly, lx + LBL_W, ly + LBL_H))
            for snd in SOUNDS:
                pg.set_content("<style>%s body{margin:0;background:transparent}</style>%s" % (FONT_CSS, labels_html(KNOB_LABELS[snd])))
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(80)
                shot = pg.screenshot(clip={"x": 0, "y": 0, "width": LBL_W, "height": LBL_H}, omit_background=True)
                lab = Image.open(io.BytesIO(shot)).convert("RGBA")
                on = panel.copy()   # opaque: drawn with margin=0, over its own panel
                on.alpha_composite(lab)
                lab = on
                lab.save(os.path.join(out, "lbl_%s.png" % snd.lower()))
        TH = THEMES[0]
        for w, h in pad_sizes():   # the clear pads that take the taps (the same in every theme)
            Image.new("RGBA", (w, h), (0, 0, 0, 0)).save(os.path.join(ART, "pad_%dx%d.png" % (w, h)))
        b.close()
    os.remove(tmp)


def row_col_w():
    x, y, w, cols = ROW_LIST
    return (w - (cols - 1) * ROW_COL_GAP) // cols


def pad_sizes():
    return {(STRIP_PAD, STRIP[3] - STRIP[1]), (CAT_LIST[2], LIST_TH), (row_col_w(), LIST_TH), (PG_W, PG_H),
            (THEME_PAD, THEME_BOX[3] - THEME_BOX[1])}


# --- layout.conf ----------------------------------------------------------------------------------------
def write_layout():
    open(os.path.join(HERE, "skin.css"), "w").write(SKIN_CSS)
    L = ["# generated by make_skin.py: edit that script, not this file",
         "theme_bg=c4c8cc", "theme_ink=eef3fa", "theme_ink_dim=7ff0ff", "theme_accent=1f6fff",
         "theme_seg_active_tx=ffffff", "art_css=skin.css",
         "qlinks_track = velocity,breath,attack,release,air,dark,lofi,motion,master", ""]

    def themed(fn):   # fn(th, when) -> lines, once per theme
        for n, th in enumerate(THEMES):
            L.extend(fn(th, " when=theme:%d" % n))

    def knob(th, w, key, label, cx, cy, r, vs, bw):
        tx = th["txt"].lstrip("#")
        return ('knob cx=%d cy=%d r=%d label="%s" key=%s strip=%s ns=0 vs=%d bw=%d ink=%s ink_dim=%s%s'
                % (cx, cy, r, label.upper() or key.upper(), key, art("knob%d.png" % r, th), vs, bw, tx, tx, w))

    # PLAYER
    L.append("[tab PLAYER]")
    ox, oy = PLAYER["orb"]
    x0, y0, x1, y1 = STRIP
    cy, ph = (y0 + y1) // 2, y1 - y0
    themed(lambda th, w: ["art file=%s fit=stretch%s" % (art("bg_player.png", th), w),
                          "meter cx=%d cy=%d w=%d h=%d key=orb strip=%s frames=%d%s"
                          % (ox, oy, ORB_SIZE, ORB_SIZE, art("orb.png", th), ORB_PHASES * ORB_LEVELS, w)] +
                         [knob(th, w, key, label, cx, cy_, PLAYER_R, PLAYER_VS, PLAYER_BW) for key, label, cx, cy_ in PLAYER["knobs"]] +
                         ['readout cx=640 cy=%d w=%d h=%d label="" key=p_name box=0 tsize=34 tcolor=%s tweight=bold%s'
                          % (cy, x1 - x0 - 2 * STRIP_PAD, ph - 4, th["txt"].lstrip("#"), w)])
    for key, cx in (("p_prev", x0 + STRIP_PAD // 2), ("p_next", x1 - STRIP_PAD // 2)):
        pad = "art/pad_%dx%d.png" % (STRIP_PAD, ph)
        L.append('button cx=%d cy=%d w=%d h=%d label="" key=%s img=%s img_on=%s' % (cx, cy, STRIP_PAD, ph, key, pad, pad))
    L.append('qlinks "PLAYER" = ' + ",".join(k for k, *_ in PLAYER["knobs"]))
    L.append("")

    # BROWSE
    L.append("[tab BROWSE]")
    rows_h = 8 * LIST_TH + 7 * LIST_GAP
    cx_, cy_, cw_ = CAT_LIST
    x, y, w, cols = ROW_LIST
    cw = row_col_w()
    hy = CAT_BOX[1] + 8 + PG_H // 2
    px = ROW_BOX[2] - 18 - 2 * PG_W
    tx0, ty0, tx1, ty1 = THEME_BOX
    tcy = (ty0 + ty1) // 2
    themed(lambda th, wh: [
        "art file=%s fit=stretch%s" % (art("bg_browse.png", th), wh),
        "list x=%d y=%d w=%d h=%d key=cat cols=1 rows=8 tap=no th=%d gap=%d tsize=30 tcolor=%s tweight=bold "
        "talign=left tx=16 img=%s img_on=%s%s" % (cx_, cy_, cw_, rows_h, LIST_TH, LIST_GAP, th["txt"].lstrip("#"),
                                                  art("cat_off.png", th), art("cat_on.png", th), wh),
        "list x=%d y=%d w=%d h=%d key=row cols=%d rows=8 order=cols tap=no th=%d gap=%d tsize=26 tcolor=%s "
        "tweight=semibold talign=left tx=14 img=%s img_on=%s%s" % (x, y, w, rows_h, cols, LIST_TH, LIST_GAP,
                                                                  th["row_tx"].lstrip("#"), art("row_off.png", th),
                                                                  art("row_on.png", th), wh),
        'readout cx=%d cy=%d w=420 h=%d label="" key=b_head box=0 tsize=20 tcolor=%s tweight=bold talign=left%s'
        % (ROW_BOX[0] + 18 + 210, hy, PG_H, th["txt_dim"].lstrip("#"), wh),
        'readout cx=%d cy=%d w=150 h=%d label="" key=b_page box=0 tsize=20 tcolor=%s tweight=bold talign=right%s'
        % (px - 8 - 75, hy, PG_H, th["txt_dim"].lstrip("#"), wh),
        'readout cx=%d cy=%d w=%d h=%d label="" key=th_name box=0 tsize=22 tcolor=%s tweight=bold%s'
        % ((tx0 + tx1) // 2, tcy, tx1 - tx0 - 2 * THEME_PAD, ty1 - ty0 - 4, th["txt"].lstrip("#"), wh)])
    for r in range(8):
        pad = "art/pad_%dx%d.png" % (cw_, LIST_TH)
        L.append('button cx=%d cy=%d w=%d h=%d label="" key=cpick_%d img=%s img_on=%s'
                 % (cx_ + cw_ // 2, cy_ + r * (LIST_TH + LIST_GAP) + LIST_TH // 2, cw_, LIST_TH, r + 1, pad, pad))
    for c in range(cols):
        for r in range(8):
            pad = "art/pad_%dx%d.png" % (cw, LIST_TH)
            L.append('button cx=%d cy=%d w=%d h=%d label="" key=rpick_%d img=%s img_on=%s'
                     % (x + c * (cw + LIST_GAP) + cw // 2, y + r * (LIST_TH + LIST_GAP) + LIST_TH // 2, cw, LIST_TH,
                        c * 8 + r + 1, pad, pad))
    for i, key in enumerate(("pg_prev", "pg_next")):
        pad = "art/pad_%dx%d.png" % (PG_W, PG_H)
        L.append('button cx=%d cy=%d w=%d h=%d label="" key=%s img=%s img_on=%s' % (px + i * PG_W + PG_W // 2, hy, PG_W, PG_H, key, pad, pad))
    for key, bx in (("th_prev", tx0 + THEME_PAD // 2), ("th_next", tx1 - THEME_PAD // 2)):
        pad = "art/pad_%dx%d.png" % (THEME_PAD, ty1 - ty0)
        L.append('button cx=%d cy=%d w=%d h=%d label="" key=%s img=%s img_on=%s' % (bx, tcy, THEME_PAD, ty1 - ty0, key, pad, pad))
    L.append("")

    # SOUND: a category's sounds follow <slot>_look (theme x 8 + category), the knob names <slot>_lbl (theme x 23 + sound)
    L.append("[tab SOUND]")
    themed(lambda th, w: ["art file=%s fit=stretch%s" % (art("bg_sound.png", th), w)])
    for p, name, x0, y0 in SLOTS:
        g = slot_geom(x0, y0)
        themed(lambda th, w: [
            'enum_h cx=%d cy=%d label="" key=%s_cat options="%s" rows=2 sw=%d sh=%d img=%s img_on=%s%s'
            % (g["cat"][0], g["cat"][1], p, ",".join(x.upper() for x in CATS), CAT_SW, CAT_SH,
               art("seg_cat_off.png", th), art("seg_cat_on.png", th), w),
            'enum_h cx=%d cy=%d label="" key=%s_oct options="-2,-1,0,+1,+2" sw=%d sh=%d img=%s img_on=%s%s'
            % (g["oct"][0], g["oct"][1], p, OCT_SW, OCT_SH, art("seg_oct_off.png", th), art("seg_oct_on.png", th), w)])
        for n, th in enumerate(THEMES):
            for ci, c in enumerate(CATS[1:], 1):   # only the chosen category's sounds are shown
                k = len(PER[c])
                L.append('enum_h cx=%d cy=%d label="" key=%s_%s options="%s" sw=%d sh=%d img=%s img_on=%s when=%s_look:%d'
                         % (g["snd"][0], g["snd"][1], p, c.lower(),
                            ",".join(x.upper().replace("BOWED VIBES", "BOWED") for x in PER[c]), snd_sw(k), SND_H,
                            art("seg_snd%d_off.png" % k, th), art("seg_snd%d_on.png" % k, th), p, n * len(CATS) + ci))
        (cx1, cy1) = g["knobs"][0]
        L.append('picture x=%d y=%d w=%d h=%d key=%s_lbl margin=0 files="%s"'
                 % (cx1 - SLOT_KNOB_DX // 2, label_top(cy1) - 3, LBL_W, LBL_H, p,
                    ",".join(art("lbl_%s.png" % x.lower(), th) for th in THEMES for x in SOUNDS)))
    themed(lambda th, w: [knob(th, w, key, label, cx, cy_, SLOT_R, SLOT_VS, SLOT_BW) for key, label, cx, cy_ in slot_knobs()])
    L.append('qlinks "SOUND" = ' + ",".join(k for k, *_ in slot_knobs()))
    L.append("")

    # FX
    L.append("[tab FX]")
    themed(lambda th, w: ["art file=%s fit=stretch%s" % (art("bg_fx.png", th), w)] +
                         [knob(th, w, key, label, cx, cy_, FX_R, FX_VS, FX_BW) for key, label, cx, cy_ in fx_knobs()])
    # one Q-Link column (4 knobs, one press of the Q-Link button) per panel, top to bottom; "-" pads a 3-knob panel
    cols = []
    for p, *_ in FX:
        keys = [k for k, *_ in fx_knobs() if k.startswith(p + "_") or (p == "sb" and k == "master") or (p == "dr" and k == "a4")]
        cols += (keys + ["-"] * 4)[:4]
    L.append('qlinks "FX" = ' + ",".join(cols))
    open(os.path.join(HERE, "layout.conf"), "w").write("\n".join(L) + "\n")


def check_keys():
    """Every key the layout uses must exist in params.json (the build would fail later, less clearly)."""
    keys = {p["key"] for p in json.load(open(os.path.join(HERE, "..", "params.json")))["params"]}
    used = [k for k, *_ in PLAYER["knobs"]] + [k for k, *_ in slot_knobs()] + [k for k, *_ in fx_knobs()] + \
           ["orb", "a_cat", "b_cat", "a_oct", "b_oct", "a_look", "b_look", "a_lbl", "b_lbl", "theme", "th_name",
            "th_prev", "th_next"] + \
           ["%s_%s" % (x, c.lower()) for x in "ab" for c in CATS[1:]] + \
           ["p_name", "p_prev", "p_next", "b_head", "b_page", "pg_prev", "pg_next"] + \
           ["cat_%d" % i for i in range(1, 9)] + ["row_%d" % i for i in range(1, 25)] + \
           ["cpick_%d" % i for i in range(1, 9)] + ["rpick_%d" % i for i in range(1, 25)]
    missing = [k for k in used if k not in keys]
    if missing:
        raise SystemExit("make_skin: keys not in params.json: %s" % ", ".join(missing))
    unused = sorted(keys - set(used))
    if unused:
        print("note: params with no control on screen:", ", ".join(unused))


if __name__ == "__main__":
    check_keys()
    write_layout()
    render_art()
    print("skin art and layout.conf written to", HERE)
