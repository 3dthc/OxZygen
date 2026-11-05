#!/usr/bin/env bash
# Download the CC0 sample sources into samples/sources/ (not committed; about 15 GB in total, VCSL is most of it).
# Every source here is CC0 1.0; see CREDITS.md.
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)/sources"
mkdir -p "$S"
clone() { [ -d "$S/$1" ] || git clone --depth 1 "$2" "$S/$1"; }
clone vsco2ce    https://github.com/sgossner/VSCO-2-CE.git
clone vcsl       https://github.com/trbngr/VCSL.git
clone weresax    https://github.com/sfzinstruments/karoryfer.weresax.git
clone spectmorph https://github.com/swesterfeld/spectmorph-instruments.git
echo "Sources ready in $S"
