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


# sound name -> (category, that category's option)
SOUND = {"Choir": ("Voices", "Choir"), "Vowels": ("Voices", "Vowels"),
         "Flute": ("Winds", "Flute"), "Ocarina": ("Winds", "Ocarina"), "Sax": ("Winds", "Sax"),
         "Clarinet": ("Winds", "Clarinet"), "Oboe": ("Winds", "Oboe"),
         "Horn": ("Brass", "Horn"), "Mute Trumpet": ("Brass", "Mute Trumpet"), "Trombone": ("Brass", "Trombone"),
         "Strings": ("Strings", "Sustain"), "Tremolo": ("Strings", "Tremolo"),
         "Bells": ("Bells", "Church"), "Tubular": ("Bells", "Tubular"), "Vibes": ("Bells", "Vibes"),
         "Bowed Vibes": ("Bells", "Bowed Vibes"), "Glass": ("Bells", "Glass"),
         "Synth Pad": ("Synth", "Pad"), "Synth Lead": ("Synth", "Lead"), "Synth Brass": ("Synth", "Brass"),
         "Wind": ("Air", "Wind"), "Texture": ("Air", "Texture")}


def slot(x, sound, oct="Mid", k1=50, k2=50, k3=50, level=75):
    cat, opt = SOUND[sound]
    return {x + "_cat": cat, "%s_%s" % (x, cat.lower()): opt, x + "_oct": oct,
            x + "_k1": k1, x + "_k2": k2, x + "_k3": k3, x + "_level": level}


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
]

LEVEL = {'Init': 91, 'Lone Flute': 100, 'Midnight Sax': 100, 'Clay Ocarina': 100, 'Angel Lead': 94, 'Torch Song': 94, 'Saint Air': 74, 'Choir Drift': 83, 'High Heavens': 92, 'Monastery': 63, 'Doo Choir': 96, 'Glass Cathedral': 100, 'Music Box Ghost': 100, 'Wind Over Water': 100, 'Frozen Breath': 93, 'Astro Haze': 100, 'After Hours Fog': 76, 'Black Choir Stabs': 100, 'Dark Vowel Bed': 74, 'Distant Horn': 80, 'Smoke Trumpet': 90, 'Low Brass Hymn': 84, 'Reed Lament': 100, 'Celtic Oboe': 87, 'Frost Strings': 77, 'Shiver': 73, 'Bell Tower': 76, 'Midnight Vibes': 93, 'Bowed Halo': 74, 'Glass Prayer': 73, 'Juno Dawn': 87, 'Neon Lead': 100, 'Night Drive Brass': 92, 'Ghost Synth Choir': 73, 'Scat Doos': 73, 'Vesper Choir': 69, 'Ooh Pad': 63, 'Dah Section': 89, 'Bah Brass Doos': 80, 'Cloister': 66, 'Soprano Light': 75, 'Highland Flute': 79, 'Hollow Ocarina': 88, 'Lowlight Clarinet': 100, 'Reed Choir': 95, 'Sax and Smoke': 90, 'Funeral Horns': 76, 'Harmon Night': 100, 'Bone Choir': 74, 'Sorrow Cellos': 71, 'Shimmer Tremolo': 69, 'Storm Strings': 71, 'Snowfall Vibes': 72, 'Grave Bells': 80, 'Crystal Rain': 79, 'Bowed Choir': 83, 'Ninety Pad': 97, 'Velvet Pad': 85, 'Square Lead': 100, 'Slide Lead': 100, 'Bloom Brass': 100, 'Dark Synth Stabs': 100, 'Ghost Wind': 80, 'Ember Field': 74, 'Octave Dust': 70}   # output level per preset, filled from measured loudness so the set plays back evenly


TAG = {"Voices": "VOX", "Winds": "WND", "Brass": "BRS", "Strings": "STR", "Bells": "BEL", "Synth": "SYN", "Air": "AIR"}
ORDER = list(TAG)


def tagged():
    """Init first, then every preset grouped by slot A's category, its name tagged (VOX, WND...) for the MPC list."""
    out = [d for d in DESIGNS if d[0] == "Init"]
    rest = [d for d in DESIGNS if d[0] != "Init"]
    rest.sort(key=lambda d: ORDER.index(d[1]["a_cat"]))   # stable: keeps each group's own order
    for name, vals in rest:
        out.append(("%s %s" % (TAG[vals["a_cat"]], name), vals, name))
    return [(d[0], d[1], d[0]) if len(d) == 2 else d for d in out]


def main():
    by_key = {p["key"]: p for p in PARAMS}
    out = []
    for name, vals, base in tagged():
        assert len(name) <= 24, name
        values = {}
        for p in PARAMS:
            if p["key"] not in SKIP:
                values[p["key"]] = p["default"]
        values["master"] = LEVEL.get(base, values["master"])
        for k, v in vals.items():
            if k not in by_key:
                raise SystemExit("%s: unknown parameter %s" % (name, k))
            values[k] = v
        out.append({"name": name, "values": values})
    json.dump({"presets": out}, open(os.path.join(HERE, "presets.json"), "w"), indent=1)
    print("%d presets written" % len(out))


if __name__ == "__main__":
    main()
