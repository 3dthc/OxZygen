#!/usr/bin/env bash
# Build, test and package an OxZygen target with the MPC VST toolchain (open-mpc/mpc-vst-plugins).
#   ./build.sh            OxZygen itself (vst/)
#   ./build.sh sdtest     the SD card access test plugin
# Needs the toolchain checked out (default ~/mpc-vst-plugins; override with MPC_VST=/path) and Docker running.
# The first OxZygen build also downloads the toolchain's skin renderer image (Chromium), which takes a while once.
# Output (dist/, also copied to your Windows Desktop when run in WSL):
#   OxZygen-<ver>-mpc-armv7.zip      Gen1: MPC Live / Live II / One / X / Force on MPC OS 3.x
#   OxZygen-<ver>-mpc-armv7-os2.zip  the same devices still on MPC OS 2.x
#   OxZygen-<ver>-mpc-aarch64.zip    Gen2: MPC Live III and the other 64-bit models (MPC OS 3.x only)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins}"
TARGET="${1:-oxzygen}"

LICENSE_ARGS=()
EXTRA_ARGS=()
case "$TARGET" in
  oxzygen) CFG="$HERE/vst/vst.json"; VER="0.7.0"
           ABOUT="OxZygen 0.7: two sound slots (voices, winds, brass, strings, bells, synth, air: 22 sounds), filter, lo-fi, drive, delay, reverb, sub; 96 presets"
           EXTRA_ARGS=(--extra "$HERE/vst/data:samples" --id oxzygen); LICENSE_ARGS=(--license MIT)
           [ -f "$HERE/vst/data/manifest.txt" ] || { echo "vst/data is missing: run samples/fetch_sources.sh, samples/trim.sh, then python3 samples/prepare.py"; exit 1; } ;;
  sdtest)  CFG="$HERE/tests/sdtest/vst.json"; VER="1.0.0"; ABOUT="OxZygen SD card access test"; LICENSE_ARGS=(--license MIT) ;;
  *) echo "Unknown target '$TARGET'. Targets: oxzygen, sdtest"; exit 1 ;;
esac

if [ ! -x "$MPC_VST/tools/build_port.sh" ]; then
  echo "Toolchain not found at $MPC_VST. Clone it there or run: MPC_VST=/path/to/mpc-vst-plugins ./build.sh $TARGET"
  exit 1
fi

DIR="$(dirname "$CFG")"
NAME="$(python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); print(c["vendor"]+" - VST - "+c["name"])' "$CFG")"
SO="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["so"])' "$CFG")"

pkg() {   # pkg <so> <skin dir> <label>: one release zip, renamed so the three builds don't collide
  local out="$HERE/dist/.tmp"; rm -rf "$out"; mkdir -p "$out"
  python3 "$MPC_VST/tools/release.py" --so "$1" --skin "$2" \
    --entry "$DIR/build/pluginlist-entry.xml" --version "$VER" --about "$ABOUT" \
    ${LICENSE_ARGS[@]+"${LICENSE_ARGS[@]}"} ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} --repo 3dthc/OxZygen -o "$out"
  local z; z="$(ls "$out"/*.zip | head -n 1)"
  local name; name="$(basename "$z" .zip)$3.zip"
  mv "$z" "$HERE/dist/$name"; ZIPS+=("$HERE/dist/$name")
  rm -rf "$out"
}
mkdir -p "$HERE/dist"
ZIPS=()

if [ "$TARGET" = oxzygen ]; then
  # Gen1 (32-bit: Live, Live II, One, X, Force) and Gen2 (64-bit: Live III and later), MPC OS 3.x skin
  echo "== build: Gen1 + Gen2, MPC OS 3 skin"
  "$MPC_VST/tools/build_port.sh" "$CFG" all
  echo "== offline test"
  "$MPC_VST/tools/test_port.sh" "$CFG"
  echo "== package"
  pkg "$DIR/build/$SO" "$DIR/build/skin/$NAME" ""
  pkg "$DIR/build/aarch64/$SO" "$DIR/build/skin/$NAME" ""
  # Gen1 on MPC OS 2.x: same plugin (built to load on 2.x), skin written in the 2.x file format
  echo "== build: Gen1, MPC OS 2 skin"
  SHADOW_SKIN_MPC_OS=2 "$MPC_VST/tools/build_port.sh" "$CFG" armv7
  pkg "$DIR/build/$SO" "$DIR/build/skin/$NAME" "-os2"
else
  echo "== build ($TARGET)"
  "$MPC_VST/tools/build_port.sh" "$CFG"
  echo "== offline test"
  "$MPC_VST/tools/test_port.sh" "$CFG"
  pkg "$DIR/build/$SO" "$DIR/build/skin/$NAME" ""
fi
echo "== zips:"; printf '   %s\n' "${ZIPS[@]}"

# In WSL, put a copy where Windows can see it.
if [ -d "/mnt/c/Users/$USER" ]; then
  for d in "/mnt/c/Users/$USER/OneDrive/Desktop" "/mnt/c/Users/$USER/Desktop"; do
    if [ -d "$d" ]; then cp "${ZIPS[@]}" "$d/"; echo "== copied to Windows: $d"; break; fi
  done
fi
