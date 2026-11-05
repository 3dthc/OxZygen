#!/usr/bin/env python3
"""Write presets.json (listed in MPC's PRESET menu) from the designs below.

    python3 vst/make_presets.py

Every preset starts from the parameter defaults and then sets its own values, so each one fully defines the
sound: switching presets never leaves a layer or effect from the previous one behind. Names stay under 24
characters (the wrapper's limit) and are original: no other library's preset names.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = json.load(open(os.path.join(HERE, "params.json")))["params"]
SKIP = {"orb"}                     # engine-driven

# Texture Pitch steps: 0 = -24, 14 = -12, 29 = -5, 43 = unison, 57 = +7, 71 = +12, 86 = +19, 100 = +24
DESIGNS = [
    ("Init", {}),
    ("Saint Air", dict(  # choir pad on "oh" under a breathy sax lead, long hall
        ch_level=70, ch_vowel=50, ch_attack=55, ch_spread=60, choir=60,
        wi_inst="Sax", wi_level=70, wi_vibrato=55, wi_tone=55, wi_breath=45, voice=58,
        breath=55, air=55, dark=45, space=78, motion=45, rv_size=70, rv_decay=70, rv_mix=40,
        dl_mix=16, dl_time=62, dl_feedback=40)),
    ("Celtic Hall", dict(  # flute over an open "ah" choir with a few soft bells
        wi_inst="Flute", wi_level=75, wi_vibrato=50, wi_tone=60, wi_breath=55, voice=62,
        ch_level=55, ch_vowel=0, ch_spread=55, choir=45, be_level=30, be_decay=55, be_strike=35, bells=30,
        air=65, dark=35, space=72, rv_decay=60, rv_mix=35)),
    ("Choir Drift", dict(
        ch_level=75, ch_vowel=30, ch_spread=75, ch_attack=65, choir=70,
        vo_level=45, vo_morph=40, vo_formant=45, vo_attack=60,
        motion=70, space=80, dark=50, rv_decay=70)),
    ("Dark Vowel Bed", dict(
        vo_level=75, vo_morph=10, vo_formant=25, vo_attack=55, ch_level=40, ch_vowel=50, choir=65,
        dark=75, air=30, space=70, motion=55, sb_level=35, sb_tune=50, sb_drop=25, dr_mix=25, dr_amount=35)),
    ("Ocarina Night", dict(
        wi_inst="Ocarina", wi_level=75, wi_vibrato=60, wi_tone=55, voice=60,
        sc_level=40, sc_density=40, sc_drift=50, sc_width=70, air=60, space=75, dl_mix=22, dl_time=58)),
    ("Glass Cathedral", dict(
        be_level=70, be_strike=55, be_decay=70, be_shimmer=50, bells=70, ch_level=45, ch_vowel=100, choir=50,
        tx_level=25, tx_grain=70, tx_pitch=71, tx_smear=50, space=85, rv_size=80, rv_decay=80, rv_mix=40, air=60)),
    ("After Hours Fog", dict(  # dark late-night sax, driven, with a sub underneath
        wi_inst="Sax", wi_level=75, wi_vibrato=40, wi_tone=35, wi_breath=55, voice=65,
        ch_level=35, ch_vowel=50, choir=40, dark=70, air=35, dr_mix=50, dr_amount=45, dr_tone=45,
        sb_level=45, sb_drop=20, space=65, dl_mix=25, dl_time=70, dl_feedback=45)),
    ("Black Choir Stabs", dict(  # short, distorted "ah" choir with a dropping sub
        ch_level=85, ch_vowel=0, ch_attack=10, ch_spread=40, choir=80, breath=20,
        dr_mix=70, dr_amount=65, dr_tone=50, dark=55, sb_level=55, sb_drop=45, sb_tune=50,
        space=55, rv_mix=25, rv_decay=40)),
    ("Astro Haze", dict(  # granular voices a fifth up, vowels, long dark delay
        tx_level=60, tx_grain=55, tx_pitch=57, tx_smear=70, vo_level=50, vo_morph=60, vo_formant=50, choir=60,
        dl_mix=35, dl_time=68, dl_feedback=55, dark=60, space=80, motion=70, sb_level=30, sb_drop=30)),
    ("Wind Over Water", dict(
        sc_level=80, sc_density=35, sc_drift=65, sc_width=80, air=75, ch_level=0,
        be_level=20, be_decay=80, be_shimmer=70, bells=25, space=85, rv_decay=75, motion=60)),
    ("Frozen Breath", dict(
        tx_level=75, tx_grain=85, tx_pitch=86, tx_smear=85, sc_level=30, sc_density=50, ch_level=0,
        space=90, rv_decay=90, rv_mix=45, dark=40, air=70, motion=50)),
    ("Angel Lead", dict(
        vo_level=70, vo_morph=65, vo_formant=75, vo_attack=20, choir=65, ch_level=0,
        wi_inst="Flute", wi_level=50, wi_vibrato=45, voice=45, motion=40, space=70, dl_mix=20, dl_time=55, air=60)),
    ("Monastery", dict(  # low male choir in a very large room
        ch_level=85, ch_vowel=50, ch_attack=70, ch_spread=35, choir=75, dark=60, air=35,
        space=88, rv_size=85, rv_decay=85, rv_mix=45, sb_level=20, sb_drop=10)),
    ("Torch Song", dict(  # bright driven vowel lead
        vo_level=80, vo_morph=75, vo_formant=60, vo_attack=5, choir=75, ch_level=0,
        dr_mix=60, dr_amount=55, dr_tone=70, dl_mix=30, dl_time=45, dl_feedback=40, dark=25, air=60, space=55, motion=50)),
    ("Doo Choir", dict(  # short rounded "doo" voices for chords
        vo_level=70, vo_morph=15, vo_formant=50, vo_attack=8, ch_level=40, ch_vowel=50, ch_attack=15, choir=60,
        space=50, rv_decay=40, motion=30, dark=40)),
]


LEVEL = {'Init': 86, 'Saint Air': 61, 'Celtic Hall': 93, 'Choir Drift': 77, 'Dark Vowel Bed': 74, 'Ocarina Night': 73, 'Glass Cathedral': 74, 'After Hours Fog': 71, 'Black Choir Stabs': 73, 'Astro Haze': 77, 'Wind Over Water': 90, 'Frozen Breath': 73, 'Angel Lead': 99, 'Monastery': 62, 'Torch Song': 76, 'Doo Choir': 88}   # output level per preset, from measured loudness (target RMS 0.22)


def main():
    by_key = {p["key"]: p for p in PARAMS}
    out = []
    for name, vals in DESIGNS:
        assert len(name) <= 24, name
        values = {}
        for p in PARAMS:
            if p["key"] in SKIP:
                continue
            values[p["key"]] = p.get("default", p["options"][0] if p.get("options") else 0)
        values["master"] = LEVEL.get(name, values["master"])   # each preset levelled to the same loudness
        for k, v in vals.items():
            if k not in by_key:
                raise SystemExit("%s: unknown parameter %s" % (name, k))
            values[k] = v
        out.append({"name": name, "values": values})
    json.dump({"presets": out}, open(os.path.join(HERE, "presets.json"), "w"), indent=1)
    print("%d presets written" % len(out))


if __name__ == "__main__":
    main()
