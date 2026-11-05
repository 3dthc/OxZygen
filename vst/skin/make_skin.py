#!/usr/bin/env python3
"""Generate the OxZygen MPC skin: artwork (Chromium via Playwright, Pillow) and layout.conf.

    python3 vst/skin/make_skin.py

Every coordinate lives here, so the baked artwork and MPC's live controls always line up. Writes:
  art/bg_player.png, art/bg_edit.png, art/bg_fx.png   tab backgrounds, 1280x628 (the plugin area)
  art/knob48.png, art/knob36.png                     knob filmstrips, 128 frames (light fixed, pointer and arc turn)
  art/orb.png                                        orb meter filmstrip: 2 energy levels x 17 frames, 360x360
  art/mute_*.png, art/solo_*.png                     layer toggles, off and on
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
BEZEL, PANEL, FG, DIM, LIVE, BRASS = "#12161d", "#0e1218", "#e4e9f1", "#6f7a8c", "#6fe0d6", "#d1a85c"

ORB_PHASES, ORB_LEVELS, ORB_SIZE = 17, 2, 360   # 34 frames x 360 px = 12240 px, under MPC's 12288 px strip limit

# --- layout -------------------------------------------------------------------------------------------
# knob: (key, label, cx, cy, r, value text size, touch width)
PLAYER = {
    "orb": (640, 400),
    "headings": [("VOICE", 120, 440, 170), ("ATMOSPHERE", 840, 1160, 170)],
    "knobs": [
        ("voice", "Voice", 200, 295), ("breath", "Breath", 360, 295),
        ("choir", "Choir", 200, 520), ("bells", "Bells", 360, 520),
        ("air", "Air", 920, 295), ("dark", "Dark", 1080, 295),
        ("space", "Space", 920, 520), ("motion", "Motion", 1080, 520),
    ],
}
PLAYER_R, PLAYER_VS, PLAYER_BW = 48, 24, 130

LAYERS = [("ch", "Choir", ["Vowel", "Attack", "Spread", "Level"]),
          ("vo", "Vowels", ["Morph", "Attack", "Formant", "Level"]),
          ("wi", "Winds", ["Breath", "Vibrato", "Tone", "Level"]),
          ("be", "Bells", ["Strike", "Decay", "Shimmer", "Level"]),
          ("sc", "Soundscape", ["Density", "Drift", "Width", "Level"]),
          ("tx", "Texture", ["Grain", "Pitch", "Smear", "Level"])]
EDIT_CARDS = [(x, y) for y in (100, 406) for x in (20, 440, 860)]   # card top-left, 400 x 296
EDIT_R, EDIT_VS, EDIT_BW = 36, 20, 90
TOGGLE_W, TOGGLE_H = 74, 34
SEG_W, SEG_H = 104, 32                  # Winds instrument selector segments (Flute | Ocarina | Sax)
WINDS_SEL = (860 + 200, 100 + 94)       # centre, on the Winds card under its title

FX = [("rv", "Reverb", ["Size", "Decay", "Mix"], 20, 100),
      ("dl", "Delay", ["Time", "Feedback", "Mix"], 650, 100),
      ("dr", "Drive", ["Amount", "Tone", "Mix"], 20, 406),
      ("sb", "Sub / Output", ["Level", "Tune", "Drop"], 650, 406)]
FX_R, FX_VS, FX_BW = 48, 24, 116   # Sub / Output has 4 knobs 122 px apart


def edit_knobs():
    out = []
    for (p, name, ks), (x0, y0) in zip(LAYERS, EDIT_CARDS):
        for i, k in enumerate(ks):
            out.append(("%s_%s" % (p, k.lower()), k, x0 + 62 + i * 92, y0 + 160))
    return out


def edit_toggles():
    out = []
    for (p, name, ks), (x0, y0) in zip(LAYERS, EDIT_CARDS):
        out.append(("%s_mute" % p, "mute", x0 + 400 - 142, y0 + 34))
        out.append(("%s_solo" % p, "solo", x0 + 400 - 60, y0 + 34))
    return out


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
    const steps = 36, tail = .32, col = w.hue ? '111,224,214' : '138,127,230';
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
  core.addColorStop(0, 'rgba(111,224,214,' + (level ? .17 : .06) + ')'); core.addColorStop(1, 'rgba(111,224,214,0)');
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
    x.strokeStyle = level ? (major ? LIVE : 'rgba(111,224,214,.35)') : (major ? '#6b7588' : '#3a4352');
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


def seg_html(on):
    """A blank segment plate; the renderer writes the option name on it (skin.css sets the font)."""
    bg = "linear-gradient(180deg,#3a2f1c,#1d1810)" if on else "linear-gradient(180deg,#1a2029,#0e1218)"
    hi = "#6b5630" if on else "#2f3746"
    return ("<div style='width:%dpx;height:%dpx;box-sizing:border-box;border:1px solid #000;border-radius:3px;"
            "background:%s;box-shadow:inset 0 1px 0 %s'></div>" % (SEG_W, SEG_H, bg, hi))


SKIN_CSS = """/* generated by make_skin.py: the selector's option names in the skin's condensed face */
@font-face { font-family: "BC"; font-weight: 600; src: url("fonts/BarlowCondensed-SemiBold.ttf"); }
.seg-tx { font-family: "BC", sans-serif; font-size: 16px; letter-spacing: 0.14em; text-transform: uppercase; }
.seg-sheen { display: none; }
"""


def toggle_html(label, on):
    bg = "linear-gradient(180deg,#3a2f1c,#1d1810)" if on else "linear-gradient(180deg,#2a313d,#161b24)"
    hi = "#6b5630" if on else "#465064"
    return ("<div style='width:%dpx;height:%dpx;box-sizing:border-box;border:1px solid #000;border-radius:3px;"
            "background:%s;box-shadow:inset 0 1px 0 %s;display:flex;align-items:center;justify-content:center;"
            "font:600 16px BC,sans-serif;letter-spacing:.14em;color:%s;padding-left:.14em'>%s</div>"
            % (TOGGLE_W, TOGGLE_H, bg, hi, BRASS if on else FG, label))


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
  background: radial-gradient(900px 520px at 50%% 45%%, #18212f 0%%, transparent 70%%), linear-gradient(180deg, #141922, #0b0e13); }
.grain { position: absolute; inset: 0; opacity: .05;
  background-image: repeating-linear-gradient(90deg, #fff 0 1px, transparent 1px 3px); mix-blend-mode: overlay; }
.vbox { position: absolute; background: #03060a; border: 1px solid #000; border-radius: 2px;
  box-shadow: inset 0 2px 5px #000, 0 1px 0 rgba(255,255,255,.05); }
.klabel { position: absolute; text-align: center; font-family: BC, sans-serif; font-weight: 600; color: %(FG)s;
  letter-spacing: .12em; text-transform: uppercase; }
.heading { position: absolute; display: flex; align-items: center; gap: 12px; font: 600 20px BC, sans-serif;
  letter-spacing: .24em; color: %(DIM)s; }
.heading::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, #2c3442, transparent); }
.well { position: absolute; background: %(PANEL)s; border: 1px solid #000; border-radius: 3px;
  box-shadow: inset 0 1px 0 #232a35, inset 0 0 40px rgba(0,0,0,.35), 0 1px 0 rgba(255,255,255,.03); }
.title { position: absolute; font: 700 22px BC, sans-serif; letter-spacing: .22em; color: %(FG)s; text-transform: uppercase; }
.title b { color: %(LIVE)s; font-weight: 700; }
""" % {"fonts": FONT_CSS, "FG": FG, "DIM": DIM, "PANEL": PANEL, "LIVE": LIVE}


def bg_player():
    ox, oy = PLAYER["orb"]
    h = ["<div class='grain'></div>"]
    # the orb's shadow on the panel (the orb itself is the live meter on top)
    h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:300px;height:300px;border-radius:50%%;"
             "background:#000;box-shadow:0 24px 56px 6px rgba(0,0,0,.8)'></div>" % (ox - 150, oy - Y0 - 150))
    # wordmark: mixed case, the Z carries the emphasis (larger, accent colour)
    h.append("<div class='title' style='left:0;width:1280px;top:%dpx;text-align:center;font-size:32px;"
             "letter-spacing:.16em;text-transform:none;line-height:40px'>Ox<b style='font-size:44px;"
             "vertical-align:-3px;letter-spacing:.1em'>Z</b>ygen</div>" % (144 - Y0))
    for text, x0, x1, y in PLAYER["headings"]:
        h.append("<div class='heading' style='left:%dpx;top:%dpx;width:%dpx'>%s</div>" % (x0, y - Y0 - 12, x1 - x0, text))
    for key, label, cx, cy in PLAYER["knobs"]:
        h.append(knob_block(key, label, cx, cy, PLAYER_R, PLAYER_VS, 74, 19))
    return "".join(h)


def bg_edit():
    h = ["<div class='grain'></div>"]
    for (p, name, ks), (x0, y0) in zip(LAYERS, EDIT_CARDS):
        h.append("<div class='well' style='left:%dpx;top:%dpx;width:400px;height:296px'></div>" % (x0, y0 - Y0))
        h.append("<div class='title' style='left:%dpx;top:%dpx'>%s</div>" % (x0 + 20, y0 - Y0 + 18, name))
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:360px;height:1px;"
                 "background:linear-gradient(90deg,#2c3442,transparent)'></div>" % (x0 + 20, y0 - Y0 + 66))
    for key, label, cx, cy in edit_knobs():
        h.append(knob_block(key, label, cx, cy, EDIT_R, EDIT_VS, 60, 16))
    return "".join(h)


def bg_fx():
    h = ["<div class='grain'></div>"]
    for p, name, ks, x0, y0 in FX:
        h.append("<div class='well' style='left:%dpx;top:%dpx;width:610px;height:296px'></div>" % (x0, y0 - Y0))
        h.append("<div class='title' style='left:%dpx;top:%dpx'>%s</div>" % (x0 + 22, y0 - Y0 + 18, name))
        h.append("<div style='position:absolute;left:%dpx;top:%dpx;width:566px;height:1px;"
                 "background:linear-gradient(90deg,#2c3442,transparent)'></div>" % (x0 + 22, y0 - Y0 + 66))
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
        for name, fn in (("player", bg_player), ("edit", bg_edit), ("fx", bg_fx)):
            page(fn())
            Image.open(io.BytesIO(pg.screenshot())).convert("RGB").save(os.path.join(ART, "bg_%s.png" % name), optimize=True)

        # filmstrips
        page("")
        pg.add_script_tag(content=DRAW_JS)
        for r in (PLAYER_R, EDIT_R):
            s = 2 * r + 10
            frames = [png(pg.evaluate("([s, v]) => knob(s, v)", [s, i / 127])) for i in range(128)]
            strip(frames, s).save(os.path.join(ART, "knob%d.png" % r), optimize=True)
        frames = [png(pg.evaluate("([S, p, n, l]) => orb(S, p, n, l)", [ORB_SIZE, ph, ORB_PHASES, lv]))
                  for lv in range(ORB_LEVELS) for ph in range(ORB_PHASES)]
        strip(frames, ORB_SIZE).save(os.path.join(ART, "orb.png"), optimize=True)

        # selector segments
        for on in (0, 1):
            pg.set_content("<style>body{margin:0;background:transparent}</style>" + seg_html(on))
            shot = pg.screenshot(clip={"x": 0, "y": 0, "width": SEG_W, "height": SEG_H}, omit_background=True)
            Image.open(io.BytesIO(shot)).save(os.path.join(ART, "seg_%s.png" % ("on" if on else "off")))

        # toggles
        for label in ("MUTE", "SOLO"):
            for on in (0, 1):
                pg.set_content("<style>%s body{background:transparent}</style>%s" % (FONT_CSS, toggle_html(label, on)))
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(100)
                shot = pg.screenshot(clip={"x": 0, "y": 0, "width": TOGGLE_W, "height": TOGGLE_H}, omit_background=True)
                Image.open(io.BytesIO(shot)).save(os.path.join(ART, "%s_%s.png" % (label.lower(), "on" if on else "off")))
        b.close()
    os.remove(tmp)


# --- layout.conf ----------------------------------------------------------------------------------------
def write_layout():
    open(os.path.join(HERE, "skin.css"), "w").write(SKIN_CSS)
    L = ["# generated by make_skin.py: edit that script, not this file",
         "theme_bg=12161d", "theme_ink=e4e9f1", "theme_ink_dim=6fe0d6", "theme_accent=d1a85c",
         "theme_seg_active_tx=d1a85c", "art_css=skin.css",
         "qlinks_track = voice,breath,choir,bells,air,dark,space,motion,master", ""]
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
    # EDIT
    L.append("[tab EDIT]")
    L.append("art file=art/bg_edit.png fit=stretch")
    for key, label, cx, cy in edit_knobs():
        L.append('knob cx=%d cy=%d r=%d label="%s" key=%s strip=art/knob%d.png ns=0 vs=%d bw=%d'
                 % (cx, cy, EDIT_R, label.upper(), key, EDIT_R, EDIT_VS, EDIT_BW))
    for key, kind, cx, cy in edit_toggles():
        L.append('toggle cx=%d cy=%d label="%s" key=%s img=art/%s_off.png img_on=art/%s_on.png w=%d h=%d ns=0 bw=%d'
                 % (cx, cy, kind.upper(), key, kind, kind, TOGGLE_W, TOGGLE_H, TOGGLE_W + 4))
    L.append('enum_h cx=%d cy=%d label="" key=wi_inst options="FLUTE,OCARINA,SAX" sw=%d sh=%d '
             'img=art/seg_off.png img_on=art/seg_on.png' % (WINDS_SEL[0], WINDS_SEL[1], SEG_W, SEG_H))
    ek = [k for k, *_ in edit_knobs()]
    L.append('qlinks "LAYERS 1-3" = ' + ",".join(ek[:12]))
    L.append('qlinks "LAYERS 4-6" = ' + ",".join(ek[12:]))
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
    used = [k for k, *_ in PLAYER["knobs"]] + [k for k, *_ in edit_knobs()] + [k for k, *_ in edit_toggles()] + \
           [k for k, *_ in fx_knobs()] + ["orb", "wi_inst"]
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
