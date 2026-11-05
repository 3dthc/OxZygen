#!/usr/bin/env python3
"""Generate the OxZygen MPC skin: artwork (Chromium via Playwright, Pillow) and layout.conf.

    python3 vst/skin/make_skin.py

Every coordinate lives here, so the baked artwork and MPC's live controls always line up. Writes:
  art/bg_player.png, art/bg_sound.png, art/bg_fx.png  tab backgrounds, 1280x628 (the plugin area)
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
BEZEL, PANEL, FG, DIM, LIVE, BRASS = "#1b1e23", "#16191e", "#eef1f5", "#8a919c", "#5cc8ff", "#d1a85c"

ORB_PHASES, ORB_LEVELS, ORB_SIZE = 17, 2, 360   # 34 frames x 360 px = 12240 px, under MPC's 12288 px strip limit

# --- layout -------------------------------------------------------------------------------------------
# knob: (key, label, cx, cy, r, value text size, touch width)
PLAYER = {
    "orb": (640, 400),
    "headings": [("VOICE", 120, 440, 170), ("ATMOSPHERE", 840, 1160, 170)],
    "knobs": [
        ("blend", "Blend", 200, 295), ("breath", "Breath", 360, 295),
        ("attack", "Attack", 200, 520), ("release", "Release", 360, 520),
        ("air", "Air", 920, 295), ("dark", "Dark", 1080, 295),
        ("space", "Space", 920, 520), ("motion", "Motion", 1080, 520),
    ],
}
PLAYER_R, PLAYER_VS, PLAYER_BW = 48, 24, 130

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
SLOT_R, SLOT_VS, SLOT_BW = 48, 24, 120
LBL_W, LBL_H = 3 * SLOT_KNOB_DX, 28    # the label strip under knobs 1-3


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
    return cy + r + 2 + max(26, round(vs * 1.2)) + 5


FX = [("rv", "Reverb", ["Size", "Decay", "Mix"], 20, 100),
      ("dl", "Delay", ["Time", "Feedback", "Mix"], 650, 100),
      ("dr", "Drive", ["Amount", "Tone", "Mix"], 20, 406),
      ("sb", "Sub / Output", ["Level", "Tune", "Drop"], 650, 406)]
FX_R, FX_VS, FX_BW = 48, 24, 116   # Sub / Output has 4 knobs 122 px apart


def fx_knobs():
    out = []
    for p, name, ks, x0, y0 in FX:
        n = len(ks) + (1 if p == "sb" else 0)
        step = 610 // (n + 1)
        for i, k in enumerate(ks):
            out.append(("%s_%s" % (p, k.lower()), k, x0 + step * (i + 1), y0 + 160))
        if p == "sb":
            out.append(("master", "Output", x0 + step * n, y0 + 160))
    return out


# --- artwork in Chromium ------------------------------------------------------------------------------
FONT_CSS = """
@font-face { font-family: 'BC'; font-weight: 600; src: url('file://%(f)s/BarlowCondensed-SemiBold.ttf'); }
@font-face { font-family: 'BC'; font-weight: 700; src: url('file://%(f)s/BarlowCondensed-Bold.ttf'); }
""" % {"f": FONTS}

DRAW_JS = r"""
const LIVE = '__LIVE__';
function knob(size, v) {
  const c = document.createElement('canvas'); c.width = c.height = size * 2;     // drawn at 2x, downsampled later
  const x = c.getContext('2d'); x.scale(size * 2 / 100, size * 2 / 100);
  const P = (deg, r) => [50 + r * Math.cos(deg * Math.PI / 180), 50 + r * Math.sin(deg * Math.PI / 180)];
  // outer hairline and tick scale (fixed)
  x.beginPath(); x.arc(50, 50, 48, 0, 2 * Math.PI); x.strokeStyle = '#1c2330'; x.lineWidth = 1; x.stroke();
  for (let i = 0; i <= 10; i++) {
    const d = 135 + i * 27, [a, b] = P(d, 42), [e, f] = P(d, i % 5 === 0 ? 47.5 : 45.5);
    x.beginPath(); x.moveTo(a, b); x.lineTo(e, f); x.strokeStyle = i % 5 === 0 ? '#8a94a6' : '#5c6678';
    x.lineWidth = i % 5 === 0 ? 1.8 : 1.4; x.stroke();
  }
  // value slot and arc
  x.lineCap = 'butt'; x.lineWidth = 3.4;
  x.beginPath(); x.arc(50, 50, 36, 135 * Math.PI / 180, 405 * Math.PI / 180); x.strokeStyle = '#03060a'; x.stroke();
  if (v > 0.002) { x.beginPath(); x.arc(50, 50, 36, 135 * Math.PI / 180, (135 + 270 * v) * Math.PI / 180);
    x.strokeStyle = LIVE; x.stroke(); }
  // machined cap: light from the top left stays put, only the pointer turns
  x.save(); x.shadowColor = 'rgba(0,0,0,.7)'; x.shadowBlur = 5; x.shadowOffsetX = 1.5; x.shadowOffsetY = 2.5;
  x.beginPath(); x.arc(50, 50, 27, 0, 2 * Math.PI); x.fillStyle = '#0a0d12'; x.fill(); x.restore();
  const g = x.createLinearGradient(30, 26, 72, 76);
  g.addColorStop(0, '#a3adbf'); g.addColorStop(.45, '#3e4656'); g.addColorStop(1, '#151a22');
  x.beginPath(); x.arc(50, 50, 26, 0, 2 * Math.PI); x.fillStyle = g; x.fill();
  x.lineWidth = 1; x.strokeStyle = '#000'; x.stroke();
  const t = x.createRadialGradient(44, 42, 2, 50, 50, 22);
  t.addColorStop(0, '#5a6476'); t.addColorStop(1, '#232a36');
  x.beginPath(); x.arc(50, 50, 21, 0, 2 * Math.PI); x.fillStyle = t; x.fill();
  x.strokeStyle = 'rgba(0,0,0,.45)'; x.stroke();
  x.beginPath(); x.ellipse(43, 40, 9, 4, -0.6, 0, 2 * Math.PI); x.fillStyle = 'rgba(255,255,255,.10)'; x.fill();
  const d = 135 + 270 * v, [a, b] = P(d, 7), [e, f] = P(d, 20);
  x.lineCap = 'round'; x.lineWidth = 2.8;
  x.beginPath(); x.moveTo(a + .6, b + .8); x.lineTo(e + .6, f + .8); x.strokeStyle = 'rgba(0,0,0,.6)'; x.stroke();
  x.beginPath(); x.moveTo(a, b); x.lineTo(e, f); x.strokeStyle = '#f1f5fb'; x.stroke();
  return c.toDataURL('image/png');
}

function rng(seed) { return () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }; }
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
    """A blank segment plate; the renderer writes the option name on it (skin.css sets the font)."""
    if on:
        bg = ("linear-gradient(180deg,rgba(92,200,255,.30),rgba(92,200,255,.10) 55%,rgba(20,60,90,.35)),"
              "linear-gradient(180deg,#2c3a48,#141c25)")
        sh = "inset 0 1px 0 rgba(170,225,255,.55),inset 0 0 12px rgba(92,200,255,.35),0 0 8px rgba(92,200,255,.25)"
        border = "#2f86b8"
    else:
        bg = ("repeating-linear-gradient(0deg,rgba(255,255,255,.025) 0 1px,transparent 1px 2px),"
              "linear-gradient(180deg,#4a5059 0%,#30353d 48%,#262a31 52%,#1d2026 100%)")
        sh = "inset 0 1px 0 rgba(255,255,255,.22),inset 0 -1px 0 rgba(0,0,0,.5)"
        border = "#07080a"
    return ("<div style='width:%dpx;height:%dpx;box-sizing:border-box;border:1px solid %s;border-radius:3px;"
            "background:%s;box-shadow:%s'></div>" % (w, h, border, bg, sh))


def labels_html(names):
    """Three knob names, centred under knobs 1-3 (a transparent strip a picture widget swaps per sound)."""
    cells = "".join("<div style='width:%dpx;text-align:center'>%s</div>" % (SLOT_KNOB_DX, n.upper()) for n in names)
    return ("<div style='display:flex;width:%dpx;height:%dpx;align-items:center;font:600 19px BC,sans-serif;"
            "letter-spacing:.12em;color:%s'>%s</div>" % (LBL_W, LBL_H, FG, cells))


SKIN_CSS = """/* generated by make_skin.py: the selector's option names in the skin's condensed face */
@font-face { font-family: "BC"; font-weight: 600; src: url("fonts/BarlowCondensed-SemiBold.ttf"); }
.seg-tx { font-family: "BC", sans-serif; font-size: 18px; letter-spacing: 0.14em; text-transform: uppercase; }
.seg-sheen { display: none; }
"""


def value_box(cx, cy, r, vs, width):
    """The dark readout behind MPC's live value, and where the baked name goes under it."""
    vh = max(26, round(vs * 1.2))
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
body { width: 1280px; height: 628px; overflow: hidden; position: relative;
  background: radial-gradient(1000px 420px at 50%% 0%%, rgba(255,255,255,.07), transparent 70%%),
    linear-gradient(180deg, #2a2e35, #1a1d22 60%%, #121418); }
.grain { position: absolute; inset: 0; opacity: .10;
  background-image: repeating-linear-gradient(0deg, #fff 0 1px, transparent 1px 2px, #000 2px 3px, transparent 3px 4px);
  mix-blend-mode: overlay; }
.vbox { position: absolute; background: #03060a; border: 1px solid #000; border-radius: 2px;
  box-shadow: inset 0 2px 5px #000, 0 1px 0 rgba(255,255,255,.05); }
.klabel { position: absolute; text-align: center; font-family: BC, sans-serif; font-weight: 600; color: %(FG)s;
  letter-spacing: .12em; text-transform: uppercase; }
.heading { position: absolute; display: flex; align-items: center; gap: 12px; font: 600 20px BC, sans-serif;
  letter-spacing: .24em; color: %(DIM)s; }
.heading::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, #4a515c, transparent); }
.well { position: absolute; border: 1px solid #050608; border-radius: 4px;
  background: repeating-linear-gradient(0deg, rgba(255,255,255,.018) 0 1px, transparent 1px 3px),
    linear-gradient(180deg, #23272d, %(PANEL)s 40%%, #111317);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.14), inset 0 -1px 0 rgba(0,0,0,.6), inset 0 0 30px rgba(0,0,0,.3),
    0 2px 6px rgba(0,0,0,.6); }
.well::before { content: ""; position: absolute; inset: 7px; pointer-events: none;   /* corner screws */
  background: radial-gradient(circle at 5px 5px, #9aa1ab 0 1.5px, #3a3f47 2.5px, #0b0c0f 4px, transparent 5px) 0 0 / 10px 10px no-repeat,
    radial-gradient(circle at 5px 5px, #9aa1ab 0 1.5px, #3a3f47 2.5px, #0b0c0f 4px, transparent 5px) 100%% 0 / 10px 10px no-repeat,
    radial-gradient(circle at 5px 5px, #9aa1ab 0 1.5px, #3a3f47 2.5px, #0b0c0f 4px, transparent 5px) 0 100%% / 10px 10px no-repeat,
    radial-gradient(circle at 5px 5px, #9aa1ab 0 1.5px, #3a3f47 2.5px, #0b0c0f 4px, transparent 5px) 100%% 100%% / 10px 10px no-repeat; }
.title { position: absolute; font: 700 22px BC, sans-serif; letter-spacing: .22em; color: %(FG)s; text-transform: uppercase; }
.title b { color: %(LIVE)s; font-weight: 700; }
""" % {"fonts": FONT_CSS, "FG": FG, "DIM": DIM, "PANEL": PANEL, "LIVE": LIVE}


def bg_player():
    ox, oy = PLAYER["orb"]
    h = ["<div class='grain'></div>"]
    # the orb's shadow on the panel (the orb itself is the live meter on top)
    h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:300px;height:300px;border-radius:50%%;"
             "background:#000;box-shadow:0 24px 56px 6px rgba(0,0,0,.8)'></div>" % (ox - 150, oy - Y0 - 150))
    # wordmark: all caps, the Z carries the emphasis (larger, accent colour)
    h.append("<div class='title' style='left:0;width:1280px;top:%dpx;text-align:center;font-size:32px;"
             "letter-spacing:.22em;line-height:40px'>OX<b style='font-size:46px;vertical-align:-4px;"
             "letter-spacing:.18em'>Z</b>YGEN</div>" % (144 - Y0))
    for text, x0, x1, y in PLAYER["headings"]:
        h.append("<div class='heading' style='left:%dpx;top:%dpx;width:%dpx'>%s</div>" % (x0, y - Y0 - 12, x1 - x0, text))
    for key, label, cx, cy in PLAYER["knobs"]:
        h.append(knob_block(key, label, cx, cy, PLAYER_R, PLAYER_VS, 74, 19))
    return "".join(h)


def bg_sound():
    h = ["<div class='grain'></div>"]
    for p, name, x0, y0 in SLOTS:
        g = slot_geom(x0, y0)
        h.append("<div class='well' style='left:%dpx;top:%dpx;width:610px;height:600px'></div>" % (x0, y0 - Y0))
        h.append("<div class='title' style='left:%dpx;top:%dpx'>SOUND <b>%s</b></div>" % (x0 + 22, y0 - Y0 + 18, p.upper()))
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:566px;height:1px;"
                 "background:linear-gradient(90deg,#4a515c,transparent)'></div>" % (x0 + 22, y0 - Y0 + 66))
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:566px;height:1px;"
                 "background:linear-gradient(90deg,#4a515c,transparent)'></div>" % (x0 + 22, y0 - Y0 + 178))
        lx, ly = g["oct_label"]
        h.append("<div class='heading' style='left:%dpx;top:%dpx;width:110px;font-size:18px'>OCTAVE</div>" % (lx, ly - Y0 - 12))
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:566px;height:1px;"
                 "background:linear-gradient(90deg,#4a515c,transparent)'></div>" % (x0 + 22, y0 - Y0 + 330))
        for i, (cx, cy) in enumerate(g["knobs"]):
            top, vh, box = value_box(cx, cy, SLOT_R, SLOT_VS, 74)
            h.append(box)
            if i == 3:   # Level is the same for every sound: baked; knobs 1-3 get a picture per sound
                h.append("<div class='klabel' style='left:%dpx;top:%dpx;width:200px;font-size:19px'>LEVEL</div>"
                         % (cx - 100, label_top(cy) - Y0))
    return "".join(h)


def bg_fx():
    h = ["<div class='grain'></div>"]
    for p, name, ks, x0, y0 in FX:
        h.append("<div class='well' style='left:%dpx;top:%dpx;width:610px;height:296px'></div>" % (x0, y0 - Y0))
        h.append("<div class='title' style='left:%dpx;top:%dpx'>%s</div>" % (x0 + 22, y0 - Y0 + 18, name))
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:566px;height:1px;"
                 "background:linear-gradient(90deg,#4a515c,transparent)'></div>" % (x0 + 22, y0 - Y0 + 66))
    for key, label, cx, cy in fx_knobs():
        h.append(knob_block(key, label, cx, cy, FX_R, FX_VS, 74, 19))
    return "".join(h)


def render_art():
    os.makedirs(ART, exist_ok=True)
    tmp = os.path.join(ART, "_page.html")
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})

        def page(body):
            open(tmp, "w").write("<!doctype html><meta charset=utf-8><style>%s</style><body>%s</body>" % (PAGE_CSS, body))
            pg.goto("file://" + tmp)
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(150)

        # backgrounds
        for name, fn in (("player", bg_player), ("sound", bg_sound), ("fx", bg_fx)):
            page(fn())
            Image.open(io.BytesIO(pg.screenshot())).convert("RGB").save(os.path.join(ART, "bg_%s.png" % name), optimize=True)

        # filmstrips
        page("")
        pg.add_script_tag(content=DRAW_JS)
        for r in (PLAYER_R,):
            s = 2 * r + 10
            frames = [png(pg.evaluate("([s, v]) => knob(s, v)", [s, i / 127])) for i in range(128)]
            strip(frames, s).save(os.path.join(ART, "knob%d.png" % r), optimize=True)
        frames = [png(pg.evaluate("([S, p, n, l]) => orb(S, p, n, l)", [ORB_SIZE, ph, ORB_PHASES, lv]))
                  for lv in range(ORB_LEVELS) for ph in range(ORB_PHASES)]
        strip(frames, ORB_SIZE).save(os.path.join(ART, "orb.png"), optimize=True)

        # selector segments, two sizes
        sizes = [("cat", CAT_SW, CAT_SH), ("oct", OCT_SW, OCT_SH)] + \
                [("snd%d" % n, snd_sw(n), SND_H) for n in sorted({len(v) for v in PER.values()})]
        for kind, w, h in sizes:
            for on in (0, 1):
                pg.set_content("<style>body{margin:0;background:transparent}</style>" + seg_html(on, w, h))
                shot = pg.screenshot(clip={"x": 0, "y": 0, "width": w, "height": h}, omit_background=True)
                Image.open(io.BytesIO(shot)).save(os.path.join(ART, "seg_%s_%s.png" % (kind, "on" if on else "off")))

        # knob-name strips, one per sound
        for snd in SOUNDS:
            pg.set_content("<style>%s body{margin:0;background:transparent}</style>%s" % (FONT_CSS, labels_html(KNOB_LABELS[snd])))
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(80)
            shot = pg.screenshot(clip={"x": 0, "y": 0, "width": LBL_W, "height": LBL_H}, omit_background=True)
            Image.open(io.BytesIO(shot)).save(os.path.join(ART, "lbl_%s.png" % snd.lower()))
        b.close()
    os.remove(tmp)


# --- layout.conf ----------------------------------------------------------------------------------------
def write_layout():
    open(os.path.join(HERE, "skin.css"), "w").write(SKIN_CSS)
    L = ["# generated by make_skin.py: edit that script, not this file",
         "theme_bg=12161d", "theme_ink=e4e9f1", "theme_ink_dim=6fe0d6", "theme_accent=d1a85c",
         "theme_seg_active_tx=d1a85c", "art_css=skin.css",
         "qlinks_track = blend,breath,attack,release,air,dark,space,motion,master", ""]
    # PLAYER
    L.append("[tab PLAYER]")
    L.append("art file=art/bg_player.png fit=stretch")
    ox, oy = PLAYER["orb"]
    L.append("meter cx=%d cy=%d w=%d h=%d key=orb strip=art/orb.png frames=%d"
             % (ox, oy, ORB_SIZE, ORB_SIZE, ORB_PHASES * ORB_LEVELS))
    for key, label, cx, cy in PLAYER["knobs"]:
        L.append('knob cx=%d cy=%d r=%d label="%s" key=%s strip=art/knob%d.png ns=0 vs=%d bw=%d'
                 % (cx, cy, PLAYER_R, label.upper(), key, PLAYER_R, PLAYER_VS, PLAYER_BW))
    L.append('qlinks "PLAYER" = ' + ",".join(k for k, *_ in PLAYER["knobs"]))
    L.append("")
    # SOUND
    L.append("[tab SOUND]")
    L.append("art file=art/bg_sound.png fit=stretch")
    for p, name, x0, y0 in SLOTS:
        g = slot_geom(x0, y0)
        L.append('enum_h cx=%d cy=%d label="" key=%s_cat options="%s" rows=2 sw=%d sh=%d '
                 'img=art/seg_cat_off.png img_on=art/seg_cat_on.png'
                 % (g["cat"][0], g["cat"][1], p, ",".join(x.upper() for x in CATS), CAT_SW, CAT_SH))
        for c in CATS[1:]:   # only the chosen category's sounds are shown
            n = len(PER[c])
            L.append('enum_h cx=%d cy=%d label="" key=%s_%s options="%s" sw=%d sh=%d '
                     'img=art/seg_snd%d_off.png img_on=art/seg_snd%d_on.png when=%s_cat:%s'
                     % (g["snd"][0], g["snd"][1], p, c.lower(), ",".join(x.upper().replace("BOWED VIBES", "BOWED") for x in PER[c]), snd_sw(n), SND_H,
                        n, n, p, c))
        L.append('enum_h cx=%d cy=%d label="" key=%s_oct options="-2,-1,0,+1,+2" sw=%d sh=%d '
                 'img=art/seg_oct_off.png img_on=art/seg_oct_on.png' % (g["oct"][0], g["oct"][1], p, OCT_SW, OCT_SH))
        (cx1, cy1) = g["knobs"][0]
        L.append('picture x=%d y=%d w=%d h=%d key=%s_sound files="%s"'
                 % (cx1 - SLOT_KNOB_DX // 2, label_top(cy1) - 3, LBL_W, LBL_H, p,
                    ",".join("art/lbl_%s.png" % x.lower() for x in SOUNDS)))
    for key, label, cx, cy in slot_knobs():
        L.append('knob cx=%d cy=%d r=%d label="%s" key=%s strip=art/knob%d.png ns=0 vs=%d bw=%d'
                 % (cx, cy, SLOT_R, label.upper() or key.upper(), key, SLOT_R, SLOT_VS, SLOT_BW))
    L.append('qlinks "SOUND" = ' + ",".join(k for k, *_ in slot_knobs()))
    L.append("")
    # FX
    L.append("[tab FX]")
    L.append("art file=art/bg_fx.png fit=stretch")
    for key, label, cx, cy in fx_knobs():
        L.append('knob cx=%d cy=%d r=%d label="%s" key=%s strip=art/knob%d.png ns=0 vs=%d bw=%d'
                 % (cx, cy, FX_R, label.upper(), key, FX_R, FX_VS, FX_BW))
    L.append('qlinks "FX" = ' + ",".join(k for k, *_ in fx_knobs()))
    open(os.path.join(HERE, "layout.conf"), "w").write("\n".join(L) + "\n")


def check_keys():
    """Every key the layout uses must exist in params.json (the build would fail later, less clearly)."""
    keys = {p["key"] for p in json.load(open(os.path.join(HERE, "..", "params.json")))["params"]}
    used = [k for k, *_ in PLAYER["knobs"]] + [k for k, *_ in slot_knobs()] + [k for k, *_ in fx_knobs()] + \
           ["orb", "a_cat", "b_cat", "a_oct", "b_oct", "a_sound", "b_sound"] + \
           ["%s_%s" % (x, c.lower()) for x in "ab" for c in CATS[1:]]
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
