#!/usr/bin/env bash
# OxZygen v1 trim: copies a reduced subset of CC0 sources into build/
# and converts to 16-bit / 44.1 kHz WAV. Source repos are read-only inputs.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/sources"
OUT="$HERE/build"

rm -rf "$OUT"
mkdir -p "$OUT/vowels" "$OUT/flute" "$OUT/ocarina" "$OUT/sax"

conv() { # conv <in> <out>
  ffmpeg -v error -y -i "$1" -c:a pcm_s16le -ar 44100 "$2"
}

# 1. Vowels: SpectMorph CC0 (claudia, mirko, sven x ah/ih/oh)
for v in claudia-ah claudia-ih claudia-oh mirko-ah mirko-oh sven-ah sven-ih sven-oh; do
  mkdir -p "$OUT/vowels/$v"
  for f in "$SRC/spectmorph/$v"/*.flac; do
    conv "$f" "$OUT/vowels/$v/$(basename "${f%.flac}").wav"
  done
done

# 2. Flute: VSCO 2 CE (CC0). Keep sustain (no vibrato) and sustain with vibrato.
#    Dropped for v1: staccato (48 files) and expressive vibrato.
for art in susNV susvib; do
  mkdir -p "$OUT/flute/$art"
  for f in "$SRC/vsco2ce/Woodwinds/Flute/$art"/*.wav; do
    conv "$f" "$OUT/flute/$art/$(basename "${f%.wav}").wav"
  done
done

# 3. Ocarina: VCSL (CC0). Sustains only. Recorder and Releases dropped for v1.
mkdir -p "$OUT/ocarina"
OCA="$SRC/vcsl/Aerophones/Edge-blown Aerophones"
for f in "$OCA/Ocarina, Typical/Sustains/Sus"/*.wav \
         "$OCA/Ocarina, Typical/Sustains/SusVib"/*.wav \
         "$OCA/Ocarina, Small/Sustain"/*.wav; do
  [ -e "$f" ] || continue
  conv "$f" "$OUT/ocarina/$(basename "${f%.wav}").wav"
done

# 4. Alto sax: Weresax (CC0). One round robin (rr1), both dynamics, one mic variant (dnm).
#    Dropped for v1: rr2 and the cnd mic variant (halves the set; add back in lite/full later).
mkdir -p "$OUT/sax"
for f in "$SRC/weresax/Samples/alto"/*_rr1_dnm.wav; do
  conv "$f" "$OUT/sax/$(basename "${f%.wav}").wav"
done

echo "done"
for d in vowels flute ocarina sax; do
  echo "$d: $(find "$OUT/$d" -name '*.wav' | wc -l) files, $(du -sh "$OUT/$d" | cut -f1)"
done
echo "total: $(du -sh "$OUT" | cut -f1)"
