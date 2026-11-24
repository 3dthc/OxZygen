#!/usr/bin/env python3
"""Render the README / catalog / release screenshots (docs/img/*.png) from the built skin art and vst/skin/layout.conf.

Composites each page as MPC draws it: the background, knob and meter filmstrip frames, segmented selectors, lists,
readouts and pictures, with the values below. Text MPC draws itself (values, segment and list text) is set in Inter.
Run from the repo root after vst/skin/make_skin.py:  python3 tools/screenshots.py
"""
import os, re, shlex
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIN = os.path.join(ROOT, "vst", "skin")
OUT = os.path.join(ROOT, "docs", "img")
Y0 = 86                     # the plugin area starts 86 px down MPC's screen
FONT = "/usr/share/fonts/opentype/inter/Inter-%s.otf"
THEMES = ["ALUMINUM", "GREEN", "NAVY", "GRAPHITE", "NEBULA"]
NCATS = 10


def font(size, weight="SemiBold"):
    return ImageFont.truetype(FONT % weight, size)


def parse():
    tabs, cur, glob = {}, None, {}
    for line in open(os.path.join(SKIN, "layout.conf")):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"\[tab (\w+)\]", line)
        if m:
            cur = tabs.setdefault(m.group(1), [])
            continue
        if cur is None:
            if "=" in line:
                k, v = line.split("=", 1)
                glob[k.strip()] = v.strip()
            continue
        parts = shlex.split(line)
        kind, attrs = parts[0], {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                attrs[k] = v
        cur.append((kind, attrs))
    return tabs, glob


def shown(a, st):
    w = a.get("when")
    if not w:
        return True
    k, v = w.split(":")
    return int(st.get(k, 0)) == int(v)


def img(path):
    return Image.open(os.path.join(SKIN, path)).convert("RGBA")


def frame(strip, n, i, w=None, h=None):
    fh = strip.height // n
    return strip.crop((0, i * fh, strip.width, (i + 1) * fh))


def text(d, xy, s, size, color, weight="SemiBold", anchor="mm"):
    d.text(xy, s, font=font(size, weight), fill="#" + color, anchor=anchor)


def render(tab, st, glob):
    base = None
    d = None
    for kind, a in tab:
        if not shown(a, st):
            continue
        if kind == "art":
            base = img(a["file"]).resize((1280, 628))
            d = ImageDraw.Draw(base)
        elif kind == "meter":
            s = img(a["strip"]); n = int(a["frames"])
            f = frame(s, n, min(n - 1, int(st.get(a["key"], 0))))
            cx, cy = int(a["cx"]), int(a["cy"]) - Y0
            base.paste(f, (cx - f.width // 2, cy - f.height // 2), f)
        elif kind == "knob":
            s = img(a["strip"]); v = st.get(a["key"], (0.5, ""))
            f = frame(s, s.height // s.width, round(v[0] * (s.height // s.width - 1)))
            cx, cy, r = int(a["cx"]), int(a["cy"]) - Y0, int(a["r"])
            base.paste(f, (cx - f.width // 2, cy - f.height // 2), f)
            vs = int(a["vs"])
            text(d, (cx, cy + r + 2 + vs * 0.62), v[1], vs, a["ink"])
        elif kind == "enum_h":
            opts = a["options"].split(","); rows = int(a.get("rows", 1)); cols = -(-len(opts) // rows)
            sw, sh = int(a["sw"]), int(a["sh"]); gap = 2
            W, H = cols * sw + (cols - 1) * gap, rows * sh + (rows - 1) * gap
            x0, y0 = int(a["cx"]) - W // 2, int(a["cy"]) - Y0 - H // 2
            off, on = img(a["img"]).resize((sw, sh)), img(a["img_on"]).resize((sw, sh))
            sel = int(st.get(a["key"], 0))
            for i, o in enumerate(opts):
                x, y = x0 + (i % cols) * (sw + gap), y0 + (i // cols) * (sh + gap)
                base.paste(on if i == sel else off, (x, y), on if i == sel else off)
                text(d, (x + sw / 2, y + sh / 2), o, 18,
                     glob["theme_seg_active_tx"] if i == sel else glob["theme_ink"], "Bold")
        elif kind == "list":
            items = st.get(a["key"] + "_items", [])
            sel = int(st.get(a["key"], 0))
            cols, rows, th, gap = int(a["cols"]), int(a["rows"]), int(a["th"]), int(a["gap"])
            x0, y0, w = int(a["x"]), int(a["y"]) - Y0, int(a["w"])
            cw = (w - (cols - 1) * gap) // cols
            off, on = img(a["img"]).resize((cw, th)), img(a["img_on"]).resize((cw, th))
            for i, s in enumerate(items[:cols * rows]):
                c, r_ = (i // rows, i % rows) if a.get("order") == "cols" else (i % cols, i // cols)
                x, y = x0 + c * (cw + gap), y0 + r_ * (th + gap)
                base.paste(on if i == sel else off, (x, y), on if i == sel else off)
                text(d, (x + int(a.get("tx", 12)), y + th / 2), s, round(int(a["tsize"]) * 0.64),
                     "ffffff" if i == sel else a["tcolor"], a.get("tweight", "bold").title().replace("Semibold", "SemiBold"), "lm")
        elif kind == "readout":
            s = st.get(a["key"])
            if s:
                cx, cy, w = int(a["cx"]), int(a["cy"]) - Y0, int(a["w"])
                al = a.get("talign", "center")
                x, anc = (cx - w // 2, "lm") if al == "left" else (cx + w // 2, "rm") if al == "right" else (cx, "mm")
                text(d, (x, cy), s, int(a["tsize"]) - 4, a["tcolor"], "Bold", anc)
        elif kind == "picture":
            files = a["files"].split(",")
            p = img(files[int(st.get(a["key"], 0))])
            base.paste(p, (int(a["x"]), int(a["y"]) - Y0), p)
    return base.convert("RGB")


def engine_state():
    """Real values and texts from the engine (tools/screenshots_state.c), after loading the first NOIR preset."""
    import subprocess, tempfile
    exe = os.path.join(tempfile.mkdtemp(), "state")
    wrap = os.environ.get("MPC_VST", os.path.join(os.path.dirname(ROOT), "mpc-vst-plugins")) + "/wrapper"
    subprocess.run(["cc", "-std=gnu11", "-I" + wrap, "-I" + ROOT + "/vst/build", "-I" + ROOT + "/vst",
                    ROOT + "/tools/screenshots_state.c", "-lm", "-lpthread", "-o", exe], check=True)
    out = subprocess.run([exe], check=True, capture_output=True, text=True, cwd=ROOT + "/vst").stdout
    st = {}
    for line in out.splitlines():
        k, n, raw, txt, unit = (line.split("\t") + [""] * 5)[:5]
        st[k] = (float(n), float(raw), txt, unit)
    return st


def main():
    tabs, glob = parse()
    E = engine_state()
    st = {}
    for k, (n, raw, txt, unit) in E.items():
        try:
            float(txt); st[k] = (min(1.0, max(0.0, n)), txt + (" " + unit if unit else ""))   # a knob value
        except ValueError:
            st[k] = int(round(raw)) if not k.startswith(("row_", "cat_")) else txt         # an option index
        if k in ("p_name", "b_head", "b_page", "th_name", "ds_name", "ms_name"):
            st[k] = txt
    st.update(theme=0, orb=16, cat=0, row=-1,
              cat_items=[E["cat_%d" % i][2] for i in range(1, 13)], row_items=[E["row_%d" % i][2] for i in range(1, 25)])
    for sl in "ab":
        st[sl + "_look"] = st[sl + "_cat"]          # theme 0: the look is the category
    player = browse = sound = fx = st
    os.makedirs(OUT, exist_ok=True)
    pages = {"player": ("PLAYER", player), "browse": ("BROWSE", browse), "sound": ("SOUND", sound), "fx": ("FX", fx)}
    for name, (tab, st) in pages.items():
        render(tabs[tab], st, glob).save(os.path.join(OUT, name + ".png"), optimize=True)
    m = Image.new("RGB", (1280, 314 * 3), (20, 21, 24))
    for i in range(5):
        st = dict(player, theme=i, a_look=i * NCATS + player["a_look"], b_look=i * NCATS + player["b_look"])
        m.paste(render(tabs["PLAYER"], st, glob).resize((640, 314), Image.LANCZOS), ((i % 2) * 640, (i // 2) * 314))
    m.save(os.path.join(OUT, "themes.png"), optimize=True)


if __name__ == "__main__":
    main()
