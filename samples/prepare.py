#!/usr/bin/env python3
"""Turn the trimmed CC0 set (samples/build, from trim.sh) into the engine's sample data (vst/data).

    python3 samples/prepare.py [trimmed dir] [out dir] [sources dir]

The trimmed dir holds the original winds and choir set (trim.sh); the newer instruments (brass, reeds, strings,
tubular bells, vibraphone, wine glasses) are read straight from the sources dir (fetch_sources.sh).

For every sample:
  - mono, 16-bit, 44.1 kHz
  - its real pitch is measured (the sources name octaves differently), so each zone carries its root note and
    fine tuning in cents
  - sustained sounds get a seamless loop baked in: a stretch of the sustain, a whole number of pitch periods long, with an
    equal-power crossfade written into the audio before the loop end, so a held note can sustain forever
  - the audio after the loop end is dropped (the loop carries the sustain), which saves RAM
  - struck sounds (tubular bells, vibraphone) are one-shots: they ring out naturally, up to a length cap, with a
    short fade; their manifest line has loop_start = loop_end = frames (no loop)
  - each instrument group is levelled to one loudness, keeping soft/loud layers apart

Writes <out>/<inst>/*.wav and <out>/manifest.txt, one zone per line:
  inst var root cents loop_start loop_end frames file
Needs numpy and scipy.
"""
import glob
import math
import os
import re
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "vst", "data")
SRC2 = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "sources")
SR = 44100
MAX_LEN = {"flute": 3.2, "ocarina": 3.2, "sax": 3.2, "choir": 3.0,   # seconds kept up to the loop end
           "horn": 3.0, "mtrumpet": 3.0, "trombone": 3.0, "clarinet": 3.0, "oboe": 3.0,
           "strings": 3.4, "trem": 3.0, "bowedvibes": 4.0, "glass": 4.0}
ONESHOT = {"tubular": 6.0, "vibes": 4.5}                              # struck: seconds kept, no loop
TARGET_RMS = {"flute": 0.16, "ocarina": 0.14, "sax": 0.16, "choir": 0.15,
              "horn": 0.16, "mtrumpet": 0.15, "trombone": 0.16, "clarinet": 0.16, "oboe": 0.15,
              "strings": 0.15, "trem": 0.15, "bowedvibes": 0.14, "glass": 0.13, "tubular": 0.14, "vibes": 0.15}
NO_DETECT = {"tubular"}       # inharmonic: the heard pitch is not the fundamental, so trust the file names
FORCED_OFFSET = {"tubular": 12}   # ...but VCSL names every instrument an octave low (vibes, bowed vibes and glasses measure +12)

# the newer instruments, read from the sources: (inst, var, folder under SRC2, regex with the note as group 1)
EXTRA = [
    ("horn", "p", "vsco2ce/Brass/F Horn/sus", r"_sus_([A-G]#?\d)_v1_1"),
    ("horn", "f", "vsco2ce/Brass/F Horn/sus", r"_sus_([A-G]#?\d)_v3_1"),
    ("mtrumpet", "p", "vsco2ce/Brass/Trumpet/harmonM-sus", r"_harmonM-sus_([A-G]#?\d)_v1_rr1"),
    ("mtrumpet", "f", "vsco2ce/Brass/Trumpet/harmonM-sus", r"_harmonM-sus_([A-G]#?\d)_v3_rr1"),
    ("trombone", "p", "vsco2ce/Brass/Tenor Trombone/sus", r"_sus_([A-G]#?\d)_v1_1"),
    ("trombone", "f", "vsco2ce/Brass/Tenor Trombone/sus", r"_sus_([A-G]#?\d)_v3_1"),
    ("clarinet", "p", "vsco2ce/Woodwinds/Clarinet/susLong", r"_susLong_([A-G]#?\d)_v1_rr1"),
    ("clarinet", "f", "vsco2ce/Woodwinds/Clarinet/susLong", r"_susLong_([A-G]#?\d)_v3_rr1"),
    ("oboe", "nv_p", "vsco2ce/Woodwinds/Oboe/Sus", r"_Sus_([A-G]#?\d)_v1_"),
    ("oboe", "nv_f", "vsco2ce/Woodwinds/Oboe/Sus", r"_Sus_([A-G]#?\d)_v3_"),
    ("oboe", "vib", "vsco2ce/Woodwinds/Oboe/Vib", r"_Vib_([A-G]#?\d)_v3_"),
    ("strings", "vln", "vsco2ce/Strings/Violin Section/susVib", r"_susVib_([A-G]#?\d)_v1\."),
    ("strings", "vla", "vsco2ce/Strings/Viola Section/susvib", r"_susvib_([A-G]#?\d)_v1_1"),
    ("strings", "vc", "vsco2ce/Strings/Cello Section/susvib", r"^susvib_([A-G]#?\d)_v1_1"),
    ("trem", "vln", "vsco2ce/Strings/Violin Section/Trem", r"_Trem_([A-G]#?\d)_v1\."),
    ("trem", "vla", "vsco2ce/Strings/Viola Section/trem", r"_trem_([A-G]#?\d)_v2_rr1"),
    ("trem", "vc", "vsco2ce/Strings/Cello Section/trem", r"^trem_([A-G]#?\d)_v2_1"),
    ("tubular", "p", "vcsl/Idiophones/Struck Idiophones/Tubular Bells 1", r"chimes_([A-G]#?\d)_(?:p|pp)_rr\d"),
    ("tubular", "f", "vcsl/Idiophones/Struck Idiophones/Tubular Bells 1", r"chimes_([A-G]#?\d)_(?:ff|f|fff)_rr\d"),
    ("vibes", "p", "vcsl/Idiophones/Struck Idiophones/Vibraphone/Soft Mallets", r"_soft_([A-G]#?\d)_v1_rr1"),
    ("vibes", "f", "vcsl/Idiophones/Struck Idiophones/Vibraphone/Soft Mallets", r"_soft_([A-G]#?\d)_v2_rr1"),
    ("bowedvibes", "std", "vcsl/Idiophones/Struck Idiophones/Vibraphone/Bowed", r"_bowed_([A-G]#?\d)_rr1"),
    ("glass", "std", "vcsl/Idiophones/Friction Idiophones/Wine Glasses/Sustains/Slow", r"glass\d_([A-G]#?\d)_Slow"),
]
NOTE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def name_midi(n):
    """'A#4', 'ab2', 'Gb3' -> MIDI number with C4 = 60 (the source's own octave numbering; corrected later)."""
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", n)
    pc = NOTE[m.group(1).lower()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return 12 * (int(m.group(3)) + 1) + pc


def zones():
    """-> [(inst, var, named_midi, path)] from the trimmed set's file names."""
    out = []
    for p in sorted(glob.glob(os.path.join(SRC, "flute", "*", "*.wav"))):
        m = re.search(r"_sus(NV|vib)_([A-G]#?\d)_v(\d)", os.path.basename(p))
        var = "vib" if m.group(1) == "vib" else ("nv_p" if m.group(3) == "1" else "nv_f")
        out.append(("flute", var, name_midi(m.group(2)), p))
    for p in sorted(glob.glob(os.path.join(SRC, "ocarina", "*.wav"))):
        b = os.path.basename(p)
        m = re.search(r"StdOcarina_(SusVib|Sus)_([A-G]#?\d)", b) or re.search(r"ocarina_([A-G]#?\d)_sustain", b)
        if b.startswith("Std"):
            out.append(("ocarina", "vib" if m.group(1) == "SusVib" else "std", name_midi(m.group(2)), p))
        else:   # the small ocarina extends the range upward
            out.append(("ocarina", "std", name_midi(m.group(1)), p))
    for p in sorted(glob.glob(os.path.join(SRC, "sax", "*.wav"))):
        m = re.match(r"([a-g]b?\d)_([pf])_", os.path.basename(p))
        out.append(("sax", m.group(2), name_midi(m.group(1)), p))
    for d in sorted(glob.glob(os.path.join(SRC, "vowels", "*"))):
        singer, vowel = os.path.basename(d).split("-")
        for p in sorted(glob.glob(os.path.join(d, "*.wav"))):
            n = int(re.search(r"-(\d+)\.wav$", p).group(1))
            if n < 30:          # a stray file in the source set (sven-ih "2"); not a note
                continue
            out.append(("choir", "%s_%s" % (singer, vowel), n, p))
    seen = set()
    for inst, var, folder, rx in EXTRA:
        for p in sorted(glob.glob(os.path.join(SRC2, folder, "*.wav"))):
            m = re.search(rx, os.path.basename(p))
            if not m:
                continue
            n = name_midi(m.group(1))
            if (inst, var, n) in seen:        # several takes of one note: keep the first
                continue
            seen.add((inst, var, n))
            out.append((inst, var, n, p))
    return out


def load(p):
    if not p.startswith(SRC):                 # sources: any format, so decode with ffmpeg to mono 44.1 kHz
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype="<f4").astype(np.float32)
    w = wave.open(p)
    ch, n = w.getnchannels(), w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x


def f0_of(x):
    """Fundamental: the median of four 120 ms windows across the note (a single window wobbles by ~15 cents)."""
    n = len(x)
    est = [f for f in (f0_window(x[int(n * fr): int(n * fr) + int(0.12 * SR)]) for fr in (0.25, 0.4, 0.55, 0.7)) if f]
    return float(np.median(est)) if est else None


def f0_window(seg):
    """YIN-style difference function over one window."""
    if len(seg) < 2048:
        return None
    lo, hi = int(SR / 1500), int(SR / 50)
    w = len(seg) - hi
    if w < 256:
        return None
    d = np.array([np.sum((seg[:w] - seg[t:t + w]) ** 2) for t in range(hi)])
    cmnd = d.copy()
    cmnd[1:] = d[1:] * np.arange(1, hi) / np.maximum(np.cumsum(d[1:]), 1e-12)
    cmnd[0] = 1
    cand = np.where(cmnd[lo:] < 0.15)[0]
    t = (cand[0] + lo) if len(cand) else (np.argmin(cmnd[lo:]) + lo)
    while t + 1 < hi and cmnd[t + 1] < cmnd[t]:
        t += 1
    if 1 <= t < hi - 1:   # parabolic refinement
        a, b, c = cmnd[t - 1], cmnd[t], cmnd[t + 1]
        den = a - 2 * b + c
        t = t + (0.5 * (a - c) / den if den else 0)
    return SR / t


def bake_loop(x, period, inst):
    """-> (audio, loop_start, loop_end): loop a whole number of periods, crossfade baked before the end."""
    n = len(x)
    env = np.sqrt(np.convolve(x ** 2, np.ones(1024) / 1024, mode="same"))
    peak = env.max()
    att = int(np.argmax(env > 0.6 * peak))                  # end of the attack
    end_lim = min(n - int(0.06 * SR), int(MAX_LEN[inst] * SR))
    start = max(att + int(0.08 * SR), int(0.18 * n))
    if end_lim - start < int(0.25 * SR):                    # very short sample: loop more of it
        start = max(int(0.12 * SR), att)
    start = min(start, end_lim - int(0.2 * SR))
    length = end_lim - start
    if period:
        k = max(1, int(length / period))
        length = int(round(k * period))
    end = start + length
    xf = min(int(0.3 * SR), length // 2, start)               # crossfade length
    y = x[:end].copy()
    t = np.linspace(0, 1, xf, endpoint=False)
    fade_out, fade_in = np.cos(t * np.pi / 2), np.sin(t * np.pi / 2)
    y[end - xf:end] = x[end - xf:end] * fade_out + x[start - xf:start] * fade_in
    return y, start, end


def main():
    zs = zones()
    rows, groups = [], {}
    for inst, var, named, p in zs:
        x = load(p)
        f0 = None if inst in NO_DETECT else f0_of(x)
        det = 69 + 12 * math.log2(f0 / 440.0) if f0 else None
        groups.setdefault(inst, []).append((var, named, det, x, p))

    os.makedirs(OUT, exist_ok=True)
    total = 0
    report = []
    for inst, items in groups.items():
        # octave convention per instrument: the most common (detected - named) multiple of 12
        offs = [round((d - n) / 12) * 12 for _, n, d, _, _ in items if d is not None]
        off = max(set(offs), key=offs.count) if offs else 0
        off = FORCED_OFFSET.get(inst, off)
        report.append("%s: named octave %+d, %d zones" % (inst, off, len(items)))
        rms_all = []
        prepared = []
        for var, named, det, x, p in items:
            root = named + off
            cents = 0.0
            if det is not None and abs(det - root) < 0.75:   # trust the measurement for fine tuning only
                cents = (det - root) * 100.0
            if inst in ONESHOT:               # struck: ring out to the cap, fade the last 60 ms, no loop
                y = x[:int(ONESHOT[inst] * SR)].copy()
                fade = min(len(y), int(0.06 * SR))
                y[len(y) - fade:] *= np.linspace(1, 0, fade)
                ls = le = len(y)
                mid = y[:int(0.6 * SR)]
            else:
                period = SR / (440.0 * 2 ** ((root + cents / 100 - 69) / 12))
                y, ls, le = bake_loop(x, period, inst)
                mid = y[ls:le]
            rms_all.append(float(np.sqrt(np.mean(mid ** 2))) if len(mid) else 0.0)
            prepared.append((var, root, cents, y, ls, le, p))
        gain = TARGET_RMS[inst] / max(1e-6, float(np.median([r for r in rms_all if r > 0])))
        os.makedirs(os.path.join(OUT, inst), exist_ok=True)
        for var, root, cents, y, ls, le, p in prepared:
            y = np.clip(y * gain, -1, 1)
            fn = "%s/%s_%d.wav" % (inst, var, root)
            k = 2
            while os.path.exists(os.path.join(OUT, fn)) and any(r[-1] == fn for r in rows):
                fn = "%s/%s_%d_%d.wav" % (inst, var, root, k)
                k += 1
            w = wave.open(os.path.join(OUT, fn), "wb")
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((y * 32767).astype("<i2").tobytes())
            w.close()
            total += len(y) * 2
            rows.append((inst, var, root, cents, ls, le, len(y), fn))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(os.path.join(OUT, "manifest.txt"), "w") as f:
        f.write("# inst var root cents loop_start loop_end frames file  (generated by samples/prepare.py)\n")
        for r in rows:
            f.write("%s %s %d %.1f %d %d %d %s\n" % r)
    print("\n".join(report))
    print("%d zones, %.1f MB of 16-bit audio (= RAM when loaded)" % (len(rows), total / 1e6))


if __name__ == "__main__":
    main()
