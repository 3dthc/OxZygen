#!/usr/bin/env python3
"""Write presets.json (listed in MPC's PRESET menu) from the designs below.

    python3 vst/make_presets.py

Every preset starts from the parameter defaults and then sets its own values, so each one fully defines the
sound: switching presets never leaves a slot or effect from the previous one behind. Names stay under 24
characters (the wrapper's limit) and are original: no other library's preset names.

Each preset has one clear identity. Leads play alone (slot B off), the bright ones sit up an octave, and only
the dark group uses the Sub, so the set covers a real range instead of variations on one pad.
Texture Pitch steps (k2): 0 = -24, 14 = -12, 29 = -5, 43 = unison, 57 = +7, 71 = +12, 86 = +19, 100 = +24.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = json.load(open(os.path.join(HERE, "params.json")))["params"]
SKIP = {"orb", "a_sound", "b_sound"}   # engine-driven
import re
UI = re.compile(r"^(cat_|row_|cpick_|rpick_|p_|th_|ds_|ms_|b_head$|b_page$|theme$|preset$|[ab]_look$|[ab]_lbl$)")   # the browser and
# the theme: never in a preset (loading one must not change the theme or the browser's rows)


# sound name -> (category, that category's option)
SOUND = {"Choir": ("Voices", "Choir"), "Vowels": ("Voices", "Vowels"),
         "Flute": ("Winds", "Flute"), "Ocarina": ("Winds", "Ocarina"), "Sax": ("Winds", "Sax"),
         "Clarinet": ("Winds", "Clarinet"), "Oboe": ("Winds", "Oboe"),
         "Horn": ("Brass", "Horn"), "Mute Trumpet": ("Brass", "Mute Trumpet"), "Trombone": ("Brass", "Trombone"),
         "Strings": ("Strings", "Sustain"), "Tremolo": ("Strings", "Tremolo"),
         "Bells": ("Bells", "Church"), "Tubular": ("Bells", "Tubular"), "Vibes": ("Bells", "Vibes"),
         "Bowed Vibes": ("Bells", "Bowed Vibes"), "Glass": ("Bells", "Glass"),
         "Synth Pad": ("Synth", "Pad"), "Synth Lead": ("Synth", "Lead"), "Synth Brass": ("Synth", "Brass"),
         "Wind": ("Air", "Wind"), "Texture": ("Air", "Texture"),
         "Piano": ("Keys", "Piano"), "E-Piano": ("Keys", "E-Piano"), "Harp": ("Keys", "Harp"),
         "Glockenspiel": ("Mallets", "Glockenspiel"), "Hand Chimes": ("Mallets", "Hand Chimes"),
         "Kalimba": ("Mallets", "Kalimba"), "Marimba": ("Mallets", "Marimba")}


def slot(x, sound, oct="Mid", k1=50, k2=50, k3=50, level=75):
    cat, opt = SOUND[sound]
    return {x + "_cat": cat, "%s_%s" % (x, cat.lower()): opt, x + "_oct": oct,
            x + "_k1": k1, x + "_k2": k2, x + "_k3": k3, x + "_level": level}


def convert(vals):
    """Fold the retired Space and Blend knobs (0.5.6 and earlier) into what they did: Space scaled the reverb, Blend
    trimmed one slot. The designs keep their old values; the presets come out the same as they sounded."""
    v = dict(vals)
    sp = v.pop("space", 60) / 100.0
    if True:   # reverb: always rewritten, since every preset sat on Space's default if it didn't set it
        r_size, r_dec, r_mix = v.get("rv_size", 50) / 100.0, v.get("rv_decay", 50) / 100.0, v.get("rv_mix", 30) / 100.0
        v["rv_size"] = round(100 * (0.5 * r_size + 0.5 * sp))
        rt = (0.6 + 11.0 * r_dec * r_dec) * (0.7 + 0.6 * sp)
        v["rv_decay"] = round(100 * max(0.0, (rt - 0.6) / 13.2) ** 0.5)
        v["rv_mix"] = min(100, round(100 * min(0.9, r_mix * (0.35 + 1.3 * sp)) / 0.9))
    b = v.pop("blend", 50) / 100.0
    for x, side in (("a", min(1.0, 2 * (1 - b))), ("b", min(1.0, 2 * b))):
        if side < 1.0:
            v[x + "_level"] = round(v.get(x + "_level", 75) * side)
    return v


def A(*a, **k): return slot("a", *a, **k)
def B(*a, **k): return slot("b", *a, **k)
OFF = {"b_cat": "Off"}

DESIGNS = [
    ("Init", {}),
    # --- leads: one instrument, close and clear ---
    ("Lone Flute", dict(**A("Flute", k1=45, k2=60, k3=60), **OFF,
        attack=40, release=35, air=60, dark=25, space=45, rv_decay=40, rv_mix=22, motion=35)),
    ("Midnight Sax", dict(**A("Sax", k1=50, k2=55, k3=45), **OFF,
        release=40, dark=45, air=45, space=50, rv_mix=26, dl_mix=18, dl_time=62, dl_feedback=35,
        dr_mix=20, dr_amount=30, motion=40)),
    ("Clay Ocarina", dict(**A("Ocarina", k1=60, k2=40, k3=55), **OFF,
        release=40, air=55, dark=30, space=55, rv_mix=28, dl_mix=15, dl_time=58, motion=40)),
    ("Angel Lead", dict(**A("Vowels", k1=70, k2=75, k3=15, level=75), **B("Flute", oct="+1", k1=40, k2=50, k3=60, level=30),
        release=40, air=65, dark=20, space=65, dl_mix=20, dl_time=55, motion=40)),
    ("Torch Song", dict(**A("Vowels", k1=55, k2=55, k3=3, level=80), **OFF,
        attack=20, release=30, dark=20, air=65, space=45, rv_mix=22, dl_mix=28, dl_time=45, dl_feedback=40,
        dr_mix=60, dr_amount=55, dr_tone=70, motion=50)),
    # --- voices and pads ---
    ("Saint Air", dict(**A("Choir", k1=50, k2=60, k3=55, level=70), **B("Sax", k1=55, k2=45, k3=55, level=60),
        blend=60, release=60, air=55, dark=40, space=78, rv_size=70, rv_decay=70, rv_mix=40,
        dl_mix=16, dl_time=62, dl_feedback=40, motion=45)),
    ("Choir Drift", dict(**A("Choir", k1=30, k2=75, k3=65), **B("Vowels", k1=40, k2=45, k3=60, level=45),
        release=70, dark=45, air=55, space=80, rv_decay=70, motion=70)),
    ("High Heavens", dict(**A("Choir", oct="+1", k1=100, k2=80, k3=60, level=75),
        **B("Bells", oct="+1", k1=40, k2=70, k3=60, level=35),
        release=65, air=75, dark=15, space=85, rv_size=75, rv_decay=75, rv_mix=40, motion=50)),
    ("Monastery", dict(**A("Choir", oct="-1", k1=50, k2=35, k3=70, level=85), **OFF,
        release=75, dark=60, air=30, space=88, rv_size=85, rv_decay=85, rv_mix=45, motion=35)),
    ("Doo Choir", dict(**A("Vowels", k1=15, k2=50, k3=8, level=70), **B("Choir", k1=50, k2=40, k3=15, level=40),
        attack=30, release=25, dark=35, air=50, space=40, rv_decay=35, rv_mix=25, motion=30)),
    ("Scat Doos", dict(**A("Vowels", k1=4, k2=55, k3=0, level=80), **B("Vowels", oct="-1", k1=4, k2=40, k3=0, level=35),
        attack=0, release=12, dark=30, air=45, space=30, rv_size=40, rv_decay=30, rv_mix=18, motion=20)),
    # --- bells ---
    ("Glass Cathedral", dict(**A("Bells", k1=55, k2=70, k3=50), **B("Choir", oct="+1", k1=100, k2=60, k3=60, level=35),
        release=70, air=60, dark=20, space=85, rv_size=80, rv_decay=80, rv_mix=40)),
    ("Music Box Ghost", dict(**A("Bells", oct="+1", k1=75, k2=40, k3=30), **OFF,
        release=45, air=65, dark=20, space=60, rv_mix=32, dl_mix=30, dl_time=40, dl_feedback=45)),
    # --- air and texture ---
    ("Wind Over Water", dict(**A("Wind", k1=35, k2=65, k3=80, level=80), **B("Bells", oct="+1", k1=30, k2=85, k3=75, level=25),
        release=70, air=70, dark=30, space=85, rv_decay=75, motion=60)),
    ("Frozen Breath", dict(**A("Texture", k1=85, k2=86, k3=85), **B("Wind", k1=50, k2=50, k3=70, level=30),
        release=75, air=70, dark=35, space=90, rv_decay=90, rv_mix=45, motion=50)),
    # --- dark: driven, low, with the sub ---
    ("Astro Haze", dict(**A("Texture", k1=55, k2=57, k3=70, level=60), **B("Vowels", k1=60, k2=50, k3=50, level=50),
        release=65, dark=60, air=40, space=80, dl_mix=35, dl_time=68, dl_feedback=55, motion=70,
        sb_level=30, sb_drop=30)),
    ("After Hours Fog", dict(**A("Sax", k1=40, k2=55, k3=35), **B("Choir", k1=50, k2=50, k3=55, level=35),
        blend=40, release=50, dark=70, air=35, space=65, dl_mix=25, dl_time=70, dl_feedback=45,
        dr_mix=50, dr_amount=45, dr_tone=45, sb_level=45, sb_drop=20)),
    ("Black Choir Stabs", dict(**A("Choir", k1=0, k2=40, k3=10, level=85), **OFF,
        attack=20, release=15, dark=55, air=40, space=35, rv_decay=40, rv_mix=25,
        dr_mix=70, dr_amount=65, dr_tone=50, sb_level=28, sb_drop=45)),
    ("Dark Vowel Bed", dict(**A("Vowels", k1=10, k2=25, k3=55), **B("Choir", k1=50, k2=50, k3=60, level=40),
        release=60, dark=75, air=30, space=70, motion=55, dr_mix=25, dr_amount=35, sb_level=35, sb_drop=25)),
    # --- brass and reeds ---
    ("Distant Horn", dict(**A("Horn", oct="-1", k1=30, k2=40, k3=45, level=80), **OFF,
        attack=35, release=55, dark=40, air=35, space=75, rv_size=75, rv_decay=70, rv_mix=36, motion=30)),
    ("Smoke Trumpet", dict(**A("Mute Trumpet", k1=45, k2=55, k3=55), **OFF,
        release=35, dark=35, air=45, space=50, rv_mix=24, dl_mix=22, dl_time=60, dl_feedback=38, motion=35)),
    ("Low Brass Hymn", dict(**A("Trombone", oct="-1", k1=25, k2=45, k3=40, level=75), **B("Horn", k1=30, k2=40, k3=50, level=60),
        blend=55, attack=40, release=60, dark=45, air=30, space=78, rv_size=80, rv_decay=75, rv_mix=38, sb_level=20)),
    ("Reed Lament", dict(**A("Clarinet", k1=50, k2=50, k3=45), **OFF,
        release=45, dark=35, air=45, space=60, rv_mix=28, dl_mix=14, dl_time=64, motion=40)),
    ("Celtic Oboe", dict(**A("Oboe", k1=55, k2=50, k3=60), **B("Strings", oct="-1", k1=60, k2=60, k3=40, level=40),
        blend=65, release=50, air=50, dark=30, space=70, rv_decay=65, rv_mix=32, motion=40)),
    # --- strings ---
    ("Frost Strings", dict(**A("Strings", k1=75, k2=70, k3=40, level=80), **B("Choir", oct="+1", k1=90, k2=70, k3=70, level=30),
        release=70, dark=40, air=55, space=85, rv_size=80, rv_decay=80, rv_mix=42, motion=55)),
    ("Shiver", dict(**A("Tremolo", k1=60, k2=40, k3=35), **B("Wind", k1=40, k2=60, k3=70, level=30),
        release=60, dark=55, air=40, space=80, rv_decay=75, rv_mix=40, motion=50, sb_level=18)),
    # --- mallets and glass ---
    ("Bell Tower", dict(**A("Tubular", k1=80, k2=20, k3=55), **B("Choir", oct="-1", k1=50, k2=50, k3=70, level=30),
        release=65, air=50, dark=30, space=85, rv_size=85, rv_decay=80, rv_mix=40)),
    ("Midnight Vibes", dict(**A("Vibes", k1=60, k2=45, k3=50), **OFF,
        release=50, dark=45, air=40, space=60, rv_mix=28, dl_mix=22, dl_time=55, dl_feedback=40, sb_level=0)),
    ("Bowed Halo", dict(**A("Bowed Vibes", oct="+1", k1=40, k2=45, k3=60), **B("Glass", k1=50, k2=35, k3=60, level=45),
        release=75, air=65, dark=20, space=88, rv_size=85, rv_decay=85, rv_mix=44, motion=45)),
    ("Glass Prayer", dict(**A("Glass", k1=55, k2=30, k3=55), **B("Choir", k1=40, k2=60, k3=70, level=40),
        release=70, air=60, dark=25, space=85, rv_decay=80, rv_mix=40, motion=40)),
    # --- synths ---
    ("Juno Dawn", dict(**A("Synth Pad", k1=45, k2=55, k3=70, level=80), **OFF,
        release=60, air=50, dark=30, space=70, rv_decay=65, rv_mix=32, motion=45)),
    ("Neon Lead", dict(**A("Synth Lead", k1=60, k2=25, k3=45), **OFF,
        release=30, air=50, dark=25, space=45, rv_mix=22, dl_mix=28, dl_time=50, dl_feedback=40)),
    ("Night Drive Brass", dict(**A("Synth Brass", k1=40, k2=55, k3=60), **B("Horn", k1=30, k2=40, k3=50, level=40),
        blend=40, release=45, dark=40, air=40, space=60, rv_mix=28, dr_mix=25, dr_amount=30, sb_level=25, sb_drop=25)),
    ("Ghost Synth Choir", dict(**A("Synth Pad", oct="-1", k1=30, k2=40, k3=80, level=65), **B("Choir", k1=40, k2=60, k3=65, level=55),
        release=70, dark=60, air=35, space=82, rv_decay=80, rv_mix=40, motion=60, sb_level=25, sb_drop=30)),
    # --- 0.5.4 additions ---
    ("Vesper Choir", dict(**A("Choir", k1=20, k2=55, k3=60, level=80), **B("Strings", oct="-1", k1=60, k2=70, k3=35, level=45),
        release=70, dark=50, air=40, space=85, rv_size=85, rv_decay=80, rv_mix=42, motion=40)),
    ("Ooh Pad", dict(**A("Vowels", k1=0, k2=45, k3=60, level=75), **B("Synth Pad", k1=35, k2=40, k3=70, level=35),
        release=65, dark=40, air=45, space=70, rv_decay=65, rv_mix=34, motion=50)),
    ("Dah Section", dict(**A("Vowels", k1=50, k2=50, k3=0, level=80), **B("Vowels", oct="+1", k1=50, k2=65, k3=0, level=35),
        attack=0, release=15, dark=25, air=50, space=35, rv_mix=20, motion=20)),
    ("Bah Brass Doos", dict(**A("Vowels", k1=40, k2=35, k3=5, level=75), **B("Synth Brass", oct="-1", k1=30, k2=40, k3=40, level=35),
        attack=0, release=15, dark=35, air=40, space=35, rv_mix=18, dr_mix=20, dr_amount=25)),
    ("Cloister", dict(**A("Choir", oct="-1", k1=35, k2=45, k3=70, level=80), **B("Tubular", k1=85, k2=20, k3=40, level=25),
        release=80, dark=55, air=30, space=92, rv_size=90, rv_decay=90, rv_mix=48, motion=30)),
    ("Soprano Light", dict(**A("Choir", oct="+1", k1=90, k2=50, k3=50, level=75), **OFF,
        release=60, air=70, dark=15, space=80, rv_decay=75, rv_mix=40, motion=35)),
    ("Highland Flute", dict(**A("Flute", oct="+1", k1=55, k2=45, k3=70), **B("Wind", k1=30, k2=50, k3=60, level=20),
        release=40, air=60, dark=20, space=70, rv_decay=60, rv_mix=30, dl_mix=15, dl_time=55, motion=40)),
    ("Hollow Ocarina", dict(**A("Ocarina", oct="-1", k1=40, k2=55, k3=40), **OFF,
        release=45, dark=45, air=40, space=75, rv_decay=70, rv_mix=36, dl_mix=20, dl_time=66, dl_feedback=45)),
    ("Lowlight Clarinet", dict(**A("Clarinet", oct="-1", k1=40, k2=55, k3=35, level=100), **OFF,
        release=40, dark=50, air=35, space=55, rv_mix=26, dr_mix=20, dr_amount=25, sb_level=15)),
    ("Reed Choir", dict(**A("Oboe", k1=45, k2=45, k3=50, level=70), **B("Clarinet", oct="-1", k1=45, k2=50, k3=45, level=55),
        blend=55, release=55, dark=35, air=45, space=70, rv_decay=65, rv_mix=34, motion=35)),
    ("Sax and Smoke", dict(**A("Sax", k1=55, k2=65, k3=40), **B("Texture", k1=60, k2=43, k3=80, level=25),
        release=50, dark=60, air=35, space=70, dl_mix=25, dl_time=70, dl_feedback=50, dr_mix=30, dr_amount=35, sb_level=25)),
    ("Funeral Horns", dict(**A("Horn", oct="-1", k1=25, k2=50, k3=35, level=80), **B("Trombone", oct="-1", k1=20, k2=50, k3=30, level=55),
        attack=45, release=65, dark=60, air=25, space=85, rv_size=85, rv_decay=80, rv_mix=40, sb_level=25, sb_drop=20)),
    ("Harmon Night", dict(**A("Mute Trumpet", k1=60, k2=45, k3=45), **B("Vibes", k1=60, k2=40, k3=45, level=30),
        release=40, dark=40, air=40, space=55, rv_mix=24, dl_mix=25, dl_time=58, dl_feedback=35)),
    ("Bone Choir", dict(**A("Trombone", k1=35, k2=55, k3=45, level=70), **B("Choir", oct="-1", k1=20, k2=50, k3=50, level=50),
        release=60, dark=55, air=30, space=80, rv_decay=75, rv_mix=38, motion=35, sb_level=20)),
    ("Sorrow Cellos", dict(**A("Strings", oct="-1", k1=50, k2=55, k3=35, level=85), **OFF,
        release=70, dark=55, air=30, space=80, rv_decay=75, rv_mix=40, motion=40, sb_level=15)),
    ("Shimmer Tremolo", dict(**A("Tremolo", oct="+1", k1=70, k2=30, k3=60, level=70), **B("Glass", k1=40, k2=50, k3=60, level=35),
        release=60, air=60, dark=25, space=85, rv_decay=80, rv_mix=42, motion=40)),
    ("Storm Strings", dict(**A("Tremolo", oct="-1", k1=60, k2=20, k3=40, level=80), **B("Wind", k1=60, k2=70, k3=80, level=35),
        release=55, dark=60, air=40, space=75, dr_mix=25, dr_amount=30, sb_level=30, sb_drop=40, motion=60)),
    ("Snowfall Vibes", dict(**A("Vibes", oct="+1", k1=70, k2=55, k3=60), **OFF,
        release=55, air=60, dark=20, space=80, rv_decay=75, rv_mix=38, dl_mix=25, dl_time=50, dl_feedback=45)),
    ("Grave Bells", dict(**A("Tubular", oct="-1", k1=90, k2=30, k3=35), **B("Wind", k1=30, k2=50, k3=70, level=25),
        release=75, dark=60, air=30, space=90, rv_size=90, rv_decay=85, rv_mix=45, sb_level=20)),
    ("Crystal Rain", dict(**A("Glass", oct="+1", k1=20, k2=60, k3=70), **B("Bells", oct="+1", k1=50, k2=50, k3=80, level=30),
        release=65, air=70, dark=15, space=85, rv_decay=80, rv_mix=40, dl_mix=20, dl_time=45, motion=50)),
    ("Bowed Choir", dict(**A("Bowed Vibes", k1=50, k2=40, k3=55, level=70), **B("Choir", k1=60, k2=60, k3=65, level=45),
        release=75, air=55, dark=30, space=88, rv_decay=85, rv_mix=44, motion=45)),
    ("Ninety Pad", dict(**A("Synth Pad", k1=55, k2=65, k3=80), **OFF,
        release=55, air=50, dark=25, space=60, rv_mix=28, motion=50)),
    ("Velvet Pad", dict(**A("Synth Pad", k1=30, k2=35, k3=75, level=80), **B("Strings", k1=60, k2=70, k3=30, level=40),
        release=70, dark=55, air=35, space=78, rv_decay=75, rv_mix=38, motion=45, sb_level=15)),
    ("Square Lead", dict(**A("Synth Lead", k1=50, k2=10, k3=30), **OFF,
        release=25, air=40, dark=30, space=40, rv_mix=18, dl_mix=22, dl_time=48, dl_feedback=35)),
    ("Slide Lead", dict(**A("Synth Lead", k1=65, k2=70, k3=55), **OFF,
        release=35, air=50, dark=20, space=50, rv_mix=22, dl_mix=30, dl_time=55, dl_feedback=45, dr_mix=25, dr_amount=30)),
    ("Bloom Brass", dict(**A("Synth Brass", k1=30, k2=85, k3=65), **OFF,
        release=45, dark=35, air=45, space=60, rv_mix=26, motion=40)),
    ("Dark Synth Stabs", dict(**A("Synth Brass", oct="-1", k1=25, k2=60, k3=40), **OFF,
        attack=0, release=15, dark=50, air=30, space=40, rv_mix=20, dr_mix=40, dr_amount=45, sb_level=35, sb_drop=40)),
    ("Ghost Wind", dict(**A("Wind", k1=50, k2=80, k3=85), **B("Choir", oct="+1", k1=100, k2=60, k3=80, level=25),
        release=75, air=60, dark=35, space=85, rv_decay=80, rv_mix=40, motion=70)),
    ("Ember Field", dict(**A("Texture", k1=40, k2=43, k3=60), **B("Synth Pad", oct="-1", k1=25, k2=40, k3=60, level=35),
        release=70, dark=60, air=35, space=80, rv_decay=80, rv_mix=40, motion=60, sb_level=20)),
    ("Octave Dust", dict(**A("Texture", k1=70, k2=71, k3=90), **OFF,
        release=75, air=65, dark=25, space=88, rv_decay=85, rv_mix=44, motion=55)),
    # --- 0.5.5: late-night R&B ---
    ("Underwater Vox", dict(**A("Vowels", oct="-1", k1=10, k2=30, k3=60, level=80), **B("Synth Pad", oct="-1", k1=20, k2=40, k3=80, level=40),
        release=75, dark=80, air=20, space=85, rv_size=85, rv_decay=80, rv_mix=45, dl_mix=25, dl_time=72, dl_feedback=55,
        motion=60, sb_level=40, sb_drop=35)),
    ("Codeine Choir", dict(**A("Choir", oct="-1", k1=20, k2=60, k3=65, level=80), **B("Texture", k1=60, k2=29, k3=85, level=30),
        release=80, dark=75, air=25, space=88, rv_decay=85, rv_mix=45, dl_mix=20, dl_time=75, dl_feedback=50,
        motion=55, dr_mix=20, dr_amount=30, sb_level=35, sb_drop=40)),
    ("4AM Hook Vox", dict(**A("Vowels", k1=60, k2=45, k3=10, level=80), **OFF,
        release=40, dark=55, air=45, space=60, rv_mix=30, dl_mix=35, dl_time=62, dl_feedback=50,
        dr_mix=35, dr_amount=40, dr_tone=55, motion=45, sb_level=30, sb_drop=30)),
    ("Haunted Ad Libs", dict(**A("Vowels", oct="+1", k1=85, k2=70, k3=20, level=70), **B("Choir", oct="+1", k1=100, k2=70, k3=50, level=30),
        release=55, dark=50, air=55, space=85, rv_size=85, rv_decay=85, rv_mix=48, dl_mix=40, dl_time=66, dl_feedback=60,
        motion=60)),
    ("Purple Sax", dict(**A("Sax", oct="-1", k1=45, k2=60, k3=30), **B("Synth Pad", oct="-1", k1=20, k2=40, k3=70, level=30),
        release=50, dark=70, air=30, space=70, rv_mix=30, dl_mix=30, dl_time=70, dl_feedback=50,
        dr_mix=30, dr_amount=35, sb_level=35, sb_drop=30)),
    ("Lean Flute", dict(**A("Flute", oct="-1", k1=60, k2=65, k3=35, level=95), **OFF,
        release=50, dark=65, air=35, space=75, rv_decay=70, rv_mix=36, dl_mix=35, dl_time=68, dl_feedback=55,
        motion=55, sb_level=30, sb_drop=40)),
    ("Desert Horn", dict(**A("Horn", oct="-1", k1=35, k2=55, k3=30, level=85), **B("Wind", k1=40, k2=60, k3=70, level=25),
        attack=30, release=65, dark=70, air=25, space=85, rv_size=85, rv_decay=80, rv_mix=42, dl_mix=20, dl_time=74,
        dr_mix=30, dr_amount=40, sb_level=40, sb_drop=35)),
    ("Velvet Room Strings", dict(**A("Strings", oct="-1", k1=60, k2=50, k3=25, level=85), **B("Vowels", k1=10, k2=40, k3=60, level=30),
        release=70, dark=75, air=25, space=80, rv_decay=75, rv_mix=40, motion=50, sb_level=35, sb_drop=30)),
    ("Late Night Keys", dict(**A("Vibes", k1=55, k2=60, k3=30), **B("Synth Pad", oct="-1", k1=20, k2=35, k3=70, level=30),
        release=50, dark=65, air=30, space=65, rv_mix=32, dl_mix=28, dl_time=64, dl_feedback=45,
        dr_mix=25, dr_amount=30, sb_level=35, sb_drop=25)),
    ("Faded Bells", dict(**A("Bells", oct="-1", k1=30, k2=70, k3=75), **B("Texture", k1=55, k2=43, k3=80, level=30),
        release=70, dark=70, air=30, space=85, rv_decay=85, rv_mix=45, dl_mix=30, dl_time=70, dl_feedback=55,
        motion=50, sb_level=30, sb_drop=35)),
    ("Codeine Pad", dict(**A("Synth Pad", oct="-1", k1=25, k2=55, k3=90, level=85), **B("Choir", oct="-1", k1=20, k2=50, k3=70, level=30),
        release=80, dark=70, air=30, space=85, rv_decay=80, rv_mix=42, dl_mix=20, dl_time=72, motion=65,
        dr_mix=25, dr_amount=30, sb_level=45, sb_drop=40)),
    ("Night Ride Lead", dict(**A("Synth Lead", oct="-1", k1=35, k2=60, k3=60), **OFF,
        release=35, dark=55, air=35, space=60, rv_mix=28, dl_mix=38, dl_time=66, dl_feedback=55,
        dr_mix=40, dr_amount=45, dr_tone=50, sb_level=40, sb_drop=50)),
    ("Ghost Synth Brass", dict(**A("Synth Brass", oct="-1", k1=20, k2=70, k3=70, level=85), **B("Vowels", oct="-1", k1=0, k2=35, k3=60, level=30),
        release=55, dark=70, air=30, space=75, rv_decay=70, rv_mix=36, dl_mix=25, dl_time=70, dl_feedback=45,
        dr_mix=35, dr_amount=40, sb_level=45, sb_drop=45)),
    ("Siren Glide", dict(**A("Synth Lead", k1=55, k2=95, k3=70), **B("Vowels", oct="+1", k1=85, k2=70, k3=40, level=25),
        release=50, dark=45, air=45, space=80, rv_decay=80, rv_mix=42, dl_mix=40, dl_time=60, dl_feedback=60, motion=50)),
    ("Smoke Room", dict(**A("Texture", oct="-1", k1=75, k2=43, k3=90, level=85), **B("Sax", oct="-1", k1=40, k2=60, k3=25, level=30),
        release=80, dark=80, air=25, space=90, rv_size=90, rv_decay=90, rv_mix=48, dl_mix=25, dl_time=74, dl_feedback=55,
        motion=60, sb_level=35, sb_drop=40)),
    ("Heartbreak Haze", dict(**A("Texture", k1=60, k2=29, k3=80, level=75), **B("Choir", k1=40, k2=60, k3=70, level=40),
        release=80, dark=65, air=40, space=88, rv_decay=85, rv_mix=46, dl_mix=30, dl_time=68, dl_feedback=55,
        motion=70, dr_mix=20, dr_amount=30, sb_level=30, sb_drop=35)),
    # --- 0.5.6: horror and film score ---
    ("Possessed Choir", dict(**A("Choir", oct="-2", k1=10, k2=80, k3=80, level=85), **B("Texture", oct="-1", k1=80, k2=0, k3=95, level=35),
        release=85, dark=70, air=30, space=92, rv_size=95, rv_decay=92, rv_mix=50, motion=80,
        dr_mix=30, dr_amount=40, sb_level=40, sb_drop=60)),
    ("Cluster Strings", dict(**A("Tremolo", k1=100, k2=60, k3=50, level=80), **B("Tremolo", oct="+1", k1=100, k2=60, k3=60, level=45),
        release=60, dark=50, air=40, space=85, rv_decay=80, rv_mix=42, motion=90, sb_level=20)),
    ("Dread Drone", dict(**A("Strings", oct="-2", k1=90, k2=90, k3=20, level=85), **B("Wind", oct="-1", k1=70, k2=90, k3=80, level=40),
        release=85, dark=80, air=20, space=90, rv_size=90, rv_decay=90, rv_mix=48, motion=70,
        dr_mix=35, dr_amount=50, dr_tone=35, sb_level=45, sb_drop=70)),
    ("Nursery Ghost", dict(**A("Bells", oct="+1", k1=80, k2=50, k3=90), **B("Glass", oct="+1", k1=30, k2=80, k3=60, level=30),
        release=65, dark=35, air=55, space=88, rv_decay=85, rv_mix=46, dl_mix=35, dl_time=55, dl_feedback=60, motion=60)),
    ("Funeral Toll", dict(**A("Tubular", oct="-2", k1=100, k2=40, k3=30, level=90), **B("Choir", oct="-1", k1=10, k2=50, k3=80, level=30),
        release=90, dark=70, air=25, space=95, rv_size=95, rv_decay=95, rv_mix=50, sb_level=30, sb_drop=50)),
    ("Whisper Swarm", dict(**A("Texture", oct="+1", k1=20, k2=100, k3=100, level=75), **B("Vowels", oct="+1", k1=100, k2=100, k3=80, level=25),
        release=80, dark=40, air=70, space=90, rv_decay=88, rv_mix=48, dl_mix=30, dl_time=40, dl_feedback=65, motion=100)),
    ("Attic Wind", dict(**A("Wind", oct="-1", k1=80, k2=100, k3=100, level=85), **B("Bowed Vibes", oct="-1", k1=60, k2=90, k3=40, level=30),
        release=85, dark=60, air=40, space=92, rv_decay=90, rv_mix=48, motion=90, sb_level=20, sb_drop=70)),
    ("Brass of Doom", dict(**A("Trombone", oct="-2", k1=10, k2=70, k3=60, level=85), **B("Horn", oct="-1", k1=10, k2=70, k3=50, level=60),
        attack=10, release=50, dark=55, air=30, space=80, rv_size=85, rv_decay=75, rv_mix=40,
        dr_mix=40, dr_amount=50, dr_tone=45, sb_level=50, sb_drop=30)),
    ("Stalker Pulse", dict(**A("Synth Brass", oct="-2", k1=15, k2=40, k3=30, level=85), **OFF,
        attack=0, release=20, dark=70, air=25, space=60, rv_mix=30, dl_mix=40, dl_time=55, dl_feedback=70,
        dr_mix=50, dr_amount=55, sb_level=50, sb_drop=60)),
    # --- 0.5.6: cold, sparse, ghost-vocal R&B ---
    ("Problem Child Vox", dict(**A("Vowels", oct="-1", k1=25, k2=20, k3=40, level=80), **B("Vowels", oct="+1", k1=60, k2=80, k3=60, level=20),
        release=60, dark=70, air=35, space=82, rv_size=85, rv_decay=80, rv_mix=44, dl_mix=35, dl_time=70, dl_feedback=55,
        motion=55, sb_level=40, sb_drop=40)),
    ("Cold Room Keys", dict(**A("Vibes", oct="-1", k1=50, k2=55, k3=20, level=85), **B("Wind", k1=30, k2=50, k3=70, level=15),
        release=55, dark=75, air=25, space=80, rv_decay=78, rv_mix=42, dl_mix=30, dl_time=72, dl_feedback=50,
        dr_mix=25, dr_amount=30, sb_level=40, sb_drop=35)),
    ("Lonely Vox Chop", dict(**A("Vowels", k1=50, k2=35, k3=0, level=80), **OFF,
        attack=0, release=20, dark=65, air=40, space=70, rv_mix=36, dl_mix=45, dl_time=60, dl_feedback=60,
        dr_mix=30, dr_amount=35, sb_level=35, sb_drop=30)),
    ("Grey Sky Pad", dict(**A("Synth Pad", oct="-1", k1=15, k2=30, k3=85, level=85), **B("Choir", oct="-1", k1=0, k2=40, k3=75, level=35),
        release=85, dark=80, air=20, space=88, rv_decay=85, rv_mix=46, motion=55, sb_level=45, sb_drop=40)),
    ("Atlanta Fog Flute", dict(**A("Flute", oct="-1", k1=35, k2=75, k3=25), **B("Texture", oct="-1", k1=55, k2=43, k3=80, level=25),
        release=60, dark=75, air=25, space=85, rv_decay=82, rv_mix=44, dl_mix=30, dl_time=74, dl_feedback=55,
        motion=50, sb_level=40, sb_drop=35)),
    ("Numb Bells", dict(**A("Glass", oct="-1", k1=40, k2=30, k3=30, level=85), **B("Synth Pad", oct="-2", k1=15, k2=30, k3=70, level=30),
        release=75, dark=75, air=25, space=88, rv_decay=85, rv_mix=46, dl_mix=25, dl_time=70, dl_feedback=50,
        motion=45, sb_level=40, sb_drop=40)),
    # --- UP FRONT (0.7.6): sounds that carry the track on their own: clear attack, less wash, room to play ---
    ("Golden Hour Lead", dict(**A("Synth Lead", k1=75, k2=15, k3=95, level=80), **B("Synth Brass", oct="+1", k1=60, k2=30, k3=90, level=35),
        attack=5, release=40, dark=25, air=60, motion=35, space=55, rv_mix=24, dl_mix=26, dl_feedback=40, dl_sync="1/8D",
        dr_mix=25, dr_amount=30, dr_tone=65)),
    ("Sunset Saw Lead", dict(**A("Synth Lead", k1=85, k2=10, k3=100, level=80), **B("Synth Lead", oct="+1", k1=70, k2=10, k3=70, level=30),
        attack=0, release=35, dark=20, air=65, motion=30, space=50, rv_mix=22, dl_mix=22, dl_feedback=35, dl_sync="1/4",
        dr_mix=30, dr_amount=35, dr_tone=70)),
    ("Velvet Poly", dict(**A("Synth Pad", k1=60, k2=40, k3=75, level=85), **OFF,
        attack=5, release=35, dark=35, air=50, motion=30, space=45, rv_mix=22, rv_decay=45)),
    ("Analog Brass Section", dict(**A("Synth Brass", k1=70, k2=55, k3=60, level=85), **OFF,
        attack=10, release=30, dark=25, air=55, motion=25, space=45, rv_mix=22, dr_mix=20, dr_amount=25, dr_tone=60)),
    ("Neon Stab", dict(**A("Synth Brass", k1=80, k2=20, k3=50, level=85), **B("Choir", k1=20, k2=40, k3=0, level=30),
        attack=0, release=12, dark=20, air=55, motion=10, space=40, rv_mix=22, rv_decay=35, dr_mix=40, dr_amount=45, dr_tone=65)),
    ("Bright Pluck", dict(**A("Synth Lead", k1=65, k2=0, k3=60, level=85), **OFF,
        attack=0, release=8, dark=25, air=60, motion=10, space=45, rv_mix=22, dl_mix=28, dl_feedback=40, dl_sync="1/16")),
    ("Hollow Square", dict(**A("Synth Lead", k1=45, k2=20, k3=30, level=85), **OFF,
        attack=0, release=25, dark=40, air=45, motion=25, space=40, rv_mix=20, dl_mix=18, dl_feedback=30, dl_sync="1/8")),
    ("Chord Keys", dict(**A("E-Piano", k1=80, k2=15, k3=65, level=80), **B("Synth Pad", k1=55, k2=30, k3=55, level=35),
        attack=0, release=30, dark=30, air=55, motion=20, space=45, rv_mix=22)),
    ("Glide Bass", dict(**A("Synth Lead", oct="-2", k1=40, k2=60, k3=20, level=85), **OFF,
        attack=0, release=15, dark=55, air=25, motion=10, space=15, rv_mix=6, dr_mix=30, dr_amount=40, dr_tone=40)),
    ("Round Bass", dict(**A("Synth Lead", oct="-2", k1=25, k2=10, k3=10, level=85), **OFF,
        attack=0, release=20, dark=70, air=15, motion=5, space=10, rv_mix=4)),
    ("Wide Chord Pad", dict(**A("Synth Pad", k1=50, k2=55, k3=95, level=80), **B("Strings", k1=60, k2=40, k3=50, level=35),
        attack=20, release=55, dark=35, air=55, motion=55, mo_sync="1 Bar", space=65, rv_mix=30)),
    ("Pulse Swell", dict(**A("Synth Pad", k1=45, k2=70, k3=70, level=85), **OFF,
        attack=10, release=45, dark=60, air=40, motion=85, mo_sync="1/4", space=55, rv_mix=26)),
    ("String Machine", dict(**A("Strings", k1=85, k2=30, k3=60, level=70), **B("Synth Pad", k1=55, k2=50, k3=90, level=50),
        attack=15, release=45, dark=30, air=55, motion=40, space=55, rv_mix=26)),
    ("Dream Brass", dict(**A("Horn", k1=35, k2=50, k3=60, level=70), **B("Synth Brass", k1=55, k2=60, k3=70, level=55),
        attack=15, release=45, dark=35, air=50, motion=30, space=55, rv_mix=26)),
    ("Digital Bell Keys", dict(**A("E-Piano", k1=75, k2=25, k3=85, level=75), **B("Glockenspiel", k1=40, k2=30, k3=70, level=35),
        attack=0, release=35, dark=15, air=65, motion=20, space=50, rv_mix=24)),
    ("Glass Piano", dict(**A("Piano", k1=100, k2=0, k3=80, level=80), **B("Glass", k1=5, k2=35, k3=55, level=40), attack=0, release=35, dark=25, air=55, motion=10, space=45, rv_mix=22)),
    ("Celesta Lead", dict(**A("Glockenspiel", oct="-1", k1=60, k2=15, k3=60, level=85), **OFF,
        attack=0, release=25, dark=25, air=60, motion=15, space=45, rv_mix=22, dl_mix=20, dl_feedback=35, dl_sync="1/8D")),
    ("Midnight Marimba", dict(**A("Marimba", k1=80, k2=0, k3=50, level=85), **OFF,
        attack=0, release=20, dark=45, air=35, motion=5, space=35, rv_mix=18)),
    ("Front Row Strings", dict(**A("Strings", k1=75, k2=15, k3=65, level=85), **OFF,
        attack=10, release=35, dark=25, air=55, motion=25, space=45, rv_mix=22)),
    ("Short Strings", dict(**A("Strings", k1=60, k2=0, k3=60, level=85), **OFF,
        attack=0, release=8, dark=30, air=50, motion=10, space=40, rv_mix=20)),
    ("Octave String Lead", dict(**A("Strings", oct="+1", k1=40, k2=20, k3=70, level=80), **B("Strings", k1=40, k2=20, k3=50, level=40),
        attack=15, release=40, dark=25, air=55, motion=35, space=50, rv_mix=24)),
    ("Lead Vox Ahh", dict(**A("Vowels", k1=40, k2=60, k3=10, level=85), **OFF,
        attack=10, release=35, dark=25, air=60, motion=35, space=45, rv_mix=22, dl_mix=16, dl_feedback=30, dl_sync="1/4")),
    ("Choir Hit", dict(**A("Choir", k1=40, k2=50, k3=0, level=85), **B("Synth Brass", k1=60, k2=20, k3=40, level=30),
        attack=0, release=15, dark=25, air=55, motion=10, space=45, rv_mix=24, rv_decay=40, dr_mix=25, dr_amount=30)),
    ("Bright Vocal Pad", dict(**A("Choir", oct="+1", k1=70, k2=55, k3=40, level=80), **B("Synth Pad", k1=60, k2=50, k3=80, level=30),
        attack=20, release=50, dark=15, air=70, motion=40, mo_sync="2 Bars", space=60, rv_mix=28)),
    ("Solo Flute", dict(**A("Flute", k1=50, k2=45, k3=60, level=85), **OFF,
        attack=5, release=25, dark=20, air=60, motion=30, space=35, rv_mix=18)),
    ("Pan Lead", dict(**A("Ocarina", k1=55, k2=65, k3=55, level=75), **B("Flute", oct="+1", k1=30, k2=70, k3=50, level=30),
        attack=5, release=30, dark=25, air=60, motion=30, space=45, rv_mix=22, dl_mix=18, dl_feedback=30, dl_sync="1/8D")),
    ("Soprano Sax Lead", dict(**A("Sax", oct="+1", k1=55, k2=45, k3=60, level=85), **OFF,
        attack=5, release=30, dark=25, air=55, motion=35, space=40, rv_mix=20)),
    ("Clarinet Melody", dict(**A("Clarinet", k1=45, k2=40, k3=55, level=85), **OFF,
        attack=5, release=25, dark=30, air=50, motion=25, space=35, rv_mix=18)),
    ("Solo Trumpet", dict(**A("Mute Trumpet", k1=50, k2=40, k3=70, level=85), **OFF,
        attack=5, release=25, dark=20, air=55, motion=30, space=40, rv_mix=20)),
    ("Horn Section Stab", dict(**A("Horn", k1=30, k2=35, k3=70, level=75), **B("Trombone", k1=30, k2=35, k3=65, level=60),
        attack=0, release=12, dark=25, air=50, motion=10, space=40, rv_mix=22, dr_mix=25, dr_amount=30)),
    ("Big Brass Swell", dict(**A("Horn", k1=40, k2=60, k3=65, level=70), **B("Synth Brass", k1=50, k2=95, k3=70, level=55),
        attack=45, release=50, dark=30, air=50, motion=30, space=60, rv_mix=26)),
    ("Evolving Lead", dict(**A("Texture", k1=40, k2=43, k3=30, level=60), **B("Synth Lead", k1=55, k2=25, k3=80, level=65),
        attack=10, release=45, dark=35, air=55, motion=60, mo_sync="2 Bars", space=60, rv_mix=26, dl_mix=20, dl_feedback=40, dl_sync="1/4D")),
    ("Grain Keys", dict(**A("Texture", k1=20, k2=71, k3=20, level=70), **B("Vibes", k1=40, k2=50, k3=45, level=55),
        attack=0, release=30, dark=30, air=55, motion=30, space=50, rv_mix=24)),
    ("Shimmer Motion Bed", dict(**A("Wind", k1=40, k2=50, k3=85, level=55), **B("Synth Pad", k1=50, k2=60, k3=90, level=70),
        attack=30, release=65, dark=35, air=65, motion=75, mo_sync="2 Bars", space=75, rv_mix=34)),
    ("Sync Echo Keys", dict(**A("Vibes", k1=45, k2=50, k3=55, level=85), **OFF,
        attack=0, release=25, dark=35, air=50, motion=15, space=45, rv_mix=20, dl_mix=38, dl_feedback=50, dl_sync="1/8D")),
    ("Bar Sweep Pad", dict(**A("Synth Pad", k1=40, k2=50, k3=85, level=80), **B("Choir", k1=40, k2=50, k3=70, level=30),
        attack=25, release=55, dark=70, air=40, motion=95, mo_sync="1 Bar", space=60, rv_mix=28)),
    # --- NOIR (0.7.6): sad, somber, close. Keys from the bells, leads that cry, pads behind a wall ---
    ("Tired Rhodes", dict(**A("E-Piano", k1=65, k2=30, k3=35, level=85), **OFF, _cat="NOIR", 
        attack=0, release=40, dark=60, air=25, lofi=45, motion=55, space=55, rv_mix=26, dl_mix=14, dl_time=62, dl_feedback=30)),
    ("3AM Text", dict(**A("Kalimba", k1=45, k2=10, k3=50, level=85), **B("Glass", k1=10, k2=30, k3=35, level=35), _cat="NOIR", 
        attack=0, release=30, dark=50, air=35, lofi=20, motion=25, space=55, rv_mix=26, dl_mix=34, dl_time=60, dl_feedback=45)),
    ("Felt Room", dict(**A("Piano", k1=55, k2=0, k3=22, level=85), **B("Bowed Vibes", k1=30, k2=20, k3=20, level=18), _cat="NOIR", 
        attack=0, release=40, dark=70, air=20, lofi=25, motion=20, space=35, rv_size=35, rv_decay=35, rv_mix=22)),
    ("Pillow Talk Keys", dict(**A("E-Piano", k1=70, k2=20, k3=45, level=85), **B("Choir", k1=40, k2=40, k3=70, level=25), _cat="NOIR", 
        attack=0, release=45, dark=50, air=35, lofi=30, motion=45, space=60, rv_mix=30, dl_mix=18, dl_time=64, dl_feedback=35)),
    ("Unread", dict(**A("Vibes", oct="+1", k1=20, k2=40, k3=40, level=80), **B("Glass", oct="+1", k1=5, k2=40, k3=30, level=45), _cat="NOIR",
        attack=0, release=35, dark=60, air=40, motion=20, space=65, rv_mix=30, dl_mix=40, dl_time=55, dl_feedback=55)),
    ("Cried Out Lead", dict(**A("Synth Lead", k1=40, k2=75, k3=45, level=85), **OFF, _cat="NOIR",
        attack=25, release=55, dark=55, air=35, motion=65, space=75, rv_size=75, rv_decay=80, rv_mix=36, dl_mix=22, dl_time=66, dl_feedback=40)),
    ("Cold Shoulder Lead", dict(**A("Synth Lead", oct="+1", k1=45, k2=20, k3=85, level=80), **OFF, _cat="NOIR",
        attack=5, release=35, dark=45, air=40, motion=40, space=60, rv_mix=30, dl_mix=30, dl_time=58, dl_feedback=40,
        dr_mix=20, dr_amount=30)),
    ("Wilted Lead", dict(**A("Synth Lead", k1=55, k2=35, k3=100, level=80), **OFF, _cat="NOIR",
        attack=10, release=40, dark=40, air=45, lofi=35, motion=70, space=65, rv_mix=32, dl_mix=20, dl_time=62)),
    ("Drowned Lead", dict(**A("Synth Lead", k1=35, k2=55, k3=60, level=80), **B("Vowels", k1=40, k2=45, k3=40, level=35), _cat="NOIR",
        attack=20, release=65, dark=60, air=40, motion=55, space=90, rv_size=90, rv_decay=88, rv_mix=48, dl_mix=28, dl_time=70, dl_feedback=50)),
    ("Smoke Ring Sax", dict(**A("Sax", oct="-1", k1=35, k2=65, k3=30, level=85), **OFF, _cat="NOIR",
        attack=30, release=55, dark=70, air=35, motion=35, space=65, rv_mix=32, dl_mix=18, dl_time=68, dl_feedback=35)),
    ("Behind The Wall", dict(**A("Synth Pad", k1=10, k2=50, k3=70, level=85), **B("Choir", k1=30, k2=50, k3=70, level=25), _cat="NOIR",
        attack=45, release=70, dark=90, air=20, motion=80, space=80, rv_decay=75, rv_mix=40)),
    ("Overcast Pad", dict(**A("Synth Pad", k1=30, k2=45, k3=80, level=75), **B("Tremolo", k1=50, k2=60, k3=40, level=40), _cat="NOIR",
        attack=55, release=75, dark=65, air=35, motion=70, space=80, rv_decay=78, rv_mix=40)),
    ("Aching Pad", dict(**A("Choir", k1=40, k2=80, k3=75, level=70), **B("Synth Pad", k1=35, k2=55, k3=85, level=55), _cat="NOIR",
        attack=50, release=80, dark=55, air=45, motion=60, space=88, rv_size=85, rv_decay=85, rv_mix=44)),
    ("Cold Bloom", dict(**A("Synth Brass", k1=30, k2=95, k3=70, level=80), **OFF, _cat="NOIR",
        attack=70, release=75, dark=60, air=35, motion=55, space=82, rv_decay=80, rv_mix=40)),
    ("Sinking", dict(**A("Strings", oct="-1", k1=60, k2=70, k3=25, level=80), **B("Synth Pad", oct="-1", k1=15, k2=50, k3=60, level=30), _cat="NOIR",
        attack=55, release=75, dark=80, air=20, motion=45, space=78, rv_decay=75, rv_mix=38)),
    ("Gone By Morning", dict(**A("Vowels", oct="+1", k1=60, k2=65, k3=20, level=80), **OFF, _cat="NOIR",
        attack=15, release=55, dark=40, air=55, motion=50, space=80, rv_size=80, rv_decay=80, rv_mix=40, dl_mix=25, dl_time=64, dl_feedback=45)),
    ("Echoes Of You", dict(**A("Vowels", k1=45, k2=50, k3=10, level=80), **OFF, _cat="NOIR",
        attack=5, release=40, dark=55, air=45, motion=40, space=70, rv_mix=34, dl_mix=45, dl_time=70, dl_feedback=70)),
    ("Warm Halo", dict(**A("Choir", k1=55, k2=45, k3=60, level=80), **B("Vibes", k1=60, k2=50, k3=20, level=20), _cat="NOIR",
        attack=35, release=60, dark=50, air=40, motion=40, space=60, rv_size=50, rv_decay=55, rv_mix=30)),
    ("Static Pulse", dict(**A("Synth Lead", k1=50, k2=0, k3=40, level=80), **OFF, _cat="NOIR",
        attack=0, release=10, dark=40, air=40, motion=30, space=40, rv_size=45, rv_decay=25, rv_mix=26, dl_mix=25, dl_time=50, dl_feedback=40,
        dr_mix=45, dr_amount=50, dr_tone=55)),
    ("Velvet Funeral", dict(**A("Tubular", oct="-1", k1=70, k2=40, k3=30, level=70), **B("Trombone", oct="-1", k1=25, k2=45, k3=35, level=55), _cat="NOIR",
        attack=30, release=75, dark=70, air=25, motion=30, space=85, rv_size=85, rv_decay=85, rv_mix=42)),
    # --- ASTRO (0.7.6): spacey and dark. Flutes in the fog, bells far off, leads that whine ---
    ("Night Flute", dict(**A("Flute", k1=40, k2=70, k3=35, level=85), **OFF, _cat="ASTRO",
        attack=15, release=45, dark=60, air=50, motion=40, space=70, rv_mix=32, dl_mix=30, dl_time=62, dl_feedback=45)),
    ("Syrup Flute", dict(**A("Flute", oct="-1", k1=30, k2=60, k3=30, level=85), **OFF, _cat="ASTRO",
        attack=25, release=55, dark=65, air=40, lofi=40, motion=55, space=70, rv_mix=32, dl_mix=22, dl_time=68, dl_feedback=40)),
    ("Far Planet Pipe", dict(**A("Ocarina", oct="+1", k1=50, k2=45, k3=40, level=80), **OFF, _cat="ASTRO",
        attack=10, release=50, dark=45, air=55, motion=45, space=80, rv_size=80, rv_decay=78, rv_mix=38, dl_mix=38, dl_time=56, dl_feedback=55)),
    ("Haze Flute", dict(**A("Flute", k1=35, k2=80, k3=40, level=75), **B("Texture", k1=60, k2=43, k3=80, level=35), _cat="ASTRO",
        attack=30, release=65, dark=55, air=60, motion=60, space=82, rv_decay=80, rv_mix=40, dl_mix=20, dl_time=66)),
    ("Starlight Mallets", dict(**A("Glockenspiel", k1=50, k2=50, k3=70, level=80), **B("Glass", k1=5, k2=70, k3=55, level=40), _cat="ASTRO",
        attack=0, release=40, dark=35, air=55, motion=30, space=75, rv_mix=34, dl_mix=45, dl_time=52, dl_feedback=60)),
    ("Orbit Bells", dict(**A("Tubular", k1=75, k2=65, k3=35, level=75), **OFF, _cat="ASTRO",
        attack=0, release=80, dark=60, air=40, motion=35, space=95, rv_size=95, rv_decay=92, rv_mix=48)),
    ("Comet Keys", dict(**A("Vibes", oct="+1", k1=40, k2=80, k3=45, level=80), **OFF, _cat="ASTRO",
        attack=0, release=40, dark=40, air=55, motion=65, space=70, rv_mix=32, dl_mix=35, dl_time=50, dl_feedback=50)),
    ("Zero Gravity", dict(**A("Bowed Vibes", k1=85, k2=75, k3=40, level=80), **B("Wind", k1=30, k2=60, k3=80, level=20), _cat="ASTRO",
        attack=70, release=85, dark=45, air=60, motion=55, space=92, rv_size=90, rv_decay=90, rv_mix=46)),
    ("Signal Lead", dict(**A("Synth Lead", oct="+1", k1=60, k2=60, k3=70, level=75), **OFF, _cat="ASTRO",
        attack=10, release=45, dark=40, air=45, motion=75, space=70, rv_mix=32, dl_mix=35, dl_time=60, dl_feedback=55)),
    ("Siren Rise", dict(**A("Synth Lead", k1=45, k2=100, k3=55, level=80), **OFF, _cat="ASTRO",
        attack=40, release=60, dark=50, air=40, motion=85, space=80, rv_decay=78, rv_mix=40, dl_mix=30, dl_time=66, dl_feedback=60)),
    ("Abduction", dict(**A("Synth Brass", k1=35, k2=70, k3=80, level=70), **B("Vowels", oct="+1", k1=50, k2=30, k3=50, level=40), _cat="ASTRO",
        attack=45, release=70, dark=60, air=40, motion=70, space=85, rv_decay=82, rv_mix=42, dl_mix=20, dl_time=70, dl_feedback=45)),
    ("Far Horn Signal", dict(**A("Mute Trumpet", oct="-1", k1=40, k2=55, k3=30, level=80), **OFF, _cat="ASTRO",
        attack=25, release=60, dark=70, air=35, motion=35, space=85, rv_size=85, rv_decay=80, rv_mix=40, dl_mix=40, dl_time=72, dl_feedback=65)),
    ("Violet Planet", dict(**A("Synth Pad", k1=30, k2=60, k3=85, level=70), **B("Choir", oct="-1", k1=35, k2=60, k3=70, level=45), _cat="ASTRO",
        attack=50, release=80, dark=65, air=40, motion=65, space=88, rv_size=85, rv_decay=85, rv_mix=44)),
    ("Moon Choir", dict(**A("Vowels", oct="-1", k1=30, k2=40, k3=60, level=80), **B("Choir", k1=40, k2=60, k3=70, level=30), _cat="ASTRO",
        attack=45, release=75, dark=60, air=40, motion=50, space=88, rv_size=88, rv_decay=85, rv_mix=44)),
    ("Astronaut Fog", dict(**A("Wind", k1=45, k2=70, k3=85, level=75), **B("Synth Pad", oct="-1", k1=25, k2=50, k3=75, level=50), _cat="ASTRO",
        attack=60, release=85, dark=55, air=65, motion=70, space=92, rv_decay=88, rv_mix=46)),
    ("Low Orbit", dict(**A("Strings", oct="-2", k1=55, k2=75, k3=20, level=80), **B("Synth Pad", oct="-1", k1=15, k2=45, k3=70, level=30), _cat="ASTRO",
        attack=60, release=80, dark=80, air=25, motion=40, space=82, rv_decay=80, rv_mix=40)),
    # --- GEMS (0.7.6): beautiful, sparkling. Warm jewels: a soft, short, rounded bell over a low bed with a slow swirl;
    # then the bright ones ---
    ("Soft Diamond", dict(**A("Hand Chimes", k1=45, k2=15, k3=45, level=85), **B("Synth Pad", oct="-1", k1=20, k2=50, k3=80, level=28), _cat="GEMS", 
        attack=0, release=30, dark=45, air=40, motion=45, mo_sync="2 Bars", space=50, rv_mix=26)),
    ("Velvet Bells", dict(**A("Vibes", k1=40, k2=20, k3=25, level=80), **B("Bowed Vibes", k1=40, k2=30, k3=30, level=35), _cat="GEMS",
        attack=0, release=35, dark=48, air=30, motion=35, space=50, rv_mix=26)),
    ("Music Box Glow", dict(**A("Glockenspiel", oct="-1", k1=45, k2=10, k3=40, level=80), **B("Synth Pad", oct="-1", k1=20, k2=45, k3=75, level=30), _cat="GEMS", 
        attack=0, release=30, dark=45, air=40, motion=40, mo_sync="2 Bars", space=55, rv_mix=28)),
    ("Pearl Keys", dict(**A("E-Piano", k1=70, k2=20, k3=55, level=80), **B("Choir", oct="-1", k1=30, k2=55, k3=75, level=30), _cat="GEMS", 
        attack=0, release=35, dark=40, air=40, motion=55, mo_sync="2 Bars", space=58, rv_mix=28)),
    ("Moonstone", dict(**A("Tubular", k1=30, k2=30, k3=25, level=75), **B("Synth Pad", oct="-1", k1=22, k2=50, k3=85, level=32), _cat="GEMS",
        attack=0, release=40, dark=60, air=35, motion=45, mo_sync="2 Bars", space=60, rv_mix=30)),
    ("Opal Pluck", dict(**A("Kalimba", k1=60, k2=10, k3=60, level=85), **B("Glass", k1=5, k2=30, k3=25, level=40), _cat="GEMS", 
        attack=0, release=28, dark=35, air=45, motion=40, space=50, rv_mix=26)),
    ("Lullaby Bells", dict(**A("Glockenspiel", oct="-2", k1=55, k2=20, k3=35, level=85), **B("Bowed Vibes", k1=50, k2=40, k3=30, level=22), _cat="GEMS", 
        attack=0, release=40, dark=50, air=35, motion=60, mo_sync="4 Bars", space=60, rv_mix=30)),
    ("Amber Chime", dict(**A("Marimba", k1=70, k2=10, k3=55, level=80), **B("Horn", oct="-1", k1=15, k2=40, k3=30, level=30), _cat="GEMS", 
        attack=0, release=35, dark=45, air=35, motion=35, space=55, rv_mix=28)),
    ("Diamond Dust", dict(**A("Glockenspiel", k1=60, k2=45, k3=85, level=80), **B("Glass", oct="+1", k1=5, k2=75, k3=65, level=40), _cat="GEMS", 
        attack=0, release=30, dark=15, air=70, motion=25, space=60, rv_mix=28, dl_mix=32, dl_feedback=45, dl_sync="1/8D")),
    ("Cut Glass", dict(**A("Harp", oct="+1", k1=70, k2=10, k3=85, level=80), **B("Glass", k1=5, k2=60, k3=70, level=40), _cat="GEMS", 
        attack=0, release=28, dark=15, air=65, motion=20, space=50, rv_mix=24, dl_mix=26, dl_feedback=40, dl_sync="1/8")),
    ("Chandelier", dict(**A("Hand Chimes", oct="+1", k1=70, k2=55, k3=80, level=75), **B("Glockenspiel", oct="+1", k1=40, k2=40, k3=70, level=30), _cat="GEMS", 
        attack=0, release=35, dark=15, air=70, motion=30, space=60, rv_mix=28, dl_mix=28, dl_feedback=45, dl_sync="1/16")),
    ("Halo Lead", dict(**A("Vowels", oct="+1", k1=60, k2=70, k3=10, level=75), **B("Glass", oct="+1", k1=5, k2=70, k3=60, level=35), _cat="GEMS",
        attack=5, release=40, dark=20, air=70, motion=35, space=60, rv_mix=28, dl_mix=22, dl_feedback=40, dl_sync="1/4")),
    ("Crystal Voice", dict(**A("Choir", oct="+1", k1=85, k2=60, k3=35, level=80), **B("Bowed Vibes", oct="+1", k1=60, k2=70, k3=50, level=30), _cat="GEMS",
        attack=15, release=50, dark=15, air=75, motion=35, space=65, rv_mix=30)),
    ("Aurora", dict(**A("Bowed Vibes", k1=80, k2=70, k3=50, level=75), **B("Choir", k1=70, k2=65, k3=70, level=45), _cat="GEMS",
        attack=55, release=75, dark=25, air=65, motion=65, mo_sync="2 Bars", space=80, rv_size=80, rv_decay=80, rv_mix=40)),
    ("Snow Globe", dict(**A("Texture", k1=25, k2=86, k3=40, level=55), **B("Synth Pad", k1=55, k2=55, k3=90, level=65), _cat="GEMS",
        attack=30, release=65, dark=25, air=65, motion=60, mo_sync="1 Bar", space=75, rv_mix=34)),
    ("Diamond Rain", dict(**A("Texture", k1=15, k2=100, k3=25, level=70), **B("Glockenspiel", k1=50, k2=60, k3=75, level=35), _cat="GEMS", 
        attack=10, release=60, dark=15, air=75, motion=50, space=80, rv_decay=80, rv_mix=38, dl_mix=25, dl_feedback=50, dl_sync="1/8T")),
    # reed and synth stacks, voiced to be played high as the main melody
    ("High Reed Stack", dict(**A("Sax", oct="+1", k1=45, k2=45, k3=60, level=75), **B("Synth Lead", oct="+1", k1=55, k2=30, k3=90, level=50), _cat="GEMS",
        attack=5, release=40, dark=25, air=60, motion=40, space=60, rv_mix=28, dl_mix=20, dl_feedback=35, dl_sync="1/4")),
    ("Silk Reed Lead", dict(**A("Sax", oct="+1", k1=40, k2=55, k3=50, level=75), **B("Synth Pad", oct="+1", k1=55, k2=45, k3=90, level=50), _cat="GEMS",
        attack=10, release=45, dark=30, air=60, motion=40, space=65, rv_mix=30)),
    ("Reed Halo Lead", dict(**A("Sax", oct="+1", k1=45, k2=50, k3=55, level=75), **B("Choir", oct="+1", k1=80, k2=60, k3=40, level=45), _cat="GEMS",
        attack=8, release=45, dark=25, air=65, motion=40, space=65, rv_mix=30, dl_mix=16, dl_feedback=30, dl_sync="1/4")),
    ("Glass Reed Lead", dict(**A("Sax", oct="+1", k1=40, k2=40, k3=65, level=75), **B("Glass", oct="+1", k1=5, k2=60, k3=55, level=40), _cat="GEMS",
        attack=5, release=40, dark=22, air=65, motion=35, space=60, rv_mix=28, dl_mix=22, dl_feedback=40, dl_sync="1/8D")),
    # --- keys and mallets (0.7.6): the new recorded instruments on their own, then paired ---
    ("Grand Piano", dict(**A("Piano", k1=100, k2=0, k3=90, level=85), **OFF,
        attack=0, release=35, dark=15, air=50, motion=0, space=35, rv_mix=16)),
    ("Soft Piano", dict(**A("Piano", k1=100, k2=0, k3=35, level=85), **OFF,
        attack=0, release=40, dark=50, air=30, motion=0, space=40, rv_mix=20)),
    ("Ballad Piano", dict(**A("Piano", k1=100, k2=0, k3=75, level=80), **B("Strings", k1=60, k2=45, k3=45, level=35),
        attack=0, release=45, dark=25, air=50, motion=25, space=50, rv_mix=24)),
    ("Piano and Pad", dict(**A("Piano", k1=100, k2=0, k3=70, level=80), **B("Synth Pad", k1=35, k2=50, k3=85, level=35),
        attack=0, release=45, dark=30, air=45, motion=40, mo_sync="2 Bars", space=50, rv_mix=24)),
    ("Electric Piano", dict(**A("E-Piano", k1=100, k2=20, k3=75, level=85), **OFF,
        attack=0, release=30, dark=20, air=45, motion=10, space=35, rv_mix=16)),
    ("Dream E-Piano", dict(**A("E-Piano", k1=90, k2=45, k3=60, level=80), **B("Synth Pad", oct="+1", k1=45, k2=40, k3=95, level=25),
        attack=0, release=45, dark=30, air=55, motion=50, space=60, rv_mix=28, dl_mix=18, dl_feedback=35, dl_sync="1/4")),
    ("Concert Harp", dict(**A("Harp", k1=100, k2=0, k3=90, level=85), **OFF,
        attack=0, release=45, dark=15, air=55, motion=0, space=45, rv_mix=22)),
    ("Harp Garden", dict(**A("Harp", k1=100, k2=0, k3=80, level=80), **B("Flute", k1=30, k2=60, k3=50, level=25),
        attack=0, release=50, dark=20, air=60, motion=30, space=60, rv_mix=28)),
    ("Kalimba", dict(**A("Kalimba", k1=100, k2=0, k3=85, level=85), **OFF,
        attack=0, release=30, dark=20, air=50, motion=0, space=35, rv_mix=18)),
    ("Marimba", dict(**A("Marimba", k1=100, k2=0, k3=85, level=85), **OFF,
        attack=0, release=25, dark=20, air=45, motion=0, space=35, rv_mix=18)),
    ("Glockenspiel", dict(**A("Glockenspiel", k1=100, k2=0, k3=90, level=85), **OFF,
        attack=0, release=35, dark=15, air=60, motion=0, space=45, rv_mix=22)),
    ("Hand Chimes", dict(**A("Hand Chimes", k1=100, k2=0, k3=85, level=85), **OFF,
        attack=0, release=40, dark=20, air=55, motion=0, space=50, rv_mix=24)),
]

LEVEL = {'Init': 91, 'Lone Flute': 100, 'Midnight Sax': 100, 'Clay Ocarina': 100, 'Angel Lead': 94, 'Torch Song': 94, 'Saint Air': 74, 'Choir Drift': 83, 'High Heavens': 92, 'Monastery': 63, 'Doo Choir': 96, 'Glass Cathedral': 100, 'Music Box Ghost': 100, 'Wind Over Water': 100, 'Frozen Breath': 93, 'Astro Haze': 100, 'After Hours Fog': 76, 'Black Choir Stabs': 100, 'Dark Vowel Bed': 74, 'Distant Horn': 80, 'Smoke Trumpet': 90, 'Low Brass Hymn': 84, 'Reed Lament': 100, 'Celtic Oboe': 87, 'Frost Strings': 77, 'Shiver': 73, 'Bell Tower': 76, 'Midnight Vibes': 93, 'Bowed Halo': 74, 'Glass Prayer': 73, 'Juno Dawn': 87, 'Neon Lead': 100, 'Night Drive Brass': 92, 'Ghost Synth Choir': 73, 'Scat Doos': 73, 'Vesper Choir': 69, 'Ooh Pad': 63, 'Dah Section': 89, 'Bah Brass Doos': 80, 'Cloister': 66, 'Soprano Light': 75, 'Highland Flute': 79, 'Hollow Ocarina': 88, 'Lowlight Clarinet': 100, 'Reed Choir': 95, 'Sax and Smoke': 90, 'Funeral Horns': 76, 'Harmon Night': 100, 'Bone Choir': 74, 'Sorrow Cellos': 71, 'Shimmer Tremolo': 69, 'Storm Strings': 71, 'Snowfall Vibes': 72, 'Grave Bells': 80, 'Crystal Rain': 79, 'Bowed Choir': 83, 'Ninety Pad': 97, 'Velvet Pad': 85, 'Square Lead': 100, 'Slide Lead': 100, 'Bloom Brass': 100, 'Dark Synth Stabs': 100, 'Ghost Wind': 80, 'Ember Field': 74, 'Octave Dust': 70, 'Underwater Vox': 65, 'Codeine Choir': 70, '4AM Hook Vox': 78, 'Haunted Ad Libs': 56, 'Purple Sax': 93, 'Lean Flute': 100, 'Desert Horn': 74, 'Velvet Room Strings': 67, 'Late Night Keys': 100, 'Faded Bells': 72, 'Codeine Pad': 76, 'Night Ride Lead': 100, 'Ghost Synth Brass': 72, 'Siren Glide': 71, 'Smoke Room': 63, 'Heartbreak Haze': 65, 'Possessed Choir': 75, 'Cluster Strings': 73, 'Dread Drone': 62, 'Nursery Ghost': 81, 'Funeral Toll': 63, 'Whisper Swarm': 57, 'Attic Wind': 64, 'Brass of Doom': 81, 'Stalker Pulse': 94, 'Problem Child Vox': 64, 'Cold Room Keys': 100, 'Lonely Vox Chop': 71, 'Grey Sky Pad': 85, 'Atlanta Fog Flute': 100, 'Numb Bells': 85, 'Golden Hour Lead': 92, 'Sunset Saw Lead': 92, 'Velvet Poly': 92, 'Analog Brass Section': 92, 'Neon Stab': 92, 'Bright Pluck': 92, 'Hollow Square': 92, 'Chord Keys': 92, 'Glide Bass': 92, 'Round Bass': 92, 'Wide Chord Pad': 92, 'Pulse Swell': 92, 'String Machine': 92, 'Dream Brass': 92, 'Digital Bell Keys': 92, 'Glass Piano': 92, 'Celesta Lead': 92, 'Midnight Marimba': 92, 'Front Row Strings': 92, 'Short Strings': 92, 'Octave String Lead': 92, 'Lead Vox Ahh': 92, 'Choir Hit': 92, 'Bright Vocal Pad': 92, 'Solo Flute': 92, 'Pan Lead': 92, 'Soprano Sax Lead': 92, 'Clarinet Melody': 92, 'Solo Trumpet': 92, 'Horn Section Stab': 92, 'Big Brass Swell': 92, 'Evolving Lead': 92, 'Grain Keys': 92, 'Shimmer Motion Bed': 92, 'Sync Echo Keys': 92, 'Bar Sweep Pad': 92, 'Soft Diamond': 92, 'Velvet Bells': 92, 'Music Box Glow': 88, 'Pearl Keys': 92, 'Moonstone': 92, 'Opal Pluck': 92, 'Lullaby Bells': 92, 'Amber Chime': 92, 'Diamond Dust': 92, 'Cut Glass': 92, 'Chandelier': 92, 'Halo Lead': 88, 'Crystal Voice': 88, 'Aurora': 92, 'Snow Globe': 88, 'Diamond Rain': 78, 'High Reed Stack': 100, 'Silk Reed Lead': 100, 'Reed Halo Lead': 100, 'Glass Reed Lead': 100}   # output level per preset, filled from measured loudness so the set plays back evenly


# output levels of the presets added in 0.7.6, set by measurement (tools: a held 4-note chord, as for LEVEL)
# LEVEL_076_BEGIN
LEVEL_076 = {"Lead Vox Ahh": 81, "Choir Hit": 78, "Bright Vocal Pad": 79, "Solo Flute": 100, "Pan Lead": 93, "Soprano Sax Lead": 90, "Clarinet Melody": 100, "Dream Brass": 84, "Solo Trumpet": 99, "Horn Section Stab": 75, "Big Brass Swell": 83, "String Machine": 83, "Front Row Strings": 82, "Short Strings": 78, "Octave String Lead": 87, "Sync Echo Keys": 100, "Golden Hour Lead": 100, "Sunset Saw Lead": 97, "Velvet Poly": 85, "Analog Brass Section": 91, "Neon Stab": 79, "Bright Pluck": 100, "Hollow Square": 100, "Glide Bass": 100, "Round Bass": 94, "Wide Chord Pad": 76, "Pulse Swell": 89, "Bar Sweep Pad": 89, "Evolving Lead": 81, "Grain Keys": 92, "Shimmer Motion Bed": 76, "Tired Rhodes": 100, "3AM Text": 100, "Felt Room": 100, "Pillow Talk Keys": 90, "Unread": 84, "Cried Out Lead": 91, "Cold Shoulder Lead": 71, "Wilted Lead": 99, "Drowned Lead": 63, "Smoke Ring Sax": 93, "Behind The Wall": 100, "Overcast Pad": 87, "Aching Pad": 73, "Cold Bloom": 69, "Sinking": 60, "Gone By Morning": 64, "Echoes Of You": 86, "Warm Halo": 81, "Static Pulse": 100, "Velvet Funeral": 82, "Night Flute": 100, "Syrup Flute": 100, "Far Planet Pipe": 73, "Haze Flute": 89, "Starlight Mallets": 99, "Orbit Bells": 94, "Comet Keys": 93, "Zero Gravity": 100, "Signal Lead": 99, "Siren Rise": 75, "Abduction": 57, "Far Horn Signal": 73, "Violet Planet": 86, "Moon Choir": 66, "Astronaut Fog": 70, "Low Orbit": 82, "Soft Diamond": 97, "Velvet Bells": 100, "Music Box Glow": 94, "Pearl Keys": 94, "Moonstone": 100, "Opal Pluck": 100, "Lullaby Bells": 72, "Amber Chime": 100, "Diamond Dust": 100, "Cut Glass": 100, "Chandelier": 100, "Halo Lead": 79, "Crystal Voice": 83, "Aurora": 94, "Snow Globe": 77, "Diamond Rain": 56, "High Reed Stack": 93, "Silk Reed Lead": 85, "Reed Halo Lead": 85, "Glass Reed Lead": 92, "Chord Keys": 100, "Digital Bell Keys": 100, "Glass Piano": 100, "Grand Piano": 100, "Soft Piano": 100, "Ballad Piano": 92, "Piano and Pad": 99, "Electric Piano": 100, "Dream E-Piano": 94, "Concert Harp": 100, "Harp Garden": 91, "Celesta Lead": 89, "Midnight Marimba": 100, "Kalimba": 100, "Marimba": 100, "Glockenspiel": 100, "Hand Chimes": 97}
# LEVEL_076_END
LEVEL.update(LEVEL_076)
# the kalimba is all strike: levelled on a held chord it comes out about 5 dB hot when played, so these sit lower
for _n in ("Opal Pluck", "Kalimba", "3AM Text"):
    LEVEL[_n] = max(40, LEVEL.get(_n, 80) - 32)

FIRST_076 = "Golden Hour Lead"   # the first design added in 0.7.6
TAG = {"Voices": "VOX", "Winds": "WND", "Brass": "BRS", "Strings": "STR", "Bells": "BEL", "Synth": "SYN", "Air": "AIR",
       "NOIR": "NOIR", "ASTRO": "ASTRO", "GEMS": "GEMS", "Keys": "KEY", "Mallets": "KEY"}   # NOIR and ASTRO: picked by a design's _cat, not its slot A
ORDER = list(TAG)


def tagged():
    """Init first, then every preset grouped by slot A's category, its name tagged (VOX, WND...) for the MPC list."""
    out = [d for d in DESIGNS if d[0] == "Init"]
    designs = [(n, synced(v)) for n, v in DESIGNS]
    rest = [d for d in designs if d[0] != "Init"]
    # the 96 presets up to 0.7.5 keep their places in the list (a saved project's preset number still names the same
    # preset); everything newer follows, grouped the same way
    cut = [n for n, _ in rest].index(FIRST_076)
    key = lambda d: ORDER.index(d[1].get("_cat", d[1]["a_cat"]))   # stable: keeps each group's own order
    rest = sorted(rest[:cut], key=key) + sorted(rest[cut:], key=key)
    for name, vals in rest:
        out.append(("%s %s" % (TAG[vals.get("_cat", vals["a_cat"])], name), {k: v for k, v in vals.items() if k != "_cat"}, name))
    return [(d[0], d[1], d[0]) if len(d) == 2 else d for d in out]


# The sub follows the lowest held note, so it only belongs where a bass line is the point: stabs, pulses, doom
# brass, the drone, two dark pads. Everywhere else it is off (it would put a bass under every flute or bell melody),
# and where it stays it sits under the sound, not on top of it. Players still have it on the FX page.
SUB_KEEP = {"Dark Synth Stabs": 25, "Stalker Pulse": 25, "Black Choir Stabs": 20, "Brass of Doom": 25,
            "Dread Drone": 22, "Codeine Pad": 18, "Grey Sky Pad": 18, "Sinking": 20, "Low Orbit": 22, "Glide Bass": 30, "Round Bass": 35}


# NOIR and ASTRO (new in 0.7.6) with a clear echo lock it to the tempo: the note value nearest their free time at 90 BPM.
# The earlier presets keep the free Time knob, so they sound as they always did.
NOTE_BEATS = [("1/16", 0.25), ("1/8T", 1 / 3), ("1/8", 0.5), ("1/8D", 0.75), ("1/4T", 2 / 3), ("1/4", 1), ("1/4D", 1.5), ("1/2", 2)]


def synced(vals):
    if vals.get("_cat") not in ("NOIR", "ASTRO", "GEMS") or vals.get("dl_mix", 0) < 25 or "dl_sync" in vals:
        return vals
    secs = 0.06 * 25 ** (vals.get("dl_time", 50) / 100.0)
    beats = secs * 90 / 60.0
    return dict(vals, dl_sync=min(NOTE_BEATS, key=lambda nb: abs(nb[1] - beats))[0])


def main():
    by_key = {p["key"]: p for p in PARAMS}
    out = []
    for name, vals, base in tagged():
        assert len(name) <= 24, name
        values = {}
        for p in PARAMS:
            if p["key"] not in SKIP and not UI.match(p["key"]) and "default" in p:   # momentary buttons have none and never go in a preset
                values[p["key"]] = p["default"]
        values["master"] = LEVEL.get(base, values["master"])
        vals = dict(vals, sb_level=SUB_KEEP.get(base, 0))
        for k, v in convert(vals).items():
            if k not in by_key:
                raise SystemExit("%s: unknown parameter %s" % (name, k))
            values[k] = v
        out.append({"name": name, "values": values})
    json.dump({"presets": out}, open(os.path.join(HERE, "presets.json"), "w"), indent=1)
    print("%d presets written" % len(out))


if __name__ == "__main__":
    main()
